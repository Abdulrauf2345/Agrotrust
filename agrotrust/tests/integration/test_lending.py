import unittest

from agrotrust.modules.farms.service import FarmService
from agrotrust.modules.ledger.service import LedgerService, wallet_code, C, D, BANK
from agrotrust.modules.lending.service import LendingService
from agrotrust.modules.organizations.service import OrganizationService
from agrotrust.modules.payments.idempotency import IdempotencyService
from agrotrust.security.permissions import Principal, ROLE_PERMISSIONS, Role
from agrotrust.shared.errors import Conflict, LoanNotEligible, UnauthorizedResourceAccess, ValidationFailed
from tests.helpers_ctx import CtxTestCase, insert_user, make_principal

IBADAN = (7.3775, 3.9470)


class LendingTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.led = LedgerService(self.ctx)
        self.led.ensure_system_accounts()
        self.idem = IdempotencyService(self.db, self.clock)
        self.lend = LendingService(self.ctx, self.led, self.idem)
        self.farms = FarmService(self.ctx)
        insert_user(self.db, "lender1", "11111")
        insert_user(self.db, "farmer1", "22222")
        lender_p = make_principal("lender1", Role.LENDER)
        org = OrganizationService(self.ctx).create(lender_p, name="AgroCredit", type="LENDER", state="Oyo")
        self.org_id = org["id"]
        self.lender = Principal(user_id="lender1", roles=frozenset({Role.LENDER}),
                                permissions=frozenset(ROLE_PERMISSIONS[Role.LENDER]), org_roles={self.org_id: "ADMIN"})
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.product = self.lend.create_product(self.lender, lender_org_id=self.org_id, name="Seed Loan",
                                                min_amount_minor=10_000_00, max_amount_minor=500_000_00,
                                                min_term_months=3, max_term_months=12, annual_rate_bps=1800,
                                                late_fee_bps=200, min_credit_score=0, requires_verified_farm=False)

    def _verify_farm(self):
        f = self.farms.create(self.farmer, name="F1", state="Oyo", lga="Ibadan", size_hectares=1, lat=IBADAN[0], lon=IBADAN[1])
        with self.db.transaction():
            self.db.execute("UPDATE farms SET verification_status='VERIFIED' WHERE id=?", (f["id"],))
        return f

    def test_scoring_is_explainable_and_deterministic(self):
        a = self.lend.assess("farmer1")
        self.assertEqual(a["risk_grade"], "D")   # base score only, no history
        self._verify_farm()
        b = self.lend.assess("farmer1")
        self.assertGreater(b["score"], a["score"])
        import json
        self.assertIn("verified_farm", json.loads(b["factors"]))

    def test_apply_and_auto_reject_eligibility(self):
        strict_product = self.lend.create_product(self.lender, lender_org_id=self.org_id, name="Strict Loan",
                                                   min_amount_minor=10_000_00, max_amount_minor=500_000_00,
                                                   min_term_months=3, max_term_months=12, annual_rate_bps=1800,
                                                   min_credit_score=800, requires_verified_farm=True)
        app = self.lend.apply(self.farmer, product_id=strict_product["id"], amount_minor=100_000_00, term_months=6)
        self.assertEqual(app["state"], "ASSESSMENT")
        with self.assertRaises(LoanNotEligible):
            self.lend.decide(self.lender, app["id"], approve=True, reason="looks fine to me")
        d = self.lend.decide(self.lender, app["id"], approve=False, reason="score too low, farm unverified")
        self.assertEqual(d["state"], "REJECTED")

    def test_apply_amount_out_of_range(self):
        with self.assertRaises(ValidationFailed):
            self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=1, term_months=6)

    def test_cannot_double_apply(self):
        self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=100_000_00, term_months=6)
        with self.assertRaises(Conflict):
            self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=50_000_00, term_months=6)

    def test_full_disbursement_and_amortization_sums_exactly(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=120_000_00, term_months=6)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="good applicant")
        self.assertEqual(app["state"], "APPROVED")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-001")
        self.assertEqual(loan["state"], "ACTIVE")
        self.assertEqual(self.led.wallet_balance("farmer1"), 120_000_00)
        sched = self.lend.schedule(self.farmer, loan["id"])
        self.assertEqual(len(sched), 6)
        total_principal = sum(r["principal_due_minor"] for r in sched)
        self.assertEqual(total_principal, 120_000_00)   # exact, no rounding drift
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_disburse_idempotent(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=100_000_00, term_months=3)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        a = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        b = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.led.wallet_balance("farmer1"), 100_000_00)

    def test_repayment_full_schedule_completes_loan(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=120_000_00, term_months=3)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        # top up the wallet with enough extra to cover interest on top of the disbursed principal
        self.led.post(reference="topup-full", entry_type="DEPOSIT", description="fund wallet to cover interest",
                     lines=[D(BANK, 20_000_00), C(wallet_code("farmer1"), 20_000_00)])
        sched = self.lend.schedule(self.farmer, loan["id"])
        for i, row in enumerate(sched):
            total_due = (row["principal_due_minor"] - row["principal_paid_minor"]) + \
                       (row["interest_due_minor"] - row["interest_paid_minor"])
            self.lend.repay(self.farmer, loan["id"], total_due, idempotency_key=f"pay-key-{i:03d}")
        loan = self.lend.get_loan(self.farmer, loan["id"])
        self.assertEqual(loan["state"], "COMPLETED")
        self.assertEqual(self.led.balance(LOAN_RECEIVABLE := "SYS:LOAN_RECEIVABLE"), 0)
        self.assertGreater(self.led.balance("SYS:INTEREST_REVENUE"), 0)
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_repay_more_than_outstanding_rejected(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=100_000_00, term_months=3)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        with self.assertRaises(ValidationFailed):
            self.lend.repay(self.farmer, loan["id"], 999_999_999, idempotency_key="over-key1")

    def test_repay_idempotent(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=100_000_00, term_months=3)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        self.led.post(reference="topup", entry_type="DEPOSIT", description="fund wallet for repay test",
                     lines=[D(BANK, 50_000_00), C(wallet_code("farmer1"), 50_000_00)])
        a = self.lend.repay(self.farmer, loan["id"], 30_000_00, idempotency_key="pay-key-x1")
        b = self.lend.repay(self.farmer, loan["id"], 30_000_00, idempotency_key="pay-key-x1")
        self.assertEqual(a["updated_at"], b["updated_at"])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM repayments WHERE loan_id=?", (loan["id"],)), 1)

    def test_only_borrower_can_repay_own_loan(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=100_000_00, term_months=3)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        insert_user(self.db, "farmer2", "33333")
        farmer2 = make_principal("farmer2", Role.FARMER)
        with self.assertRaises(UnauthorizedResourceAccess):
            self.lend.repay(farmer2, loan["id"], 1000, idempotency_key="hack-key1")

    def test_mark_overdue_accrues_penalty(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=120_000_00, term_months=3)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-key1")
        self.clock.advance(days=31)
        n = self.lend.mark_overdue()
        self.assertGreaterEqual(n, 1)
        sched = self.lend.schedule(self.farmer, loan["id"])
        self.assertEqual(sched[0]["status"], "OVERDUE")
        self.assertGreater(sched[0]["penalty_minor"], 0)

    def test_list_products_is_visible_to_any_borrower(self):
        products = self.lend.list_products()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["id"], self.product["id"])
        scoped = self.lend.list_products(self.org_id)
        self.assertEqual(len(scoped), 1)
        self.assertEqual(self.lend.list_products("some-other-org-id"), [])

    def test_list_applications_scoped_to_borrower_and_lender(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=50_000_00, term_months=6)
        insert_user(self.db, "farmer2", "33333")
        farmer2 = make_principal("farmer2", Role.FARMER)
        mine = self.lend.list_applications(self.farmer)
        self.assertEqual([a["id"] for a in mine], [app["id"]])
        self.assertEqual(self.lend.list_applications(farmer2), [])
        lender_view = self.lend.list_applications(self.lender)
        self.assertEqual([a["id"] for a in lender_view], [app["id"]])

    def test_list_loans_scoped_to_borrower_and_lender(self):
        app = self.lend.apply(self.farmer, product_id=self.product["id"], amount_minor=50_000_00, term_months=6)
        app = self.lend.decide(self.lender, app["id"], approve=True, reason="approved based on assessment")
        loan = self.lend.disburse(self.lender, app["id"], idempotency_key="disb-list1")
        insert_user(self.db, "farmer2", "33333")
        farmer2 = make_principal("farmer2", Role.FARMER)
        self.assertEqual([loan_["id"] for loan_ in self.lend.list_loans(self.farmer)], [loan["id"]])
        self.assertEqual(self.lend.list_loans(farmer2), [])
        self.assertEqual([loan_["id"] for loan_ in self.lend.list_loans(self.lender)], [loan["id"]])


if __name__ == "__main__":
    unittest.main()
