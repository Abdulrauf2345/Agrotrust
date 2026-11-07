"""End-to-end HTTP tests against the Flask API layer via Flask's test client (in-process,
no real socket) - each test gets a fresh Container (fresh temp-file SQLite DB)."""
import json
import os
import unittest

from agrotrust.api.app import create_app
from agrotrust.api.container import Container


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.container = Container()
        self.app = create_app(self.container)
        self.client = self.app.test_client()
        self.db_path = self.container.db.path

    def tearDown(self):
        self.container.db.close()
        for suffix in ("", "-wal", "-shm"):
            p = self.db_path + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except PermissionError:
                    pass   # best-effort cleanup; a stray OS-level file lock shouldn't fail the test

    def _register(self, phone, role, password="SecurePass123", name="Test User"):
        r = self.client.post("/api/v1/auth/register",
                             json={"phone": phone, "password": password, "full_name": name, "role": role})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def _login(self, phone, password="SecurePass123"):
        r = self.client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["access_token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _crop(self):
        # Container now seeds a few reference crops (MAIZE, RICE, CASSAVA) on startup for local/
        # Postman convenience - reuse that instead of inserting a colliding duplicate (crops.code
        # is UNIQUE).
        return self.container.db.one("SELECT id FROM crops WHERE code='MAIZE'")["id"]


class HealthAndErrorMappingTests(ApiTestCase):
    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_security_headers_present(self):
        r = self.client.get("/healthz")
        self.assertIn("X-Content-Type-Options", r.headers)
        self.assertIn("Content-Security-Policy", r.headers)

    def test_missing_auth_returns_401_with_domain_error_shape(self):
        r = self.client.get("/api/v1/me")
        self.assertEqual(r.status_code, 401)
        body = r.get_json()
        self.assertEqual(body["error"]["code"], "AUTHENTICATION_FAILED")

    def test_request_id_header_present(self):
        r = self.client.get("/healthz")
        self.assertIn("X-Request-Id", r.headers)
        self.assertTrue(len(r.headers["X-Request-Id"]) > 0)

    def test_metrics_endpoint_reports_requests(self):
        self.client.get("/healthz")
        r = self.client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("http_requests_total", r.get_data(as_text=True))

    def test_unknown_route_returns_404_json(self):
        r = self.client.get("/api/v1/nonexistent")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["code"], "NOT_FOUND")

    def test_malformed_json_body_returns_422(self):
        r = self.client.post("/api/v1/orders", data="not json", content_type="application/json",
                             headers=self._auth(self._login_new_buyer()))
        self.assertEqual(r.status_code, 422)

    def _login_new_buyer(self):
        self._register("+2348010000001", "BUYER")
        return self._login("+2348010000001")


class AuthFlowTests(ApiTestCase):
    def test_register_login_me(self):
        self._register("+2348010000002", "FARMER", name="Farmer Joe")
        token = self._login("+2348010000002")
        r = self.client.get("/api/v1/me", headers=self._auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["full_name"], "Farmer Joe")
        self.assertIn("FARMER", r.get_json()["roles"])

    def test_wrong_password_rejected(self):
        self._register("+2348010000003", "BUYER")
        r = self.client.post("/api/v1/auth/login", json={"phone": "+2348010000003", "password": "WrongPass1"})
        self.assertEqual(r.status_code, 401)

    def test_refresh_token_rotates(self):
        self._register("+2348010000004", "BUYER")
        r = self.client.post("/api/v1/auth/login", json={"phone": "+2348010000004", "password": "SecurePass123"})
        rt = r.get_json()["refresh_token"]
        r2 = self.client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        self.assertEqual(r2.status_code, 200)
        self.assertIn("access_token", r2.get_json())


class CropsApiTests(ApiTestCase):
    def test_list_crops_is_public_and_returns_seeded_reference_data(self):
        r = self.client.get("/api/v1/crops")
        self.assertEqual(r.status_code, 200)
        codes = {row["code"] for row in r.get_json()}
        self.assertEqual(codes, {"MAIZE", "RICE", "CASSAVA"})

    def test_list_crops_needs_no_auth_header(self):
        r = self.client.get("/api/v1/crops")
        self.assertEqual(r.status_code, 200)


