import unittest

from agrotrust.modules.logistics.service import LogisticsService
from agrotrust.modules.marketplace.service import MarketplaceService
from agrotrust.modules.organizations.service import OrganizationService
from agrotrust.security.permissions import Principal, ROLE_PERMISSIONS, Role
from agrotrust.shared.errors import NotFound, UnauthorizedResourceAccess, ValidationFailed
from tests.helpers_ctx import CtxTestCase, insert_crop, insert_user, make_principal

LAGOS = (6.5244, 3.3792)
IBADAN = (7.3775, 3.9470)


class LogisticsTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.log = LogisticsService(self.ctx)
        self.market = MarketplaceService(self.ctx)
        insert_user(self.db, "farmer1", "11111")
        insert_user(self.db, "buyer1", "22222")
        insert_user(self.db, "logi1", "33333")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.buyer = make_principal("buyer1", Role.BUYER)
        logi_principal = make_principal("logi1", Role.LOGISTICS_PROVIDER)
        org = OrganizationService(self.ctx).create(logi_principal, name="FastHaul", type="LOGISTICS", state="Oyo")
        self.org_id = org["id"]
        self.logi = Principal(user_id="logi1", roles=frozenset({Role.LOGISTICS_PROVIDER}),
                              permissions=frozenset(ROLE_PERMISSIONS[Role.LOGISTICS_PROVIDER]),
                              org_roles={self.org_id: "ADMIN"})
        crop = insert_crop(self.db, "MAIZE")
        listing = self.market.create_listing(self.farmer, crop_id=crop, title="Maize", quantity="50", unit="KG",
                                             price="500", state="Oyo", lga="Ibadan")
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO orders(id,buyer_id,seller_id,listing_id,crop_id,qty_milli,unit,unit_price_minor,"
                "total_minor,currency,state,created_at,updated_at) VALUES ('ord1',?,?,?,?,?,?,?,?,'NGN','CREATED',?,?)",
                ("buyer1", "farmer1", listing["id"], crop, 10_000, "KG", 500, 5000, self.ctx.now_iso(), self.ctx.now_iso()))
        self.vehicle = self.log.register_vehicle(self.logi, org_id=self.org_id, plate="ABC123XY",
                                                 vehicle_type="TRUCK", capacity_kg=2000)
        self.driver = self.log.register_driver(self.logi, org_id=self.org_id, name="Musa Bello", phone="+2348000000009")

    def test_full_shipment_lifecycle(self):
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        s = self.log.assign(self.logi, s["id"], driver_id=self.driver["id"], vehicle_id=self.vehicle["id"],
                            provider_org_id=self.org_id)
        self.assertEqual(s["state"], "ASSIGNED")
        s = self.log.mark_picked_up(self.logi, s["id"], *IBADAN)
        s = self.log.mark_in_transit(self.logi, s["id"])
        s = self.log.mark_delivered(self.logi, s["id"], *LAGOS)
        self.assertEqual(s["state"], "DELIVERED")
        s = self.log.confirm(self.buyer, s["id"])
        self.assertEqual(s["state"], "CONFIRMED")
        events = self.log.track(self.buyer, s["id"])
        self.assertEqual([e["event_type"] for e in events],
                         ["ASSIGNED", "PICKED_UP", "IN_TRANSIT", "DELIVERED", "CONFIRMED"])
        # milestone-only: only pickup/delivery events carry coordinates
        self.assertIsNone(events[2]["lat"])   # IN_TRANSIT has no coordinates
        self.assertIsNotNone(events[1]["lat"])  # PICKED_UP does

    def test_only_org_member_can_assign(self):
        insert_user(self.db, "outsider", "44444")
        outsider = Principal(user_id="outsider", roles=frozenset({Role.LOGISTICS_PROVIDER}),
                             permissions=frozenset(ROLE_PERMISSIONS[Role.LOGISTICS_PROVIDER]))
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        with self.assertRaises(UnauthorizedResourceAccess):
            self.log.assign(outsider, s["id"], driver_id=self.driver["id"], vehicle_id=self.vehicle["id"],
                            provider_org_id=self.org_id)

    def test_cannot_skip_states(self):
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        with self.assertRaises(Exception):
            self.log.mark_delivered(self.logi, s["id"], *LAGOS)   # CREATED -> DELIVERED illegal

    def test_duplicate_plate_rejected(self):
        with self.assertRaises(ValidationFailed):
            self.log.register_vehicle(self.logi, org_id=self.org_id, plate="abc123xy", vehicle_type="VAN",
                                      capacity_kg=500)

    def test_non_party_cannot_track(self):
        insert_user(self.db, "stranger", "55555")
        stranger = make_principal("stranger", Role.BUYER)
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        with self.assertRaises(NotFound):
            self.log.track(stranger, s["id"])

    def test_list_vehicles_and_drivers_scoped_to_org(self):
        vehicles = self.log.list_vehicles(self.logi, self.org_id)
        self.assertEqual([v["plate"] for v in vehicles], [self.vehicle["plate"]])
        drivers = self.log.list_drivers(self.logi, self.org_id)
        self.assertEqual([d["id"] for d in drivers], [self.driver["id"]])

    def test_list_vehicles_rejects_non_member(self):
        insert_user(self.db, "outsider2", "66666")
        outsider = make_principal("outsider2", Role.LOGISTICS_PROVIDER)
        with self.assertRaises(UnauthorizedResourceAccess):
            self.log.list_vehicles(outsider, self.org_id)

    def test_list_shipments_visible_to_buyer_seller_and_provider(self):
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        self.assertIn(s["id"], [row["id"] for row in self.log.list_shipments(self.buyer)])
        self.assertIn(s["id"], [row["id"] for row in self.log.list_shipments(self.farmer)])
        self.log.assign(self.logi, s["id"], driver_id=self.driver["id"], vehicle_id=self.vehicle["id"],
                        provider_org_id=self.org_id)
        self.assertIn(s["id"], [row["id"] for row in self.log.list_shipments(self.logi)])

    def test_list_shipments_hides_unrelated_from_strangers(self):
        insert_user(self.db, "stranger2", "77777")
        stranger = make_principal("stranger2", Role.BUYER)
        self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                         dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        self.assertEqual(self.log.list_shipments(stranger), [])

    def test_mark_failed_records_reason_and_event(self):
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        s = self.log.assign(self.logi, s["id"], driver_id=self.driver["id"], vehicle_id=self.vehicle["id"],
                            provider_org_id=self.org_id)
        s = self.log.mark_failed(self.logi, s["id"], "vehicle breakdown")
        self.assertEqual(s["state"], "FAILED")
        events = self.log.track(self.buyer, s["id"])
        self.assertEqual(events[-1]["event_type"], "FAILED")
        self.assertEqual(events[-1]["note"], "vehicle breakdown")

    def test_mark_failed_requires_a_reason(self):
        s = self.log.request(self.buyer, order_id="ord1", pickup_lat=IBADAN[0], pickup_lon=IBADAN[1],
                             dropoff_lat=LAGOS[0], dropoff_lon=LAGOS[1])
        with self.assertRaises(ValidationFailed):
            self.log.mark_failed(self.logi, s["id"], "")


if __name__ == "__main__":
    unittest.main()
