import unittest

from agrotrust.modules.farms.service import FarmService
from agrotrust.modules.inventory.service import InventoryService
from agrotrust.modules.traceability.service import TraceabilityService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import NotFound, UnauthorizedResourceAccess, ValidationFailed
from tests.helpers_ctx import CtxTestCase, insert_crop, insert_user, make_principal


class TraceabilityTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.farms = FarmService(self.ctx)
        self.trace = TraceabilityService(self.ctx)
        self.inv = InventoryService(self.ctx)
        self.crop = insert_crop(self.db, "MAIZE")
        insert_user(self.db, "farmer1", "11111")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.farm = self.farms.create(self.farmer, name="F1", state="Oyo", lga="Ibadan", size_hectares=1,
                                      lat=7.37, lon=3.94)
        from agrotrust.modules.organizations.service import OrganizationService
        from agrotrust.security.permissions import Principal, ROLE_PERMISSIONS
        agg_principal = make_principal("farmer1", Role.AGGREGATOR)
        org = OrganizationService(self.ctx).create(agg_principal, name="Agg Co", type="AGGREGATOR", state="Oyo")
        self.agg = Principal(user_id="farmer1", roles=frozenset({Role.AGGREGATOR}),
                             permissions=frozenset(ROLE_PERMISSIONS[Role.AGGREGATOR]), org_roles={org["id"]: "ADMIN"})
        self.org_id = org["id"]

    def test_create_lot_generates_code_and_harvest_event(self):
        lot = self.trace.create_lot(self.farmer, farm_id=self.farm["id"], crop_id=self.crop, quantity="500",
                                    unit="KG", harvest_date="2026-09-01")
        self.assertTrue(lot["code"].startswith("LOT-2026-"))
        hist = self.trace.history(lot["id"])
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["event_type"], "HARVESTED")
        self.assertTrue(self.trace.verify_chain(lot["id"])[0])

    def test_cannot_create_lot_for_others_farm(self):
        insert_user(self.db, "farmer2", "22222")
        farmer2 = make_principal("farmer2", Role.FARMER)
        with self.assertRaises(UnauthorizedResourceAccess):
            self.trace.create_lot(farmer2, farm_id=self.farm["id"], crop_id=self.crop, quantity="1", unit="KG",
                                  harvest_date="2026-09-01")

    def test_custody_chain_detects_tampering(self):
        lot = self.trace.create_lot(self.farmer, farm_id=self.farm["id"], crop_id=self.crop, quantity="500",
                                    unit="KG", harvest_date="2026-09-01")
        with self.db.transaction():
            self.trace.record_event(lot["id"], event_type="DISPATCHED", actor_id="farmer1", to_party="warehouse-1")
            self.trace.record_event(lot["id"], event_type="DELIVERED", actor_id="farmer1", from_party="warehouse-1")
        self.assertTrue(self.trace.verify_chain(lot["id"])[0])
        # tamper directly via raw connection (bypassing triggers is not even needed - just edit note)
        import sqlite3
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.transaction():
                self.db.execute("UPDATE custody_events SET note='hacked' WHERE lot_id=?", (lot["id"],))
        # drop the trigger and mutate directly to prove hash-chain (not just the trigger) catches tampering
        raw = sqlite3.connect(self.db.path)
        raw.execute("DROP TRIGGER IF EXISTS custody_no_update")
        cur = raw.execute("SELECT id FROM custody_events WHERE lot_id=? ORDER BY id LIMIT 1", (lot["id"],))
        first_id = cur.fetchone()[0]
        raw.execute("UPDATE custody_events SET note='tampered' WHERE id=?", (first_id,))
        raw.commit()
        raw.close()
        ok, bad_id = self.trace.verify_chain(lot["id"])
        self.assertFalse(ok)
        self.assertEqual(bad_id, first_id)

    def test_weighing_and_inspection(self):
        lot = self.trace.create_lot(self.farmer, farm_id=self.farm["id"], crop_id=self.crop, quantity="500",
                                    unit="KG", harvest_date="2026-09-01")
        with self.assertRaises(ValidationFailed):
            self.trace.record_weighing(self.farmer, lot["id"], gross_kg=10, tare_kg=20)
        w = self.trace.record_weighing(self.farmer, lot["id"], gross_kg=520, tare_kg=20)
        self.assertEqual(w["net_milli"], 500_000)
        insp = self.trace.record_inspection(self.farmer, lot["id"], grade="A", passed=True, moisture_pct=12.5)
        self.assertEqual(insp["grade"], "A")
        self.assertEqual(self.trace.get_lot(lot["id"])["quality_grade"], "A")
        hist = self.trace.history(lot["id"])
        self.assertEqual(hist[-1]["event_type"], "INSPECTED")

    def test_inventory_movements_and_stock(self):
        lot = self.trace.create_lot(self.farmer, farm_id=self.farm["id"], crop_id=self.crop, quantity="500",
                                    unit="KG", harvest_date="2026-09-01")
        wh = self.inv.create_warehouse(self.agg, org_id=self.org_id, name="Central WH", state="Oyo")
        self.inv.move(self.agg, warehouse_id=wh["id"], lot_id=lot["id"], movement_type="RECEIPT", qty_delta="500",
                     reason="initial receipt from farm")
        self.assertEqual(self.inv.stock(wh["id"], lot["id"]), 500_000)
        self.inv.move(self.agg, warehouse_id=wh["id"], lot_id=lot["id"], movement_type="DISPATCH", qty_delta="200",
                     reason="dispatched to buyer order #123")
        self.assertEqual(self.inv.stock(wh["id"], lot["id"]), 300_000)

    def test_inventory_requires_reason_and_blocks_overdraw(self):
        lot = self.trace.create_lot(self.farmer, farm_id=self.farm["id"], crop_id=self.crop, quantity="500",
                                    unit="KG", harvest_date="2026-09-01")
        wh = self.inv.create_warehouse(self.agg, org_id=self.org_id, name="WH2")
        with self.assertRaises(ValidationFailed):
            self.inv.move(self.agg, warehouse_id=wh["id"], lot_id=lot["id"], movement_type="RECEIPT",
                         qty_delta="10", reason="")
        with self.assertRaises(ValidationFailed):
            self.inv.move(self.agg, warehouse_id=wh["id"], lot_id=lot["id"], movement_type="DISPATCH",
                         qty_delta="10", reason="oversell attempt")

    def test_list_lots_scoped_to_owner_and_farm(self):
        lot = self.trace.create_lot(self.farmer, farm_id=self.farm["id"], crop_id=self.crop, quantity="500",
                                    unit="KG", harvest_date="2026-09-01")
        insert_user(self.db, "farmer2", "22222")
        farmer2 = make_principal("farmer2", Role.FARMER)
        self.assertEqual([x["id"] for x in self.trace.list_lots(self.farmer)], [lot["id"]])
        self.assertEqual(self.trace.list_lots(farmer2), [])
        self.assertEqual([x["id"] for x in self.trace.list_lots(self.farmer, farm_id=self.farm["id"])], [lot["id"]])
        with self.assertRaises(UnauthorizedResourceAccess):
            self.trace.list_lots(farmer2, farm_id=self.farm["id"])


if __name__ == "__main__":
    unittest.main()