class CorsTests(ApiTestCase):
    def test_allowed_origin_gets_cors_headers(self):
        r = self.client.get("/healthz", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")

    def test_unknown_origin_gets_no_cors_header(self):
        r = self.client.get("/healthz", headers={"Origin": "http://evil.example"})
        self.assertNotIn("Access-Control-Allow-Origin", r.headers)

    def test_preflight_options_request_succeeds(self):
        r = self.client.open("/api/v1/listings", method="OPTIONS", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(r.status_code, 204)


class MarketplaceAndOrderApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self._register("+2348010000010", "FARMER", name="Farmer Joe")
        self._register("+2348010000011", "BUYER", name="Buyer Sue")
        self.farmer_token = self._login("+2348010000010")
        self.buyer_token = self._login("+2348010000011")
        self.crop = self._crop()

    def test_create_search_and_get_listing(self):
        r = self.client.post("/api/v1/listings", json={"crop_id": self.crop, "title": "Fresh Maize",
                                                        "quantity": "100", "unit": "KG", "price": "500",
                                                        "state": "Oyo", "lga": "Ibadan"},
                             headers=self._auth(self.farmer_token))
        self.assertEqual(r.status_code, 201)
        listing_id = r.get_json()["id"]
        r = self.client.get(f"/api/v1/listings/{listing_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["title"], "Fresh Maize")
        r = self.client.get("/api/v1/listings?q=maize")
        self.assertEqual(r.get_json()["total"], 1)

    def test_buyer_cannot_create_listing(self):
        r = self.client.post("/api/v1/listings", json={"crop_id": self.crop, "title": "x", "quantity": "1",
                                                        "unit": "KG", "price": "1", "state": "Oyo", "lga": "Ibadan"},
                             headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 403)

    def test_order_lifecycle_via_api(self):
        r = self.client.post("/api/v1/listings", json={"crop_id": self.crop, "title": "Fresh Maize",
                                                        "quantity": "100", "unit": "KG", "price": "500",
                                                        "state": "Oyo", "lga": "Ibadan"},
                             headers=self._auth(self.farmer_token))
        listing_id = r.get_json()["id"]
        r = self.client.post("/api/v1/orders", json={"listing_id": listing_id, "quantity": "10"},
                             headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 201)
        order_id = r.get_json()["id"]
        r = self.client.post(f"/api/v1/orders/{order_id}/confirm", headers=self._auth(self.farmer_token))
        self.assertEqual(r.get_json()["state"], "CONFIRMED")
        # buyer cannot see an order that isn't theirs
        self._register("+2348010000012", "BUYER", name="Stranger")
        stranger_token = self._login("+2348010000012")
        r = self.client.get(f"/api/v1/orders/{order_id}", headers=self._auth(stranger_token))
        self.assertEqual(r.status_code, 404)

    def test_release_requires_idempotency_key_header(self):
        r = self.client.post("/api/v1/listings", json={"crop_id": self.crop, "title": "Fresh Maize",
                                                        "quantity": "100", "unit": "KG", "price": "500",
                                                        "state": "Oyo", "lga": "Ibadan"},
                             headers=self._auth(self.farmer_token))
        listing_id = r.get_json()["id"]
        r = self.client.post("/api/v1/orders", json={"listing_id": listing_id, "quantity": "10"},
                             headers=self._auth(self.buyer_token))
        order_id = r.get_json()["id"]
        r = self.client.post(f"/api/v1/orders/{order_id}/release", headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 422)   # missing Idempotency-Key


class PaymentsApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self._register("+2348010000020", "BUYER")
        self.token = self._login("+2348010000020")

    def test_charge_and_webhook_credits_wallet(self):
        r = self.client.post("/api/v1/payments/charges", json={"amount_minor": 50000}, headers=self._auth(self.token))
        self.assertEqual(r.status_code, 201)
        ref = r.get_json()["reference"]
        self.container.payment_provider.simulate_success(ref)
        body, sig = self.container.payment_provider.webhook("charge.success", "evt1", ref)
        r = self.client.post("/api/v1/payments/webhook", data=body,
                             headers={"X-Signature": sig, "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "succeeded")

    def test_dev_endpoints_drive_full_webhook_flow_over_pure_http(self):
        """The dev-only simulate-success/webhook-signature endpoints exist so an external HTTP
        client (Postman, curl) can exercise the full payment-webhook path without any
        in-process Python access to the mock provider - this proves that works end to end."""
        r = self.client.post("/api/v1/payments/charges", json={"amount_minor": 75000}, headers=self._auth(self.token))
        ref = r.get_json()["reference"]
        r = self.client.post("/api/v1/_dev/payments/simulate-success", json={"reference": ref})
        self.assertEqual(r.status_code, 200)
        body = json.dumps({"event": "charge.success", "id": "evt-dev-1", "data": {"reference": ref}})
        r = self.client.post("/api/v1/_dev/payments/webhook-signature", data=body, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        sig = r.get_json()["signature"]
        r = self.client.post("/api/v1/payments/webhook", data=body,
                             headers={"X-Signature": sig, "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "succeeded")

    def test_bad_webhook_signature_rejected(self):
        r = self.client.post("/api/v1/payments/charges", json={"amount_minor": 1000}, headers=self._auth(self.token))
        ref = r.get_json()["reference"]
        body, _ = self.container.payment_provider.webhook("charge.success", "evtbad", ref)
        r = self.client.post("/api/v1/payments/webhook", data=body,
                             headers={"X-Signature": "deadbeef", "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 401)


class RateLimitApiTests(ApiTestCase):
    def test_login_bucket_rate_limited(self):
        self._register("+2348010000030", "BUYER")
        codes = []
        for _ in range(15):
            r = self.client.post("/api/v1/auth/login", json={"phone": "+2348010000030", "password": "wrong"})
            codes.append(r.status_code)
        self.assertIn(429, codes)
        self.assertTrue(all(c in (401, 429) for c in codes))


class LogisticsApiTests(ApiTestCase):
    """Covers the list endpoints added for the frontend's logistics screens
    (GET /vehicles, /drivers, /shipments) plus the /shipments/<id>/failed
    route - none of these had HTTP coverage before, only the service layer
    did (tests/integration/test_logistics.py)."""

    def setUp(self):
        super().setUp()
        self._register("+2348020000001", "LOGISTICS_PROVIDER")
        self.logi_token = self._login("+2348020000001")
        r = self.client.post("/api/v1/organizations", json={"name": "FastHaul", "type": "LOGISTICS", "state": "Oyo"},
                             headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 201, r.get_json())
        self.org_id = r.get_json()["id"]

        self._register("+2348020000002", "FARMER")
        self.farmer_token = self._login("+2348020000002")
        self._register("+2348020000003", "BUYER")
        self.buyer_token = self._login("+2348020000003")

        crop = self._crop()
        r = self.client.post("/api/v1/listings",
                             json={"crop_id": crop, "title": "Maize", "quantity": "50", "unit": "KG",
                                   "price": "500", "state": "Oyo", "lga": "Ibadan"},
                             headers=self._auth(self.farmer_token))
        self.assertEqual(r.status_code, 201, r.get_json())
        listing_id = r.get_json()["id"]
        farmer_id = self.container.db.one("SELECT id FROM users WHERE phone=?", ("+2348020000002",))["id"]
        buyer_id = self.container.db.one("SELECT id FROM users WHERE phone=?", ("+2348020000003",))["id"]
        with self.container.db.transaction():
            self.container.db.execute(
                "INSERT INTO orders(id,buyer_id,seller_id,listing_id,crop_id,qty_milli,unit,unit_price_minor,"
                "total_minor,currency,state,created_at,updated_at) VALUES ('ord-log-1',?,?,?,?,?,?,?,?,'NGN',"
                "'CREATED',?,?)",
                (buyer_id, farmer_id, listing_id, crop, 10_000, "KG", 500, 5000,
                 self.container.ctx.now_iso(), self.container.ctx.now_iso()))

        r = self.client.post("/api/v1/vehicles",
                             json={"org_id": self.org_id, "plate": "ABC123XY", "vehicle_type": "TRUCK",
                                   "capacity_kg": 2000},
                             headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 201, r.get_json())
        self.vehicle_id = r.get_json()["id"]

        r = self.client.post("/api/v1/drivers",
                             json={"org_id": self.org_id, "name": "Musa Bello", "phone": "+2348000000009"},
                             headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 201, r.get_json())
        self.driver_id = r.get_json()["id"]

    def test_list_vehicles_requires_org_id(self):
        r = self.client.get("/api/v1/vehicles", headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 422)

    def test_list_vehicles_returns_registered_fleet(self):
        r = self.client.get(f"/api/v1/vehicles?org_id={self.org_id}", headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([v["plate"] for v in r.get_json()], ["ABC123XY"])

    def test_list_vehicles_blocks_non_member(self):
        r = self.client.get(f"/api/v1/vehicles?org_id={self.org_id}", headers=self._auth(self.farmer_token))
        self.assertEqual(r.status_code, 403)

    def test_list_drivers_returns_registered_drivers(self):
        r = self.client.get(f"/api/v1/drivers?org_id={self.org_id}", headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([d["name"] for d in r.get_json()], ["Musa Bello"])

    def test_shipment_full_lifecycle_and_list_visibility(self):
        r = self.client.post("/api/v1/shipments",
                             json={"order_id": "ord-log-1", "pickup_lat": 7.3775, "pickup_lon": 3.9470,
                                   "dropoff_lat": 6.5244, "dropoff_lon": 3.3792},
                             headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 201, r.get_json())
        shipment_id = r.get_json()["id"]

        r = self.client.get("/api/v1/shipments", headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 200)
        self.assertIn(shipment_id, [s["id"] for s in r.get_json()])

        r = self.client.post(f"/api/v1/shipments/{shipment_id}/assign",
                             json={"driver_id": self.driver_id, "vehicle_id": self.vehicle_id,
                                   "provider_org_id": self.org_id},
                             headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200, r.get_json())

        r = self.client.get("/api/v1/shipments", headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200)
        self.assertIn(shipment_id, [s["id"] for s in r.get_json()])

        r = self.client.post(f"/api/v1/shipments/{shipment_id}/picked-up",
                             json={"lat": 7.3775, "lon": 3.9470}, headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.client.post(f"/api/v1/shipments/{shipment_id}/in-transit", headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.client.post(f"/api/v1/shipments/{shipment_id}/delivered",
                             json={"lat": 6.5244, "lon": 3.3792}, headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.client.post(f"/api/v1/shipments/{shipment_id}/confirm", headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["state"], "CONFIRMED")

        r = self.client.get(f"/api/v1/shipments/{shipment_id}/track", headers=self._auth(self.buyer_token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([e["event_type"] for e in r.get_json()],
                         ["ASSIGNED", "PICKED_UP", "IN_TRANSIT", "DELIVERED", "CONFIRMED"])

    def test_shipment_failed_route(self):
        r = self.client.post("/api/v1/shipments",
                             json={"order_id": "ord-log-1", "pickup_lat": 7.3775, "pickup_lon": 3.9470,
                                   "dropoff_lat": 6.5244, "dropoff_lon": 3.3792},
                             headers=self._auth(self.buyer_token))
        shipment_id = r.get_json()["id"]
        r = self.client.post(f"/api/v1/shipments/{shipment_id}/assign",
                             json={"driver_id": self.driver_id, "vehicle_id": self.vehicle_id,
                                   "provider_org_id": self.org_id},
                             headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.client.post(f"/api/v1/shipments/{shipment_id}/failed", json={"reason": "vehicle breakdown"},
                             headers=self._auth(self.logi_token))
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["state"], "FAILED")

    def test_list_shipments_hides_from_unrelated_user(self):
        self._register("+2348020000004", "BUYER")
        stranger_token = self._login("+2348020000004")
        self.client.post("/api/v1/shipments",
                         json={"order_id": "ord-log-1", "pickup_lat": 7.3775, "pickup_lon": 3.9470,
                               "dropoff_lat": 6.5244, "dropoff_lon": 3.3792},
                         headers=self._auth(self.buyer_token))
        r = self.client.get("/api/v1/shipments", headers=self._auth(stranger_token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])


if __name__ == "__main__":
    unittest.main()
