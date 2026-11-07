"""Lending & credit (spec sections 18-20). Amortization math is exact integer arithmetic
(Decimal internally, converted to integer kobo with half-even rounding); no floats anywhere.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from ...security.permissions import Principal
from ...shared.clock import to_iso
from ...shared.context import Context
from ...shared.errors import (Conflict, LoanNotEligible, NotFound, UnauthorizedResourceAccess, ValidationFailed)
from ...shared.ids import new_id
from ...shared.money import Money
from ...shared.state_machine import StateMachine
from ..ledger.service import INTEREST_REVENUE, LOAN_FUNDING, LOAN_RECEIVABLE, C, D, LedgerService, wallet_code
from ..payments.idempotency import IdempotencyService
from .scoring import MODEL_VERSION, score_applicant

APP_SM = StateMachine("loan_application", {
    "APPLICATION": ["ASSESSMENT", "CANCELLED"],
    "ASSESSMENT": ["APPROVED", "REJECTED"],
    "APPROVED": ["DISBURSED", "CANCELLED"],
})
LOAN_SM = StateMachine("loan", {
    "DISBURSED": ["ACTIVE"],
    "ACTIVE": ["REPAYING", "DEFAULTED"],
    "REPAYING": ["COMPLETED", "DEFAULTED"],
})


def _cents(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


class LendingService:
    def __init__(self, ctx: Context, ledger: LedgerService, idem: IdempotencyService):
        self.ctx, self.db, self.ledger, self.idem = ctx, ctx.db, ledger, idem

    # -------------------------------------------------------------- products
    def create_product(self, principal: Principal, *, lender_org_id: str, name: str, min_amount_minor: int,
                       max_amount_minor: int, min_term_months: int, max_term_months: int, annual_rate_bps: int,
                       late_fee_bps: int = 0, min_credit_score: int = 0, requires_verified_farm: bool = True) -> dict:
        principal.require("loan:product_create")
        if not principal.is_org_member(lender_org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that lender organization")
        if min_amount_minor <= 0 or max_amount_minor < min_amount_minor:
            raise ValidationFailed("invalid amount range")
        if min_term_months <= 0 or max_term_months < min_term_months:
            raise ValidationFailed("invalid term range")
        if annual_rate_bps < 0 or late_fee_bps < 0:
            raise ValidationFailed("rates cannot be negative")
        pid = new_id()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO loan_products(id,lender_org_id,name,min_amount_minor,max_amount_minor,min_term_months,"
                "max_term_months,annual_rate_bps,late_fee_bps,min_credit_score,requires_verified_farm,active,"
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (pid, lender_org_id, name.strip()[:120], min_amount_minor, max_amount_minor, min_term_months,
                 max_term_months, annual_rate_bps, late_fee_bps, min_credit_score, 1 if requires_verified_farm else 0,
                 self.ctx.now_iso()))
        return self.db.one("SELECT * FROM loan_products WHERE id=?", (pid,))

    # ---------------------------------------------------------------- scoring
    def assess(self, user_id: str, application_id: str | None = None) -> dict:
        farm_verified = bool(self.db.one("SELECT 1 FROM farms WHERE owner_user_id=? AND verification_status='VERIFIED'",
                                         (user_id,)))
        kyc_verified = bool(self.db.one("SELECT 1 FROM kyc_records WHERE user_id=? AND status='VERIFIED'", (user_id,)))
        orders = self.db.one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_minor),0) AS v FROM orders WHERE seller_id=? AND state='COMPLETED'",
            (user_id,))
        defaulted = self.db.scalar("SELECT COUNT(*) FROM loans WHERE borrower_id=? AND state='DEFAULTED'", (user_id,))
        active = self.db.scalar("SELECT COUNT(*) FROM loans WHERE borrower_id=? AND state IN ('ACTIVE','REPAYING')",
                                (user_id,))
        on_time = self.db.scalar(
            "SELECT COUNT(*) FROM repayment_schedule s JOIN loans l ON l.id=s.loan_id WHERE l.borrower_id=?"
            " AND s.status='PAID' AND s.paid_at<=s.due_date", (user_id,))
        late = self.db.scalar(
            "SELECT COUNT(*) FROM repayment_schedule s JOIN loans l ON l.id=s.loan_id WHERE l.borrower_id=?"
            " AND s.status='PAID' AND s.paid_at>s.due_date", (user_id,))
        result = score_applicant(farm_verified=farm_verified, kyc_verified=kyc_verified,
                                 completed_orders=orders["n"], completed_orders_value_minor=orders["v"],
                                 defaulted_loans=defaulted or 0, active_loans=active or 0,
                                 on_time_repayments=on_time or 0, late_repayments=late or 0)
        import json
        aid = new_id()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO credit_assessments(id,user_id,application_id,score,risk_grade,factors,features,"
                "model_version,generated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (aid, user_id, application_id, result.score, result.risk_grade, json.dumps(result.factors),
                 json.dumps(result.features), MODEL_VERSION, self.ctx.now_iso()))
        return self.db.one("SELECT * FROM credit_assessments WHERE id=?", (aid,))

    def credit_view(self, principal: Principal, user_id: str) -> dict | None:
        if user_id != principal.user_id and not principal.has("credit:view_applicants") and not principal.is_admin:
            raise UnauthorizedResourceAccess("cannot view this applicant's credit history")
        return self.db.one("SELECT * FROM credit_assessments WHERE user_id=? ORDER BY generated_at DESC LIMIT 1",
                           (user_id,))

    # ------------------------------------------------------------ application
    def apply(self, principal: Principal, *, product_id: str, amount_minor: int, term_months: int,
             purpose: str = "") -> dict:
        principal.require("loan:apply")
        product = self.db.one("SELECT * FROM loan_products WHERE id=? AND active=1", (product_id,))
        if not product:
            raise NotFound("loan product not found")
        if not product["min_amount_minor"] <= amount_minor <= product["max_amount_minor"]:
            raise ValidationFailed("amount is outside this product's range",
                                   details={"min": product["min_amount_minor"], "max": product["max_amount_minor"]})
        if not product["min_term_months"] <= term_months <= product["max_term_months"]:
            raise ValidationFailed("term is outside this product's range",
                                   details={"min": product["min_term_months"], "max": product["max_term_months"]})
        if self.db.scalar("SELECT COUNT(*) FROM loan_applications WHERE applicant_id=? AND state IN"
                          " ('APPLICATION','ASSESSMENT','APPROVED')", (principal.user_id,)):
            raise Conflict("you already have a pending loan application")
        aid = new_id()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO loan_applications(id,applicant_id,product_id,amount_minor,term_months,purpose,state,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,'APPLICATION',?,?)",
                (aid, principal.user_id, product_id, amount_minor, term_months, purpose[:1000], self.ctx.now_iso(),
                 self.ctx.now_iso()))
            assessment = self.assess(principal.user_id, aid)
            self.db.execute("UPDATE loan_applications SET state='ASSESSMENT', credit_assessment_id=?,"
                            " version=version+1, updated_at=? WHERE id=?", (assessment["id"], self.ctx.now_iso(), aid))
            self.ctx.publish("loan.application_submitted", "loan_application", aid, {"score": assessment["score"]})
        return self._load_app(aid)

    def _load_app(self, aid: str) -> dict:
        row = self.db.one("SELECT * FROM loan_applications WHERE id=?", (aid,))
        if not row:
            raise NotFound("loan application not found")
        return row

    def decide(self, principal: Principal, application_id: str, *, approve: bool, reason: str,
              override: bool = False) -> dict:
        principal.require("loan:approve")
        if not reason or len(reason.strip()) < 5:
            raise ValidationFailed("a decision reason is required")
        with self.db.transaction():
            app = self._load_app(application_id)
            if app["state"] != "ASSESSMENT":
                raise Conflict("application is not awaiting a decision")
            product = self.db.one("SELECT * FROM loan_products WHERE id=?", (app["product_id"],))
            if not principal.is_org_member(product["lender_org_id"]) and not principal.is_admin:
                raise UnauthorizedResourceAccess("not a member of the lending organization")
            if approve:
                assessment = self.db.one("SELECT * FROM credit_assessments WHERE id=?", (app["credit_assessment_id"],))
                farm_ok = not product["requires_verified_farm"] or bool(
                    self.db.one("SELECT 1 FROM farms WHERE owner_user_id=? AND verification_status='VERIFIED'",
                               (app["applicant_id"],)))
                if (assessment["score"] < product["min_credit_score"] or not farm_ok) and not override:
                    raise LoanNotEligible("applicant does not meet this product's eligibility bar",
                                          details={"score": assessment["score"],
                                                   "min_required": product["min_credit_score"], "farm_ok": farm_ok})
            new_state = "APPROVED" if approve else "REJECTED"
            res = self.db.execute("UPDATE loan_applications SET state=?, decided_by=?, decision_reason=?,"
                                  " version=version+1, updated_at=? WHERE id=? AND version=?",
                                  (new_state, principal.user_id, reason.strip()[:1000], self.ctx.now_iso(),
                                   application_id, app["version"]))
            if res.rowcount != 1:
                raise Conflict("application was modified concurrently; retry")
            self.ctx.log_transition("loan_application", application_id, app["state"], new_state, principal.user_id, reason)
            return self._load_app(application_id)

    # ---------------------------------------------------------------- disbursement
    def disburse(self, principal: Principal, application_id: str, idempotency_key: str) -> dict:
        principal.require("loan:disburse")

        def cmd():
            app = self._load_app(application_id)
            if app["state"] != "APPROVED":
                raise Conflict("application must be APPROVED before disbursement", details={"state": app["state"]})
            product = self.db.one("SELECT * FROM loan_products WHERE id=?", (app["product_id"],))
            if not principal.is_org_member(product["lender_org_id"]) and not principal.is_admin:
                raise UnauthorizedResourceAccess("not a member of the lending organization")
            lid = new_id()
            self.ledger.ensure_wallet(app["applicant_id"])
            self.ledger.post(reference=f"loan_disburse:{lid}", entry_type="LOAN_DISBURSE",
                             description=f"Loan disbursed for application {application_id}",
                             lines=[D(LOAN_RECEIVABLE, app["amount_minor"]),
                                    C(wallet_code(app["applicant_id"]), app["amount_minor"])],
                             actor_id=principal.user_id)
            self.db.execute(
                "INSERT INTO loans(id,application_id,borrower_id,product_id,lender_org_id,principal_minor,"
                "term_months,annual_rate_bps,late_fee_bps,state,disbursed_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE',?,?)",
                (lid, application_id, app["applicant_id"], product["id"], product["lender_org_id"],
                 app["amount_minor"], app["term_months"], product["annual_rate_bps"], product["late_fee_bps"],
                 self.ctx.now_iso(), self.ctx.now_iso()))
            self._generate_schedule(lid, app["amount_minor"], app["term_months"], product["annual_rate_bps"])
            self.db.execute("UPDATE loan_applications SET state='DISBURSED', version=version+1, updated_at=?"
                            " WHERE id=?", (self.ctx.now_iso(), application_id))
            self.ctx.publish("loan.disbursed", "loan", lid, {"amount_minor": app["amount_minor"]})
            return self._load_loan(lid)
        res = self.idem.run(scope=principal.user_id, key=idempotency_key,
                            endpoint=f"POST /applications/{application_id}/disburse",
                            payload={"application_id": application_id}, fn=cmd)
        return res.body

    def _generate_schedule(self, loan_id: str, principal_minor: int, term_months: int, annual_rate_bps: int) -> None:
        """Reducing-balance amortization, equal-ish installments; the last installment absorbs all rounding
        so the schedule always sums EXACTLY to the disbursed principal - no float drift, no stray kobo."""
        monthly_rate = Decimal(annual_rate_bps) / Decimal(120_000)     # bps/12/10000
        balance = Decimal(principal_minor)
        if monthly_rate == 0:
            payment = (balance / term_months)
        else:
            factor = (1 + monthly_rate) ** term_months
            payment = balance * monthly_rate * factor / (factor - 1)
        now = self.ctx.clock.now()
        for n in range(1, term_months + 1):
            interest_due = _cents(balance * monthly_rate)
            if n == term_months:
                principal_due = _cents(balance)     # absorb rounding: pay off exactly what's left
            else:
                principal_due = _cents(payment) - interest_due
                principal_due = max(0, min(principal_due, _cents(balance)))
            balance -= principal_due
            due_date = to_iso(now + timedelta(days=30 * n))
            self.db.execute(
                "INSERT INTO repayment_schedule(id,loan_id,schedule_version,installment_no,due_date,"
                "principal_due_minor,interest_due_minor,status) VALUES (?,?,?,?,?,?,?,'PENDING')",
                (new_id(), loan_id, 1, n, due_date, principal_due, interest_due))

    def _load_loan(self, loan_id: str) -> dict:
        row = self.db.one("SELECT * FROM loans WHERE id=?", (loan_id,))
        if not row:
            raise NotFound("loan not found")
        return row

    def get_loan(self, principal: Principal, loan_id: str) -> dict:
        row = self._load_loan(loan_id)
        if row["borrower_id"] != principal.user_id and not principal.is_org_member(row["lender_org_id"]) \
                and not principal.has("loan:read_any"):
            raise UnauthorizedResourceAccess("not your loan")
        return row

    def schedule(self, principal: Principal, loan_id: str) -> list[dict]:
        self.get_loan(principal, loan_id)   # authorization check
        return self.db.all("SELECT * FROM repayment_schedule WHERE loan_id=? ORDER BY installment_no", (loan_id,))

    # ------------------------------------------------------------------ listings
    # Added for the frontend's lending screens - the original route set only
    # exposed single-resource reads plus the write actions, with no way to
    # browse products or see "my applications" / "my loans". That is a real
    # gap for any UI, not just a nice-to-have (see the same pattern already
    # applied to logistics' list_vehicles/list_drivers/list_shipments).

    def list_products(self, lender_org_id: str | None = None) -> list[dict]:
        """Active loan products, optionally scoped to one lender. Deliberately
        unauthenticated-shape (no principal) - any logged-in user should be
        able to browse what's on offer before applying, same as marketplace
        listings."""
        if lender_org_id:
            return self.db.all("SELECT * FROM loan_products WHERE active=1 AND lender_org_id=? ORDER BY name",
                               (lender_org_id,))
        return self.db.all("SELECT * FROM loan_products WHERE active=1 ORDER BY name")

    def list_applications(self, principal: Principal) -> list[dict]:
        """A borrower sees their own applications; a lender sees applications
        against their org's products; an admin sees everything."""
        if principal.is_admin:
            return self.db.all("SELECT * FROM loan_applications ORDER BY created_at DESC")
        org_ids = tuple(principal.org_roles.keys())
        if org_ids:
            placeholders = ",".join("?" * len(org_ids))
            return self.db.all(
                f"SELECT a.* FROM loan_applications a JOIN loan_products p ON p.id = a.product_id"
                f" WHERE a.applicant_id=? OR p.lender_org_id IN ({placeholders}) ORDER BY a.created_at DESC",
                (principal.user_id, *org_ids),
            )
        return self.db.all("SELECT * FROM loan_applications WHERE applicant_id=? ORDER BY created_at DESC",
                           (principal.user_id,))

    def list_loans(self, principal: Principal) -> list[dict]:
        """A borrower sees their own loans; a lender sees loans under their
        org; an admin sees everything."""
        if principal.is_admin:
            return self.db.all("SELECT * FROM loans ORDER BY updated_at DESC")
        org_ids = tuple(principal.org_roles.keys())
        if org_ids:
            placeholders = ",".join("?" * len(org_ids))
            return self.db.all(
                f"SELECT * FROM loans WHERE borrower_id=? OR lender_org_id IN ({placeholders})"
                f" ORDER BY updated_at DESC",
                (principal.user_id, *org_ids),
            )
        return self.db.all("SELECT * FROM loans WHERE borrower_id=? ORDER BY updated_at DESC", (principal.user_id,))

    # ---------------------------------------------------------------- servicing
    def mark_overdue(self) -> int:
        """Worker: flags PENDING/PARTIAL installments past due as OVERDUE and accrues a one-time late fee."""
        today = self.ctx.now_iso()
        rows = self.db.all(
            "SELECT s.*, l.late_fee_bps FROM repayment_schedule s JOIN loans l ON l.id=s.loan_id"
            " WHERE s.status IN ('PENDING','PARTIAL') AND s.due_date < ?", (today,))
        n = 0
        for r in rows:
            with self.db.transaction():
                outstanding = (r["principal_due_minor"] - r["principal_paid_minor"]) + \
                              (r["interest_due_minor"] - r["interest_paid_minor"])
                penalty = Money(outstanding).bps(r["late_fee_bps"]).minor if r["late_fee_bps"] else 0
                self.db.execute("UPDATE repayment_schedule SET status='OVERDUE', penalty_minor=? WHERE id=?",
                                (penalty, r["id"]))
                n += 1
        return n

    def repay(self, principal: Principal, loan_id: str, amount_minor: int, idempotency_key: str) -> dict:
        principal.require("loan:repay")
        if not isinstance(amount_minor, int) or isinstance(amount_minor, bool) or amount_minor <= 0:
            raise ValidationFailed("amount_minor must be a positive integer")

        def cmd():
            loan = self._load_loan(loan_id)
            if loan["borrower_id"] != principal.user_id:
                raise UnauthorizedResourceAccess("not your loan")
            if loan["state"] not in ("ACTIVE", "REPAYING"):
                raise Conflict("loan is not open for repayment", details={"state": loan["state"]})
            rows = self.db.all("SELECT * FROM repayment_schedule WHERE loan_id=? AND status IN"
                               " ('PENDING','PARTIAL','OVERDUE') ORDER BY installment_no", (loan_id,))
            outstanding = sum((r["principal_due_minor"] - r["principal_paid_minor"]) +
                              (r["interest_due_minor"] - r["interest_paid_minor"]) +
                              (r["penalty_minor"] - r["penalty_paid_minor"]) for r in rows)
            if amount_minor > outstanding:
                raise ValidationFailed("amount exceeds the outstanding balance", details={"outstanding": outstanding})
            remaining = amount_minor
            principal_paid_total = interest_paid_total = penalty_paid_total = 0
            for r in rows:
                if remaining <= 0:
                    break
                pen_gap = r["penalty_minor"] - r["penalty_paid_minor"]
                take = min(pen_gap, remaining)
                pen_paid = r["penalty_paid_minor"] + take
                remaining -= take
                penalty_paid_total += take
                int_gap = r["interest_due_minor"] - r["interest_paid_minor"]
                take = min(int_gap, remaining)
                int_paid = r["interest_paid_minor"] + take
                remaining -= take
                interest_paid_total += take
                prin_gap = r["principal_due_minor"] - r["principal_paid_minor"]
                take = min(prin_gap, remaining)
                prin_paid = r["principal_paid_minor"] + take
                remaining -= take
                principal_paid_total += take
                fully_paid = prin_paid == r["principal_due_minor"] and int_paid == r["interest_due_minor"]
                status = "PAID" if fully_paid else ("PARTIAL" if (prin_paid or int_paid or pen_paid) else r["status"])
                self.db.execute(
                    "UPDATE repayment_schedule SET principal_paid_minor=?, interest_paid_minor=?, penalty_paid_minor=?,"
                    " status=?, paid_at=? WHERE id=?",
                    (prin_paid, int_paid, pen_paid, status, self.ctx.now_iso() if fully_paid else r["paid_at"], r["id"]))
            reference = f"loan_repay:{loan_id}:{idempotency_key}"
            lines = [D(wallet_code(principal.user_id), amount_minor)]
            if principal_paid_total:
                lines.append(C(LOAN_RECEIVABLE, principal_paid_total))
            if interest_paid_total + penalty_paid_total:
                lines.append(C(INTEREST_REVENUE, interest_paid_total + penalty_paid_total))
            entry = self.ledger.post(reference=reference, entry_type="LOAN_REPAYMENT",
                                     description=f"Repayment on loan {loan_id}", lines=lines, actor_id=principal.user_id)
            self.db.execute("INSERT INTO repayments(id,loan_id,payer_id,amount_minor,reference,ledger_entry_id,at)"
                            " VALUES (?,?,?,?,?,?,?)",
                            (new_id(), loan_id, principal.user_id, amount_minor, reference, entry["id"],
                             self.ctx.now_iso()))
            all_paid = not self.db.one("SELECT 1 FROM repayment_schedule WHERE loan_id=? AND status!='PAID'", (loan_id,))
            new_state = "COMPLETED" if all_paid else "REPAYING"
            self.db.execute("UPDATE loans SET state=?, version=version+1, updated_at=? WHERE id=?",
                            (new_state, self.ctx.now_iso(), loan_id))
            if new_state == "COMPLETED":
                self.ctx.publish("loan.completed", "loan", loan_id, {})
            return self._load_loan(loan_id)
        res = self.idem.run(scope=principal.user_id, key=idempotency_key, endpoint=f"POST /loans/{loan_id}/repay",
                            payload={"loan_id": loan_id, "amount_minor": amount_minor}, fn=cmd)
        return res.body

    def mark_defaulted(self, principal: Principal, loan_id: str, reason: str) -> dict:
        principal.require("loan:approve")
        with self.db.transaction():
            loan = self._load_loan(loan_id)
            if not principal.is_org_member(loan["lender_org_id"]) and not principal.is_admin:
                raise UnauthorizedResourceAccess("not a member of the lending organization")
            LOAN_SM.assert_can(loan["state"], "DEFAULTED")
            self.db.execute("UPDATE loans SET state='DEFAULTED', version=version+1, updated_at=? WHERE id=?",
                            (self.ctx.now_iso(), loan_id))
            self.ctx.log_transition("loan", loan_id, loan["state"], "DEFAULTED", principal.user_id, reason)
        return self._load_loan(loan_id)
