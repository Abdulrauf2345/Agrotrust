import unittest

from agrotrust.modules.farms.service import FarmService
from agrotrust.modules.offline_sync.service import OfflineSyncService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import ValidationFailed
from tests.helpers_ctx import CtxTestCase, insert_user, make_principal

IBADAN = (7.3775, 3.9470)


class OfflineSyncTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.farms = FarmService(self.ctx)
        self.sync = OfflineSyncService(self.ctx)
        insert_user(self.db, "farmer1", "11111")
        insert_user(self.db, "agent1", "22222")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.agent = make_principal("agent1", Role.FIELD_AGENT)
        with self.db.transaction():
            self.db.execute("INSERT INTO roles(name,self_register) VALUES ('FIELD_AGENT',0) ON CONFLICT(name) DO NOTHING")
            self.db.execute("INSERT INTO user_roles(user_id,role,granted_at) VALUES ('agent1','FIELD_AGENT',?)"
                            " ON CONFLICT DO NOTHING", (self.ctx.now_iso(),))
        f = self.farms.create(self.farmer, name="F1", state="Oyo", lga="Ibadan", size_hectares=1,
                              lat=IBADAN[0], lon=IBADAN[1])
        self.farm_id = f["id"]
        f = self.farms.request_verification(self.farmer, f["id"])
        from agrotrust.security.permissions import Principal
        admin = Principal(user_id="agent1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        self.farms.assign_agent(admin, f["id"], "agent1")

        def visit_handler(principal, payload):
            return self.farms.record_visit(principal, payload["farm_id"], lat=payload["lat"], lon=payload["lon"],
                                           client_id=payload["client_id"], observations=payload.get("observations", ""))
        self.sync.register("farm_visit", visit_handler)

    def _op(self, op_id, **payload_extra):
        payload = {"farm_id": self.farm_id, "lat": IBADAN[0], "lon": IBADAN[1], "client_id": f"visit-{op_id}"}
        payload.update(payload_extra)
        return dict(operation_id=op_id, op_type="farm_visit", payload=payload, client_created_at=self.ctx.now_iso())

    def test_apply_new_operation(self):
        res = self.sync.apply(self.agent, device_id="dev1", **self._op("op-001"))
        self.assertEqual(res["status"], "APPLIED")
        self.assertFalse(res["replayed"])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM farm_visits"), 1)

    def test_replay_same_operation_is_idempotent(self):
        op = self._op("op-001")
        a = self.sync.apply(self.agent, device_id="dev1", **op)
        b = self.sync.apply(self.agent, device_id="dev1", **op)
        self.assertEqual(a["status"], b["status"])
        self.assertTrue(b["replayed"])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM farm_visits"), 1)   # not double-applied

    def test_same_operation_id_different_device_is_independent(self):
        op1 = self._op("op-shared")
        op2 = self._op("op-shared")
        self.sync.apply(self.agent, device_id="dev1", **op1)
        res = self.sync.apply(self.agent, device_id="dev2", **op2)
        self.assertEqual(res["status"], "APPLIED")
        self.assertFalse(res["replayed"])

    def test_unknown_op_type_rejected(self):
        with self.assertRaises(ValidationFailed):
            self.sync.apply(self.agent, device_id="dev1", operation_id="x1", op_type="not_a_thing", payload={},
                            client_created_at=self.ctx.now_iso())

    def test_domain_error_recorded_as_rejected_not_raised(self):
        # too far from the farm -> ValidationFailed inside the handler
        res = self.sync.apply(self.agent, device_id="dev1", **self._op("op-far", lat=1.0, lon=1.0))
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("error", res["result"])
        # replay of the same rejected op returns the same terminal result, doesn't re-run the handler
        res2 = self.sync.apply(self.agent, device_id="dev1", **self._op("op-far", lat=1.0, lon=1.0))
        self.assertEqual(res2["status"], "REJECTED")
        self.assertTrue(res2["replayed"])

    def test_batch_continues_after_one_failure(self):
        f2 = self.farms.create(self.farmer, name="F2", state="Oyo", lga="Ibadan", size_hectares=1,
                               lat=IBADAN[0], lon=IBADAN[1])
        f2 = self.farms.request_verification(self.farmer, f2["id"])
        from agrotrust.security.permissions import Principal
        admin = Principal(user_id="agent1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        self.farms.assign_agent(admin, f2["id"], "agent1")
        op3 = self._op("op-b3", farm_id=f2["id"])
        ops = [self._op("op-b1"), dict(operation_id="op-b2", op_type="bad_type", payload={},
                                       client_created_at=self.ctx.now_iso()), op3]
        results = self.sync.apply_batch(self.agent, "dev1", ops)
        statuses = [r["status"] for r in results]
        self.assertEqual(statuses.count("APPLIED"), 2)
        self.assertIn("ERROR", statuses)

    def test_pending_status_lookup(self):
        self.sync.apply(self.agent, device_id="dev1", **self._op("op-001"))
        statuses = self.sync.pending_status("dev1", ["op-001", "op-nonexistent"])
        self.assertEqual(statuses["op-001"], "APPLIED")
        self.assertNotIn("op-nonexistent", statuses)


if __name__ == "__main__":
    unittest.main()
