import unittest

from agrotrust.modules.analytics.service import AnalyticsService
from agrotrust.modules.escrow.service import EscrowService
from agrotrust.modules.ledger.service import LedgerService
from agrotrust.modules.marketplace.service import MarketplaceService
from agrotrust.modules.orders.service import OrderService
from agrotrust.modules.payments.idempotency import IdempotencyService
from agrotrust.modules.payments.service import PaymentService
from agrotrust.integrations.payment_providers import MockPaymentProvider
from agrotrust.security.permissions import Principal, ROLE_PERMISSIONS, Role
from agrotrust.shared.errors import PermissionDenied, UnauthorizedResourceAccess
from tests.helpers_ctx import CtxTestCase, insert_crop, insert_user, make_principal


class AnalyticsTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.led = LedgerService(self.ctx)
        self.led.ensure_system_accounts()
        self.market = MarketplaceService(self.ctx)
        self.escrow = EscrowService(self.ctx, self.led)
        self.idem = IdempotencyService(self.db, self.clock)
        self.orders = OrderService(self.ctx, self.market, self.escrow, self.idem)
        self.prov = MockPaymentProvider(self.settings.webhook_secret)
        self.pay = PaymentService(self.ctx, self.led, self.prov)
        self.an = AnalyticsService(self.ctx)
        crop = insert_crop(self.db, "MAIZE")
        insert_user(self.db, "farmer1", "11111")
        insert_user(self.db, "buyer1", "22222")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.buyer = make_principal("buyer1", Role.BUYER)
        self.admin = Principal(user_id="farmer1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        listing = self.market.create_listing(self.farmer, crop_id=crop, title="Maize", quantity="100", unit="KG",
                                             price="500", state="Oyo", lga="Ibadan")
        o = self.orders.create(self.buyer, listing_id=listing["id"], quantity="10")
        o = self.orders.confirm(self.farmer, o["id"])
        p = self.pay.create_charge(self.buyer, amount_minor=o["total_minor"])
        self.prov.simulate_success(p["reference"])
        self.pay.reconcile_charge(p["reference"])
        o = self.orders.fund(self.buyer, o["id"])
        o = self.orders.prepare(self.farmer, o["id"])
        o = self.orders.dispatch(self.farmer, o["id"])
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        o = self.orders.inspect(self.buyer, o["id"], "10")
        self.orders.release(self.buyer, o["id"], idempotency_key="release-key1")

    def test_farmer_dashboard_own(self):
        d = self.an.farmer_dashboard(self.farmer)
        self.assertEqual(d["completed_sales"], 1)
        self.assertGreater(d["sales_revenue_minor"], 0)

    def test_buyer_dashboard(self):
        d = self.an.buyer_dashboard(self.buyer)
        self.assertEqual(d["orders_total"], 1)
        self.assertEqual(d["orders_completed"], 1)

    def test_farmer_cannot_see_platform_overview(self):
        with self.assertRaises(PermissionDenied):
            self.an.platform_overview(self.farmer)

    def test_farmer_cannot_view_others_dashboard_without_permission(self):
        insert_user(self.db, "farmer2", "33333")
        farmer2 = make_principal("farmer2", Role.FARMER)
        with self.assertRaises(PermissionDenied):
            self.an.farmer_dashboard(farmer2, farmer_id="farmer1")

    def test_platform_overview_admin(self):
        d = self.an.platform_overview(self.admin)
        self.assertGreaterEqual(d["farms_total"], 0)
        self.assertGreater(d["gross_merchandise_value_minor"], 0)
        self.assertGreater(d["platform_fee_revenue_minor"], 0)

    def test_ops_queue_depths_gated(self):
        with self.assertRaises(PermissionDenied):
            self.an.ops_queue_depths(self.buyer)
        d = self.an.ops_queue_depths(self.admin)
        self.assertIn("pending_jobs", d)


if __name__ == "__main__":
    unittest.main()
