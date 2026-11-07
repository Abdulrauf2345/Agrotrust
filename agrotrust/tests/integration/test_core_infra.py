import sqlite3
import threading
import unittest

from agrotrust.events.outbox import InProcessBus, Outbox, OutboxPublisher
from agrotrust.modules.audit.service import AuditService
from agrotrust.modules.payments.idempotency import IdempotencyService
from agrotrust.shared.errors import (DuplicateIdempotencyKey, IdempotencyRequestInProgress, ValidationFailed)
from agrotrust.workers.queue import DbJobQueue
from tests.helpers import DbTestCase


class AuditTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.audit = AuditService(self.db, self.clock)

    def _rec(self, n):
        with self.db.transaction():
            self.audit.record(actor_id="u1", action=f"act{n}", resource_type="farm", resource_id="f1",
                              old={"s": "A"}, new={"s": "B", "password": "hunter2"})

    def test_chain_valid_and_redacts(self):
        for i in range(5):
            self._rec(i)
        self.assertEqual(self.audit.verify_chain(), (True, None))
        row = self.audit.query(limit=1)[0]
        self.assertNotIn("hunter2", row["new_state"])
        self.assertIn("[REDACTED]", row["new_state"])

    def test_requires_transaction(self):
        with self.assertRaises(RuntimeError):
            self.audit.record(actor_id="u", action="x", resource_type="y")

    def test_update_and_delete_blocked_by_db(self):
        self._rec(1)
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.transaction():
                self.db.execute("UPDATE audit_log SET action='hacked'")
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.transaction():
                self.db.execute("DELETE FROM audit_log")

    def test_tampering_detected_even_if_triggers_dropped(self):
        for i in range(4):
            self._rec(i)
        raw = sqlite3.connect(self.db_path)  # attacker with raw DB access
        raw.execute("DROP TRIGGER audit_log_no_update")
        raw.execute("UPDATE audit_log SET actor_id='someone-else' WHERE id=2")
        raw.commit(); raw.close()
        ok, bad_id = self.audit.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(bad_id, 2)

    def test_rollback_leaves_no_audit_row(self):
        with self.assertRaises(ValueError):
            with self.db.transaction():
                self.audit.record(actor_id="u", action="x", resource_type="y")
                raise ValueError
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit_log"), 0)


class OutboxTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.outbox = Outbox(self.db, self.clock)
        self.bus = InProcessBus(self.db, self.clock)
        self.pub = OutboxPublisher(self.db, self.clock, self.bus)
        self.effects = []

    def test_rollback_means_no_event(self):
        """Business change and event are atomic: failed tx => neither exists."""
        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                self.db.execute("INSERT INTO crops(id, code, name) VALUES ('c1','MAIZE','Maize')")
                self.outbox.publish("CropCreated", "crop", "c1", {})
                raise RuntimeError("boom after publishing")
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM crops"), 0)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM outbox"), 0)

    def test_commit_means_event_is_durable_and_delivered(self):
        self.bus.subscribe("CropCreated", "h1", lambda e: self.effects.append(e.aggregate_id))
        with self.db.transaction():
            self.db.execute("INSERT INTO crops(id, code, name) VALUES ('c1','MAIZE','Maize')")
            self.outbox.publish("CropCreated", "crop", "c1", {"x": 1})
        self.assertEqual(self.pub.pending_count(), 1)          # durable even before any broker exists
        self.assertEqual(self.pub.publish_pending(), {"published": 1, "failed": 0})
        self.assertEqual(self.effects, ["c1"])
        self.assertEqual(self.pub.pending_count(), 0)

    def test_broker_failure_is_not_silent_and_is_retried(self):
        state = {"fail": True}

        def flaky(e):
            if state["fail"]:
                raise ConnectionError("broker down")
            self.effects.append(e.event_id)

        self.bus.subscribe("T", "flaky", flaky)
        with self.db.transaction():
            self.outbox.publish("T", "agg", "1", {})
        self.assertEqual(self.pub.publish_pending(), {"published": 0, "failed": 1})
        self.assertEqual(self.pub.pending_count(), 1)          # still pending, not lost
        row = self.db.one("SELECT * FROM outbox")
        self.assertIn("broker down", row["last_error"])
        state["fail"] = False
        self.assertEqual(self.pub.publish_pending(), {"published": 1, "failed": 0})
        self.assertEqual(len(self.effects), 1)

    def test_consumer_dedupes_redelivery(self):
        """Two workers (or a crash between send and mark) => handler effect applied once."""
        self.bus.subscribe("T", "h", lambda e: self.effects.append(e.event_id))
        with self.db.transaction():
            self.outbox.publish("T", "agg", "1", {})
        row = self.db.one("SELECT * FROM outbox")
        from agrotrust.events.outbox import DomainEvent
        import json
        ev = DomainEvent(row["event_id"], row["event_type"], "agg", "1", json.loads(row["payload"]), row["created_at"])
        self.bus.send(ev)
        self.bus.send(ev)   # redelivery
        self.assertEqual(len(self.effects), 1)

    def test_handler_failure_rolls_back_its_effects(self):
        def bad(e):
            self.db.execute("INSERT INTO crops(id, code, name) VALUES ('c9','X','X')")
            raise RuntimeError("after write")
        self.bus.subscribe("T", "bad", bad)
        with self.db.transaction():
            self.outbox.publish("T", "agg", "1", {})
        self.pub.publish_pending()
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM crops"), 0)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM processed_events"), 0)  # will retry cleanly

    def test_outbox_requires_transaction(self):
        with self.assertRaises(RuntimeError):
            self.outbox.publish("T", "a", "1", {})


class IdempotencyTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.idem = IdempotencyService(self.db, self.clock)
        self.calls = 0

    def _cmd(self):
        self.calls += 1
        self.db.execute("INSERT INTO crops(id, code, name) VALUES (?,?,?)", (f"c{self.calls}", f"C{self.calls}", "n"))
        return {"created": self.calls}

    def test_replay_returns_same_response_without_second_effect(self):
        kw = dict(scope="u1", key="key-12345678", endpoint="POST /pay", payload={"amount": 100}, fn=self._cmd)
        first = self.idem.run(**kw)
        second = self.idem.run(**kw)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.body, second.body)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM crops"), 1)

    def test_same_key_different_payload_rejected(self):
        self.idem.run(scope="u1", key="key-12345678", endpoint="POST /pay", payload={"amount": 100}, fn=self._cmd)
        with self.assertRaises(DuplicateIdempotencyKey):
            self.idem.run(scope="u1", key="key-12345678", endpoint="POST /pay", payload={"amount": 999}, fn=self._cmd)
        with self.assertRaises(DuplicateIdempotencyKey):  # different endpoint counts too
            self.idem.run(scope="u1", key="key-12345678", endpoint="POST /refund", payload={"amount": 100}, fn=self._cmd)
        self.assertEqual(self.calls, 1)

    def test_keys_are_scoped_per_user(self):
        for user in ("u1", "u2"):
            self.idem.run(scope=user, key="shared-key-1", endpoint="e", payload={}, fn=self._cmd)
        self.assertEqual(self.calls, 2)

    def test_missing_or_malformed_key_rejected(self):
        for bad in (None, "", "short", "has space in it!!"):
            with self.assertRaises(ValidationFailed):
                self.idem.run(scope="u", key=bad, endpoint="e", payload={}, fn=self._cmd)

    def test_failure_rolls_back_effects_and_key_so_retry_works(self):
        def failing():
            self.db.execute("INSERT INTO crops(id, code, name) VALUES ('x','X','x')")
            raise RuntimeError("provider exploded")
        with self.assertRaises(RuntimeError):
            self.idem.run(scope="u", key="key-abcdefgh", endpoint="e", payload={}, fn=failing)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM crops"), 0)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM idempotency_keys"), 0)
        res = self.idem.run(scope="u", key="key-abcdefgh", endpoint="e", payload={}, fn=self._cmd)
        self.assertFalse(res.replayed)

    def test_concurrent_duplicates_execute_exactly_once(self):
        """16 threads fire the same Idempotency-Key at once."""
        executed, results, errors = [], [], []
        lock = threading.Lock()

        def cmd():
            with lock:
                executed.append(1)
            return {"ok": True}

        def worker():
            try:
                r = self.idem.run(scope="u", key="race-key-0001", endpoint="e", payload={"a": 1}, fn=cmd)
                results.append(r.replayed)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(executed), 1)
        self.assertEqual(results.count(False), 1)
        self.assertEqual(results.count(True), 15)

    def test_two_phase_in_progress_then_stale_takeover(self):
        started = threading.Event()
        release = threading.Event()
        out = {}

        def slow():
            started.set()
            release.wait(5)
            return {"done": True}

        t = threading.Thread(target=lambda: out.setdefault("r", self.idem.run(
            scope="u", key="slow-key-0001", endpoint="e", payload={}, fn=slow, atomic=False)))
        t.start()
        started.wait(5)
        with self.assertRaises(IdempotencyRequestInProgress):
            self.idem.run(scope="u", key="slow-key-0001", endpoint="e", payload={}, fn=self._cmd, atomic=False)
        release.set()
        t.join()
        self.assertFalse(out["r"].replayed)
        again = self.idem.run(scope="u", key="slow-key-0001", endpoint="e", payload={}, fn=self._cmd, atomic=False)
        self.assertTrue(again.replayed)

    def test_two_phase_failure_releases_key(self):
        with self.assertRaises(RuntimeError):
            self.idem.run(scope="u", key="tp-key-00001", endpoint="e", payload={}, atomic=False,
                          fn=lambda: (_ for _ in ()).throw(RuntimeError("x")))
        ok = self.idem.run(scope="u", key="tp-key-00001", endpoint="e", payload={}, atomic=False, fn=lambda: {"a": 1})
        self.assertFalse(ok.replayed)


class JobQueueTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.q = DbJobQueue(self.db, self.clock)

    def _enqueue(self, *a, **k):
        with self.db.transaction():
            return self.q.enqueue(*a, **k)

    def test_runs_job(self):
        seen = []
        self.q.register("t", lambda p: seen.append(p))
        self._enqueue("t", {"a": 1})
        self.assertEqual(self.q.run_due(), {"done": 1, "retried": 0, "failed": 0})
        self.assertEqual(seen, [{"a": 1}])

    def test_retry_with_backoff_then_success(self):
        attempts = []

        def flaky(p):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("temporary")

        self.q.register("f", flaky)
        self._enqueue("f")
        self.assertEqual(self.q.run_due()["retried"], 1)
        self.assertEqual(self.q.run_due()["done"], 0)      # backoff: not due yet
        self.clock.advance(seconds=30)
        self.assertEqual(self.q.run_due()["retried"], 1)
        self.clock.advance(seconds=100)
        self.assertEqual(self.q.run_due()["done"], 1)

    def test_dead_letter_after_max_attempts(self):
        self.q.register("bad", lambda p: (_ for _ in ()).throw(RuntimeError("nope")))
        self._enqueue("bad", max_attempts=2)
        self.q.run_due()
        self.clock.advance(hours=1)
        self.assertEqual(self.q.run_due()["failed"], 1)
        self.assertEqual(self.db.one("SELECT status FROM jobs")["status"], "FAILED")

    def test_dedupe_key(self):
        self.assertIsNotNone(self._enqueue("t", dedupe_key="once"))
        self.assertIsNone(self._enqueue("t", dedupe_key="once"))

    def test_failed_handler_effects_roll_back(self):
        def h(p):
            self.db.execute("INSERT INTO crops(id, code, name) VALUES ('c','C','c')")
            raise RuntimeError("late failure")
        self.q.register("h", h)
        self._enqueue("h")
        self.q.run_due()
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM crops"), 0)

    def test_two_workers_claim_job_once(self):
        ran = []
        self.q.register("t", lambda p: ran.append(1))
        self._enqueue("t")
        q2 = DbJobQueue(self.db, self.clock)
        q2.register("t", lambda p: ran.append(2))
        ts = [threading.Thread(target=self.q.run_due), threading.Thread(target=q2.run_due)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(ran), 1)


if __name__ == "__main__":
    unittest.main()
