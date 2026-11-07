import json
import threading
import unittest

from agrotrust.integrations.payment_providers import MockPaymentProvider
from agrotrust.modules.ledger.service import LedgerService
from agrotrust.modules.payments.service import PaymentService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import (PaymentVerificationFailed, PermissionDenied, ValidationFailed,
                                     WebhookSignatureInvalid)
from tests.helpers_ctx import CtxTestCase, insert_user, make_principal


class PaymentTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.led = LedgerService(self.ctx)
        self.led.ensure_system_accounts()
        self.prov = MockPaymentProvider(self.settings.webhook_secret)
        self.pay = PaymentService(self.ctx, self.led, self.prov)
        insert_user(self.db, "buyer1", "11111")
        insert_user(self.db, "farmer1", "22222")
        self.buyer = make_principal("buyer1", Role.BUYER)
        self.farmer = make_principal("farmer1", Role.FARMER)

    def _charge(self, amt=50_000):
        p = self.pay.create_charge(self.buyer, amount_minor=amt)
        self.prov.simulate_success(p["reference"])
        return p

    def test_permission_and_validation(self):
        with self.assertRaises(PermissionDenied):
            self.pay.create_charge(self.farmer, amount_minor=100)
        for bad in (0, -5, 1.5, True):
            with self.assertRaises(ValidationFailed):
                self.pay.create_charge(self.buyer, amount_minor=bad)

    def test_webhook_credits_wallet_once(self):
        p = self._charge()
        body, sig = self.prov.webhook("charge.success", "evt1", p["reference"])
        self.assertEqual(self.pay.handle_webhook(body, sig)["status"], "succeeded")
        self.assertEqual(self.led.wallet_balance("buyer1"), 50_000)
        self.assertEqual(self.pay.handle_webhook(body, sig)["status"], "duplicate")
        # same payment via a different event id must not double-credit either
        body2, sig2 = self.prov.webhook("charge.success", "evt2", p["reference"])
        self.assertEqual(self.pay.handle_webhook(body2, sig2)["status"], "already_succeeded")
        self.assertEqual(self.led.wallet_balance("buyer1"), 50_000)
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_bad_signature_rejected_no_side_effects(self):
        p = self._charge()
        body, _ = self.prov.webhook("charge.success", "evt1", p["reference"])
        with self.assertRaises(WebhookSignatureInvalid):
            self.pay.handle_webhook(body, "deadbeef")
        with self.assertRaises(WebhookSignatureInvalid):
            self.pay.handle_webhook(body + b" ", self.prov.sign(body))   # body tampered after signing
        self.assertEqual(self.led.wallet_balance("buyer1"), 0)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM webhook_events"), 0)

    def test_provider_says_pending_or_failed_no_credit(self):
        p = self.pay.create_charge(self.buyer, amount_minor=1000)
        body, sig = self.prov.webhook("charge.success", "e1", p["reference"])   # forged-but-signed claim
        self.assertEqual(self.pay.handle_webhook(body, sig)["status"], "still_pending")
        self.assertEqual(self.led.wallet_balance("buyer1"), 0)
        self.prov.simulate_failure(p["reference"])
        body, sig = self.prov.webhook("charge.success", "e2", p["reference"])
        self.assertEqual(self.pay.handle_webhook(body, sig)["status"], "failed")

    def test_amount_mismatch_never_credits(self):
        p = self.pay.create_charge(self.buyer, amount_minor=50_000)
        self.prov.simulate_success(p["reference"], amount_minor=100)
        body, sig = self.prov.webhook("charge.success", "e1", p["reference"])
        self.assertEqual(self.pay.handle_webhook(body, sig)["status"], "amount_mismatch")
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM outbox WHERE event_type='payment.amount_mismatch'"), 1)
        self.assertEqual(self.led.wallet_balance("buyer1"), 0)
        row = self.db.one("SELECT status, failure_reason FROM payments WHERE id=?", (p["id"],))
        self.assertEqual(row["status"], "FAILED")

    def test_concurrent_duplicate_webhooks_credit_once(self):
        p = self._charge()
        body, sig = self.prov.webhook("charge.success", "evtC", p["reference"])
        out = []
        ts = [threading.Thread(target=lambda: out.append(self.pay.handle_webhook(body, sig)["status"]))
              for _ in range(10)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out.count("succeeded"), 1)
        self.assertEqual(self.led.wallet_balance("buyer1"), 50_000)

    def test_hook_failure_rolls_back_credit(self):
        p = self._charge()
        def boom(_): raise RuntimeError("escrow funding failed")
        self.pay.on_charge_settled(boom)
        body, sig = self.prov.webhook("charge.success", "e1", p["reference"])
        with self.assertRaises(RuntimeError):
            self.pay.handle_webhook(body, sig)
        self.assertEqual(self.led.wallet_balance("buyer1"), 0)
        self.assertEqual(self.db.one("SELECT status FROM payments WHERE id=?", (p["id"],))["status"], "PENDING")
        self.pay._settle_hooks.clear()
        self.assertEqual(self.pay.handle_webhook(body, sig)["status"], "succeeded")   # redelivery recovers

    def test_reconcile_recovers_missed_webhook(self):
        p = self._charge()
        self.assertEqual(self.pay.reconcile_charge(p["reference"])["status"], "succeeded")
        self.assertEqual(self.pay.reconcile_charge(p["reference"])["status"], "already_succeeded")
        self.assertEqual(self.led.wallet_balance("buyer1"), 50_000)

    def _fund(self, amt):
        p = self._charge(amt)
        self.pay.reconcile_charge(p["reference"])

    DEST = {"account_number": "0123456789", "bank_code": "058"}

    def test_payout_success_and_idempotent(self):
        self._fund(10_000)
        a = self.pay.request_payout(self.buyer, amount_minor=4_000, destination=self.DEST, client_ref="wd-0001")
        b = self.pay.request_payout(self.buyer, amount_minor=4_000, destination=self.DEST, client_ref="wd-0001")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["status"], "SUCCEEDED")
        self.assertEqual(self.led.wallet_balance("buyer1"), 6_000)
        self.assertEqual(len(self.prov.payouts), 1)
        self.assertNotIn("0123456789", a["meta"])   # only last4 stored
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_payout_overdraft_blocked(self):
        from agrotrust.shared.errors import InsufficientFunds
        self._fund(1_000)
        with self.assertRaises(InsufficientFunds):
            self.pay.request_payout(self.buyer, amount_minor=1_001, destination=self.DEST, client_ref="wd-0002")
        self.assertEqual(self.led.wallet_balance("buyer1"), 1_000)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM payments WHERE kind='PAYOUT'"), 0)

    def test_payout_failure_returns_funds(self):
        self._fund(10_000)
        self.prov.fail_next_payouts(1)
        r = self.pay.request_payout(self.buyer, amount_minor=4_000, destination=self.DEST, client_ref="wd-0003")
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(self.led.wallet_balance("buyer1"), 10_000)

    def test_payout_provider_outage_keeps_funds_reserved_then_retry(self):
        self._fund(10_000)
        self.prov.outage(1)
        r = self.pay.request_payout(self.buyer, amount_minor=4_000, destination=self.DEST, client_ref="wd-0004")
        self.assertEqual(r["status"], "PENDING")
        self.assertEqual(self.led.wallet_balance("buyer1"), 6_000)   # reserved, cannot be double spent
        r = self.pay.retry_payout(r["id"], self.DEST)
        self.assertEqual(r["status"], "SUCCEEDED")
        self.assertEqual(self.led.wallet_balance("buyer1"), 6_000)
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_concurrent_payouts_cannot_overdraw(self):
        from agrotrust.shared.errors import InsufficientFunds
        self._fund(1_000)
        out = []
        def go(i):
            try:
                self.pay.request_payout(self.buyer, amount_minor=400, destination=self.DEST, client_ref=f"wd-c{i:04d}")
                out.append("ok")
            except InsufficientFunds:
                out.append("no")
        ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out.count("ok"), 2)
        self.assertEqual(self.led.wallet_balance("buyer1"), 200)


if __name__ == "__main__":
    unittest.main()
