import unittest

from agrotrust.modules.farms.service import FarmService
from agrotrust.modules.ml.service import MLService, YIELD_MODEL_VERSION_ML, YIELD_MODEL_VERSION_NAIVE
from agrotrust.modules.traceability.service import TraceabilityService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import PermissionDenied, UnauthorizedResourceAccess
from tests.helpers_ctx import CtxTestCase, insert_crop, insert_user, make_principal

IBADAN = (7.3775, 3.9470)


class MLTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.farms = FarmService(self.ctx)
        self.trace = TraceabilityService(self.ctx)
        self.ml = MLService(self.ctx)
        self.crop = insert_crop(self.db, "MAIZE")
        insert_user(self.db, "farmer1", "11111")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.farm = self.farms.create(self.farmer, name="F1", state="Oyo", lga="Ibadan", size_hectares=2,
                                      lat=IBADAN[0], lon=IBADAN[1])

    def test_naive_fallback_with_no_history(self):
        res = self.ml.predict_yield(self.farmer, self.farm["id"])
        self.assertEqual(res["model_version"], YIELD_MODEL_VERSION_NAIVE)
        self.assertEqual(res["predicted_yield_kg"], 2000.0)   # 2ha * 1000kg/ha default assumption
        self.assertIsNone(res["confidence"])

    def test_naive_fallback_with_some_history_below_sklearn_threshold(self):
        # 1-4 training rows: too few for sklearn, but enough that the naive averaging branch
        # (as opposed to the zero-data default-assumption branch) is the one actually exercised.
        self._seed_lots(3, kg_per_ha=900)
        res = self.ml.predict_yield(self.farmer, self.farm["id"])
        self.assertEqual(res["model_version"], YIELD_MODEL_VERSION_NAIVE)
        self.assertAlmostEqual(res["predicted_yield_kg"], 1800.0, delta=1.0)   # 2ha * ~900kg/ha average

    def test_prediction_is_recorded_and_queryable(self):
        self.ml.predict_yield(self.farmer, self.farm["id"])
        hist = self.ml.prediction_history(self.farmer, self.farm["id"])
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["model_name"], "yield_predictor")

    def test_cannot_predict_for_others_farm(self):
        insert_user(self.db, "farmer2", "22222")
        farmer2 = make_principal("farmer2", Role.FARMER)
        with self.assertRaises(UnauthorizedResourceAccess):
            self.ml.predict_yield(farmer2, self.farm["id"])

    def _seed_lots(self, n, kg_per_ha=800):
        for i in range(n):
            f = self.farms.create(self.farmer, name=f"Farm{i}", state="Oyo", lga="Ibadan", size_hectares=float(i + 1),
                                  lat=IBADAN[0], lon=IBADAN[1])
            self.trace.create_lot(self.farmer, farm_id=f["id"], crop_id=self.crop, quantity=str((i + 1) * kg_per_ha),
                                  unit="KG", harvest_date="2026-06-01")

    def test_sklearn_model_used_with_enough_history(self):
        self._seed_lots(6, kg_per_ha=800)
        res = self.ml.predict_yield(self.farmer, self.farm["id"])
        self.assertEqual(res["model_version"], YIELD_MODEL_VERSION_ML)
        self.assertIsNotNone(res["confidence"])
        # perfectly linear synthetic data -> should predict close to 2ha * 800kg/ha = 1600
        self.assertAlmostEqual(res["predicted_yield_kg"], 1600.0, delta=50.0)

    def test_anomaly_detection_flags_outlier_price(self):
        from agrotrust.modules.marketplace.service import MarketplaceService
        market = MarketplaceService(self.ctx)
        for _ in range(10):
            market.create_listing(self.farmer, crop_id=self.crop, title="Maize normal", quantity="10", unit="KG",
                                  price="500", state="Oyo", lga="Ibadan")
        outlier = market.create_listing(self.farmer, crop_id=self.crop, title="Maize weird price", quantity="10",
                                        unit="KG", price="100000", state="Oyo", lga="Ibadan")
        from agrotrust.security.permissions import Principal
        admin = Principal(user_id="farmer1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        flagged = self.ml.detect_price_anomalies(admin, self.crop)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["listing_id"], outlier["id"])

    def test_anomaly_detection_requires_permission(self):
        with self.assertRaises(PermissionDenied):
            self.ml.detect_price_anomalies(self.farmer, self.crop)

    def test_anomaly_detection_too_few_listings_returns_empty(self):
        from agrotrust.security.permissions import Principal
        admin = Principal(user_id="farmer1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))
        self.assertEqual(self.ml.detect_price_anomalies(admin, self.crop), [])


if __name__ == "__main__":
    unittest.main()
