"""Analytics (spec section 46): read-only reporting views, each gated by its own permission so a
farmer can never see platform-wide financials and a lender can never see another lender's book.
"""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared.context import Context


class AnalyticsService:
    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    def farmer_dashboard(self, principal: Principal, farmer_id: str | None = None) -> dict:
        uid = farmer_id or principal.user_id
        if uid != principal.user_id:
            principal.require("analytics:farmer")
            if not principal.is_admin:
                principal.require("farm:read_any")
        farms = self.db.one("SELECT COUNT(*) AS n, SUM(CASE WHEN verification_status='VERIFIED' THEN 1 ELSE 0 END)"
                            " AS verified FROM farms WHERE owner_user_id=?", (uid,))
        sales = self.db.one("SELECT COUNT(*) AS n, COALESCE(SUM(total_minor),0) AS revenue_minor FROM orders"
                            " WHERE seller_id=? AND state='COMPLETED'", (uid,))
        active_listings = self.db.scalar("SELECT COUNT(*) FROM listings WHERE seller_id=? AND status='ACTIVE'", (uid,))
        loans = self.db.one("SELECT COUNT(*) AS n, COALESCE(SUM(principal_minor),0) AS principal_minor FROM loans"
                            " WHERE borrower_id=? AND state IN ('ACTIVE','REPAYING')", (uid,))
        return {"farms_total": farms["n"], "farms_verified": farms["verified"] or 0,
                "completed_sales": sales["n"], "sales_revenue_minor": sales["revenue_minor"],
                "active_listings": active_listings, "active_loans": loans["n"],
                "active_loan_principal_minor": loans["principal_minor"]}

    def buyer_dashboard(self, principal: Principal) -> dict:
        principal.require("analytics:buyer")
        orders = self.db.one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_minor),0) AS spend_minor,"
            " SUM(CASE WHEN state='COMPLETED' THEN 1 ELSE 0 END) AS completed,"
            " SUM(CASE WHEN state='DISPUTED' THEN 1 ELSE 0 END) AS disputed"
            " FROM orders WHERE buyer_id=?", (principal.user_id,))
        return {"orders_total": orders["n"], "orders_completed": orders["completed"] or 0,
                "orders_disputed": orders["disputed"] or 0, "total_spend_minor": orders["spend_minor"]}

    def lender_portfolio(self, principal: Principal, lender_org_id: str) -> dict:
        principal.require("loan:read_portfolio")
        if not principal.is_org_member(lender_org_id) and not principal.is_admin:
            from ...shared.errors import UnauthorizedResourceAccess
            raise UnauthorizedResourceAccess("not a member of that lender organization")
        rows = self.db.one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(principal_minor),0) AS disbursed_minor,"
            " SUM(CASE WHEN state IN ('ACTIVE','REPAYING') THEN 1 ELSE 0 END) AS open_loans,"
            " SUM(CASE WHEN state='DEFAULTED' THEN 1 ELSE 0 END) AS defaulted,"
            " SUM(CASE WHEN state='COMPLETED' THEN 1 ELSE 0 END) AS completed"
            " FROM loans WHERE lender_org_id=?", (lender_org_id,))
        outstanding = self.db.one(
            "SELECT COALESCE(SUM(s.principal_due_minor - s.principal_paid_minor),0) AS principal_outstanding,"
            " COALESCE(SUM(s.interest_due_minor - s.interest_paid_minor),0) AS interest_outstanding"
            " FROM repayment_schedule s JOIN loans l ON l.id=s.loan_id WHERE l.lender_org_id=?"
            " AND s.status != 'PAID'", (lender_org_id,))
        default_rate = (rows["defaulted"] or 0) / rows["n"] if rows["n"] else 0.0
        return {"loans_total": rows["n"], "loans_open": rows["open_loans"] or 0, "loans_defaulted": rows["defaulted"] or 0,
                "loans_completed": rows["completed"] or 0, "total_disbursed_minor": rows["disbursed_minor"],
                "principal_outstanding_minor": outstanding["principal_outstanding"],
                "interest_outstanding_minor": outstanding["interest_outstanding"], "default_rate": round(default_rate, 4)}

    def platform_overview(self, principal: Principal) -> dict:
        principal.require("analytics:platform")
        users = self.db.scalar("SELECT COUNT(*) FROM users WHERE status='ACTIVE'")
        farms = self.db.one("SELECT COUNT(*) AS n, SUM(CASE WHEN verification_status='VERIFIED' THEN 1 ELSE 0 END)"
                            " AS verified FROM farms")
        gmv = self.db.scalar("SELECT COALESCE(SUM(total_minor),0) FROM orders WHERE state='COMPLETED'")
        fee_revenue = self.db.scalar("SELECT COALESCE(SUM(amount_minor),0) FROM journal_lines l"
                                     " JOIN ledger_accounts a ON a.id=l.account_id"
                                     " WHERE a.code='SYS:FEE_REVENUE' AND l.side='C'")
        disputes_open = self.db.scalar("SELECT COUNT(*) FROM disputes WHERE state='OPEN'")
        return {"active_users": users, "farms_total": farms["n"], "farms_verified": farms["verified"] or 0,
                "gross_merchandise_value_minor": gmv, "platform_fee_revenue_minor": fee_revenue or 0,
                "open_disputes": disputes_open}

    def ops_queue_depths(self, principal: Principal) -> dict:
        """Operational visibility: how much backlog exists across async workers, for on-call/ops."""
        principal.require("analytics:ops")
        return {
            "pending_notifications": self.db.scalar("SELECT COUNT(*) FROM notifications WHERE status='PENDING'"),
            "pending_outbox_events": self.db.scalar("SELECT COUNT(*) FROM outbox WHERE published_at IS NULL"),
            "pending_jobs": self.db.scalar("SELECT COUNT(*) FROM jobs WHERE status='PENDING'"),
            "open_disputes": self.db.scalar("SELECT COUNT(*) FROM disputes WHERE state='OPEN'"),
            "overdue_installments": self.db.scalar("SELECT COUNT(*) FROM repayment_schedule WHERE status='OVERDUE'"),
        }
