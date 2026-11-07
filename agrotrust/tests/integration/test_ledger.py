import threading
import unittest

from agrotrust.modules.ledger.service import (BANK, ESCROW_HOLD, FEE_REVENUE, C, D, LedgerService, wallet_code)
from agrotrust.shared.errors import Conflict, InsufficientFunds, UnbalancedJournal, ValidationFailed
from tests.helpers_ctx import CtxTestCase


class LedgerTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.led = LedgerService(self.ctx)
        self.led.ensure_system_accounts()
        with self.db.transaction():
            for u in ("u1", "u2"):
                self.db.execute("INSERT INTO users(id,phone,full_name,password_hash,status,created_at,updated_at)"
                                " VALUES (?,?,?,?,?,?,?)", (u, "+234800000000" + u[-1], u, "x", "ACTIVE", "t", "t"))
        self.led.ensure_wallet("u1")
        self.led.ensure_wallet("u2")

    def _fund(self, ref="f1", amt=10_000):
        return self.led.post(reference=ref, entry_type="DEPOSIT", description="d",
                             lines=[D(BANK, amt), C(wallet_code("u1"), amt)])

    def test_post_and_balance(self):
        self._fund()
        self.assertEqual(self.led.wallet_balance("u1"), 10_000)
        self.assertEqual(self.led.balance(BANK), 10_000)
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_unbalanced_and_invalid_rejected(self):
        with self.assertRaises(UnbalancedJournal):
            self.led.post(reference="x1", entry_type="T", description="d", lines=[D(BANK, 5), C(wallet_code("u1"), 4)])
        with self.assertRaises(ValidationFailed):
            self.led.post(reference="x2", entry_type="T", description="d", lines=[D(BANK, 0), C(wallet_code("u1"), 0)])
        with self.assertRaises(ValidationFailed):
            self.led.post(reference="x3", entry_type="T", description="d", lines=[D(BANK, 5)])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM journal_entries"), 0)

    def test_reference_idempotent(self):
        a = self._fund("dup")
        b = self._fund("dup")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.led.wallet_balance("u1"), 10_000)
        with self.assertRaises(Conflict):
            self._fund("dup", 999)

    def test_overdraft_blocked_and_rolled_back(self):
        self._fund()
        with self.assertRaises(InsufficientFunds):
            self.led.post(reference="w1", entry_type="PAYOUT", description="d",
                          lines=[D(wallet_code("u1"), 10_001), C(BANK, 10_001)])
        self.assertEqual(self.led.wallet_balance("u1"), 10_000)
        self.assertIsNone(self.db.one("SELECT 1 FROM journal_entries WHERE reference='w1'"))

    def test_reverse_once_only(self):
        e = self._fund()
        self.led.reverse(e["id"], reason="mistake")
        self.assertEqual(self.led.wallet_balance("u1"), 0)
        with self.assertRaises(Conflict):
            self.led.reverse(e["id"], reason="again")
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_immutable(self):
        e = self._fund()
        import sqlite3
        with self.db.transaction():
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.execute("UPDATE journal_lines SET amount_minor=1 WHERE entry_id=?", (e["id"],))
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.execute("DELETE FROM journal_entries WHERE id=?", (e["id"],))

    def test_concurrent_withdrawals_never_overdraw(self):
        self._fund(amt=1000)
        results = []

        def w(i):
            try:
                self.led.post(reference=f"cw{i}", entry_type="PAYOUT", description="d",
                              lines=[D(wallet_code("u1"), 300), C(BANK, 300)])
                results.append("ok")
            except InsufficientFunds:
                results.append("insufficient")
        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count("ok"), 3)
        self.assertEqual(self.led.wallet_balance("u1"), 100)
        self.assertTrue(self.led.trial_balance()["balanced"])


if __name__ == "__main__":
    unittest.main()
