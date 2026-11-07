import unittest

from agrotrust.modules.farms.service import FarmService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import (ConcurrentModification, Conflict, UnauthorizedResourceAccess, ValidationFailed)
from tests.helpers_ctx import CtxTestCase, insert_user, make_principal

IBADAN = (7.3775, 3.9470)


class FarmTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.svc = FarmService(self.ctx)
        insert_user(self.db, "farmer1", "11111")
        insert_user(self.db, "agent1", "22222")
        insert_user(self.db, "admin1", "33333")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.agent = make_principal("agent1", Role.FIELD_AGENT)
        from agrotrust.security.permissions import Principal
        self.admin = Principal(user_id="admin1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        with self.db.transaction():
            self.db.execute("INSERT INTO roles(name,self_register) VALUES ('FIELD_AGENT',0)"
                            " ON CONFLICT(name) DO NOTHING")
            self.db.execute("INSERT INTO user_roles(user_id, role, granted_at) VALUES (?,?,?)"
                            " ON CONFLICT DO NOTHING", ("agent1", "FIELD_AGENT", "t"))

    def _farm(self, **kw):
        defaults = dict(name="Adeola Farm", state="Oyo", lga="Ibadan North", size_hectares=2.5,
                        lat=IBADAN[0], lon=IBADAN[1])
        defaults.update(kw)
        return self.svc.create(self.farmer, **defaults)

    def test_create_and_ownership(self):
        f = self._farm()
        self.assertEqual(f["verification_status"], "UNVERIFIED")
        got = self.svc.get(self.farmer, f["id"])
        self.assertEqual(got["id"], f["id"])
        insert_user(self.db, "stranger", "44444")
        stranger = make_principal("stranger", Role.FARMER)
        with self.assertRaises(UnauthorizedResourceAccess):
            self.svc.get(stranger, f["id"])

    def test_validation(self):
        with self.assertRaises(ValidationFailed):
            self._farm(size_hectares=-1)
        with self.assertRaises(ValidationFailed):
            self._farm(lat=999, lon=3.9)
        with self.assertRaises(ValidationFailed):
            self._farm(name="a")

    def test_boundary_must_contain_point(self):
        # small square not containing IBADAN point
        bad_poly = {"type": "Polygon", "coordinates": [[[3.0, 7.0], [3.01, 7.0], [3.01, 7.01], [3.0, 7.01], [3.0, 7.0]]]}
        with self.assertRaises(ValidationFailed):
            self._farm(boundary_geojson=bad_poly)
        good_poly = {"type": "Polygon", "coordinates": [[[3.94, 7.37], [3.96, 7.37], [3.96, 7.39], [3.94, 7.39], [3.94, 7.37]]]}
        f = self._farm(boundary_geojson=good_poly, lat=7.38, lon=3.95)
        self.assertIsNotNone(f["boundary_geojson"])

    def test_full_verification_lifecycle(self):
        f = self._farm()
        f = self.svc.request_verification(self.farmer, f["id"])
        self.assertEqual(f["verification_status"], "PENDING")
        f = self.svc.assign_agent(self.admin, f["id"], "agent1")
        self.assertEqual(f["verification_status"], "ASSIGNED")
        f = self.svc.record_visit(self.agent, f["id"], lat=IBADAN[0], lon=IBADAN[1], client_id="visit-abc")
        self.assertEqual(f["verification_status"], "VISITED")
        f = self.svc.submit(self.agent, f["id"])
        self.assertEqual(f["verification_status"], "UNDER_REVIEW")
        f = self.svc.verify(self.admin, f["id"], notes="looks good")
        self.assertEqual(f["verification_status"], "VERIFIED")
        self.assertIsNotNone(f["verified_at"])

    def test_visit_too_far_rejected(self):
        f = self._farm()
        f = self.svc.request_verification(self.farmer, f["id"])
        f = self.svc.assign_agent(self.admin, f["id"], "agent1")
        # ~50km away (Abeokuta-ish offset)
        with self.assertRaises(ValidationFailed):
            self.svc.record_visit(self.agent, f["id"], lat=7.15, lon=3.35, client_id="visit-far")
        self.assertEqual(self.svc.get(self.admin, f["id"])["verification_status"], "ASSIGNED")

    def test_visit_idempotent_replay(self):
        f = self._farm()
        f = self.svc.request_verification(self.farmer, f["id"])
        f = self.svc.assign_agent(self.admin, f["id"], "agent1")
        self.svc.record_visit(self.agent, f["id"], lat=IBADAN[0], lon=IBADAN[1], client_id="dup-1")
        self.svc.record_visit(self.agent, f["id"], lat=IBADAN[0], lon=IBADAN[1], client_id="dup-1")  # replay
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM farm_visits WHERE client_id='dup-1'"), 1)

    def test_only_assigned_agent_can_visit(self):
        insert_user(self.db, "agent2", "55555")
        agent2 = make_principal("agent2", Role.FIELD_AGENT)
        f = self._farm()
        f = self.svc.request_verification(self.farmer, f["id"])
        f = self.svc.assign_agent(self.admin, f["id"], "agent1")
        with self.assertRaises(UnauthorizedResourceAccess):
            self.svc.record_visit(agent2, f["id"], lat=IBADAN[0], lon=IBADAN[1], client_id="x")

    def test_cannot_submit_without_visit_or_skip_states(self):
        f = self._farm()
        with self.assertRaises(Exception):
            self.svc.submit(self.agent, f["id"])
        f = self.svc.request_verification(self.farmer, f["id"])
        with self.assertRaises(Exception):
            self.svc.verify(self.admin, f["id"])   # cannot verify straight from PENDING

    def test_reject_requires_reason_and_allows_resubmit(self):
        f = self._farm()
        f = self.svc.request_verification(self.farmer, f["id"])
        f = self.svc.assign_agent(self.admin, f["id"], "agent1")
        f = self.svc.record_visit(self.agent, f["id"], lat=IBADAN[0], lon=IBADAN[1], client_id="v1")
        f = self.svc.submit(self.agent, f["id"])
        with self.assertRaises(ValidationFailed):
            self.svc.reject(self.admin, f["id"], "")
        f = self.svc.reject(self.admin, f["id"], "boundary does not match visit location")
        self.assertEqual(f["verification_status"], "REJECTED")
        f = self.svc.request_verification(self.farmer, f["id"])
        self.assertEqual(f["verification_status"], "PENDING")

    def test_cannot_edit_while_under_review(self):
        f = self._farm()
        f = self.svc.request_verification(self.farmer, f["id"])
        f = self.svc.assign_agent(self.admin, f["id"], "agent1")
        f = self.svc.record_visit(self.agent, f["id"], lat=IBADAN[0], lon=IBADAN[1], client_id="v1")
        f = self.svc.submit(self.agent, f["id"])
        with self.assertRaises(Conflict):
            self.svc.update(self.farmer, f["id"], name="Renamed Farm")

    def test_optimistic_concurrency(self):
        f = self._farm()
        stale_version = f["version"]
        self.svc.update(self.farmer, f["id"], name="First Update")   # bumps version in the DB
        # simulate a second writer that read the farm before the first update committed
        with self.db.transaction():
            with self.assertRaises(ConcurrentModification):
                res = self.db.execute(
                    "UPDATE farms SET name=?, version=version+1, updated_at=? WHERE version=? AND id=?",
                    ("late-writer", self.ctx.now_iso(), stale_version, f["id"]))
                if res.rowcount != 1:
                    raise ConcurrentModification("stale version")

    def test_nearby_search(self):
        f1 = self._farm(lat=7.3775, lon=3.9470)
        f2 = self._farm(lat=9.0765, lon=7.3986)  # Abuja, far away
        with self.db.transaction():
            self.db.execute("UPDATE farms SET verification_status='VERIFIED' WHERE id IN (?,?)", (f1["id"], f2["id"]))
        results = self.svc.nearby(7.3775, 3.9470, 50)
        ids = [r["id"] for r in results]
        self.assertIn(f1["id"], ids)
        self.assertNotIn(f2["id"], ids)


if __name__ == "__main__":
    unittest.main()
