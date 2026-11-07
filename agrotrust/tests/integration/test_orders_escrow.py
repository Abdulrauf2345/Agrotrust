import threading
import unittest

from agrotrust.integrations.payment_providers import MockPaymentProvider
from agrotrust.modules.escrow.service import EscrowService
from agrotrust.modules.ledger.service import LedgerService
from agrotrust.modules.marketplace.service import MarketplaceService
from agrotrust.modules.orders.service import OrderService
from agrotrust.modules.payments.idempotency import IdempotencyService
from agrotrust.modules.payments.service import PaymentService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import (Conflict, InsufficientFunds, NotFound, PermissionDenied, ValidationFailed)
from tests.helpers_ctx import CtxTestCase, insert_crop, insert_user, make_principal


class OrdersEscrowTests(CtxTestCase):
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
        self.crop = insert_crop(self.db, "MAIZE")
        insert_user(self.db, "farmer1", "11111")
        insert_user(self.db, "buyer1", "22222")
        insert_user(self.db, "admin1", "33333")
        from agrotrust.security.permissions import Principal
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.buyer = make_principal("buyer1", Role.BUYER)
        self.admin = Principal(user_id="admin1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        self.listing = self.market.create_listing(self.farmer, crop_id=self.crop, title="Fresh Maize",
                                                   quantity="100", unit="KG", price="500", state="Oyo", lga="Ibadan")

    def _fund_buyer_wallet(self, amt):
        p = self.pay.create_charge(self.buyer, amount_minor=amt)
        self.prov.simulate_success(p["reference"])
        self.pay.reconcile_charge(p["reference"])

    def _happy_order(self, qty="10"):
        o = self.orders.create(self.buyer, listing_id=self.listing["id"], quantity=qty)
        o = self.orders.confirm(self.farmer, o["id"])
        self._fund_buyer_wallet(o["total_minor"])
        o = self.orders.fund(self.buyer, o["id"])
        o = self.orders.prepare(self.farmer, o["id"])
        o = self.orders.dispatch(self.farmer, o["id"])
        return o

    def test_full_happy_path_releases_correctly(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        o = self.orders.inspect(self.buyer, o["id"], "10", "good quality")
        self.assertEqual(o["state"], "INSPECTED")
        res = self.orders.release(self.buyer, o["id"], idempotency_key="rel-key-0001")
        self.assertEqual(res["state"], "COMPLETED")
        fee = self.led.balance("SYS:FEE_REVENUE")
        seller_bal = self.led.wallet_balance("farmer1")
        self.assertEqual(fee, o["total_minor"] * self.settings.platform_fee_bps // 10_000)
        self.assertEqual(seller_bal + fee, o["total_minor"])
        self.assertTrue(self.led.trial_balance()["balanced"])
        listing = self.market.get(self.listing["id"])
        self.assertEqual(listing["quantity_available"], "90.000")

    def test_release_idempotent_and_exactly_once_concurrently(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        o = self.orders.inspect(self.buyer, o["id"], "10")
        out = []
        def go():
            try:
                out.append(self.orders.release(self.buyer, o["id"], idempotency_key="same-key-001"))
            except Conflict:
                out.append("conflict")
        ts = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        completed = [r for r in out if isinstance(r, dict) and r.get("state") == "COMPLETED"]
        self.assertEqual(len(completed), 8)   # all replays return the same completed result
        self.assertEqual(self.led.wallet_balance("farmer1"),
                         o["total_minor"] - self.led.balance("SYS:FEE_REVENUE"))

    def test_partial_acceptance_splits_correctly(self):
        o = self._happy_order(qty="10")
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        o = self.orders.inspect(self.buyer, o["id"], "6", "4kg spoiled")
        res = self.orders.release(self.buyer, o["id"], idempotency_key="rel-partial-1")
        self.assertEqual(res["state"], "COMPLETED")
        expected_gross = 6 * 500 * 100  # 6kg * 500 naira/kg in kobo... actually price is per-unit minor
        e = self.db.one("SELECT * FROM escrows WHERE order_id=?", (o["id"],))
        self.assertGreater(e["refunded_minor"], 0)
        self.assertTrue(self.led.trial_balance()["balanced"])
        self.assertEqual(e["seller_minor"] + e["fee_minor"] + e["refunded_minor"], e["amount_minor"])

    def test_buyer_cannot_release_before_inspection(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        with self.assertRaises(Conflict):
            self.orders.release(self.buyer, o["id"], idempotency_key="early-release")

    def test_seller_cannot_release_or_act_as_buyer(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        o = self.orders.inspect(self.buyer, o["id"], "10")
        with self.assertRaises((PermissionDenied, NotFound)):
            self.orders.release(self.farmer, o["id"], idempotency_key="seller-tries")

    def test_cross_tenant_cannot_see_or_act_on_order(self):
        insert_user(self.db, "stranger1", "44444")
        stranger = make_principal("stranger1", Role.BUYER)
        o = self.orders.create(self.buyer, listing_id=self.listing["id"], quantity="5")
        with self.assertRaises(NotFound):
            self.orders.get(stranger, o["id"])
        insert_user(self.db, "farmer2", "55555")
        other_farmer = make_principal("farmer2", Role.FARMER)
        with self.assertRaises(NotFound):
            self.orders.confirm(other_farmer, o["id"])

    def test_insufficient_funds_blocks_funding_stock_stays_reserved_until_cancel(self):
        o = self.orders.create(self.buyer, listing_id=self.listing["id"], quantity="10")
        o = self.orders.confirm(self.farmer, o["id"])
        with self.assertRaises(InsufficientFunds):
            self.orders.fund(self.buyer, o["id"])
        self.assertEqual(self.db.one("SELECT state FROM orders WHERE id=?", (o["id"],))["state"], "CONFIRMED")
        listing = self.market.get(self.listing["id"])
        self.assertEqual(listing["quantity_available"], "90.000")   # still reserved, not refunded
        self.orders.cancel(self.buyer, o["id"], "cannot fund")
        listing = self.market.get(self.listing["id"])
        self.assertEqual(listing["quantity_available"], "100.000")

    def test_cancel_after_funding_refunds_buyer(self):
        o = self.orders.create(self.buyer, listing_id=self.listing["id"], quantity="10")
        o = self.orders.confirm(self.farmer, o["id"])
        self._fund_buyer_wallet(o["total_minor"])
        o = self.orders.fund(self.buyer, o["id"])
        self.orders.cancel(self.buyer, o["id"], "seller unresponsive")
        self.assertEqual(self.led.wallet_balance("buyer1"), o["total_minor"])
        self.assertEqual(self.market.get(self.listing["id"])["quantity_available"], "100.000")
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_dispute_flow_admin_split(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        d = self.orders.open_dispute(self.buyer, o["id"], "goods arrived damaged and inedible")
        with self.assertRaises(Conflict):
            self.orders.open_dispute(self.buyer, o["id"], "again same thing happening")
        seller_amt = o["total_minor"] // 2
        buyer_amt = o["total_minor"] - seller_amt
        self.orders.resolve_dispute(self.admin, d["id"], seller_amount_minor=seller_amt,
                                    buyer_amount_minor=buyer_amt, resolution="50/50 split after review")
        self.assertEqual(self.db.one("SELECT state FROM orders WHERE id=?", (o["id"],))["state"], "COMPLETED")
        self.assertTrue(self.led.trial_balance()["balanced"])
        with self.assertRaises(Conflict):
            self.orders.resolve_dispute(self.admin, d["id"], seller_amount_minor=0, buyer_amount_minor=o["total_minor"],
                                        resolution="try again")

    def test_list_disputes_scoped_to_order_parties_and_admin(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        d = self.orders.open_dispute(self.buyer, o["id"], "goods arrived damaged and inedible")
        insert_user(self.db, "stranger1", "99999")
        stranger = make_principal("stranger1", Role.BUYER)
        self.assertEqual([x["id"] for x in self.orders.list_disputes(self.buyer)], [d["id"]])
        self.assertEqual([x["id"] for x in self.orders.list_disputes(self.farmer)], [d["id"]])
        self.assertEqual(self.orders.list_disputes(stranger), [])
        self.assertEqual([x["id"] for x in self.orders.list_disputes(self.admin)], [d["id"]])
        self.assertEqual(self.orders.get_dispute(self.buyer, d["id"])["id"], d["id"])
        with self.assertRaises(NotFound):
            self.orders.get_dispute(stranger, d["id"])

    def test_state_machine_rejects_illegal_jump(self):
        o = self.orders.create(self.buyer, listing_id=self.listing["id"], quantity="5")
        with self.assertRaises(Exception):
            self.orders.mark_delivered(self.farmer, o["id"], "5")   # CREATED -> DELIVERED illegal

    def test_auto_release_after_inactivity(self):
        o = self._happy_order()
        o = self.orders.mark_delivered(self.farmer, o["id"], "10")
        self.clock.advance(hours=73)
        n = self.orders.auto_release_stale(after_hours=72)
        self.assertEqual(n, 1)
        self.assertEqual(self.db.one("SELECT state FROM orders WHERE id=?", (o["id"],))["state"], "COMPLETED")
        self.assertTrue(self.led.trial_balance()["balanced"])


if __name__ == "__main__":
    unittest.main()
