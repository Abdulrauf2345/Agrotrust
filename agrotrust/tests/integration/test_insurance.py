import unittest

from agrotrust.modules.farms.service import FarmService
from agrotrust.modules.insurance.service import InsuranceService
from agrotrust.modules.ledger.service import BANK, LedgerService, C, D, wallet_code
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import Conflict, UnauthorizedResourceAccess, ValidationFailed
from tests.helpers_ctx import CtxTestCase, insert_user, make_principal

IBADAN = (7.3775, 3.9470)


class InsuranceTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.led = LedgerService(self.ctx)
        self.led.ensure_system_accounts()
        self.farms = FarmService(self.ctx)
        self.ins = InsuranceService(self.ctx, self.led)
        insert_user(self.db, "farmer1", "11111")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.farm = self.farms.create(self.farmer, name="F1", state="Oyo", lga="Ibadan", size_hectares=2,
                                      lat=IBADAN[0], lon=IBADAN[1])

    def _buy(self, threshold=50.0, comparator="below", window_start="2026-06-01", window_end="2026-06-30",
            premium=5_000_00, coverage=200_000_00):
        return self.ins.buy_policy(self.farmer, farm_id=self.farm["id"], coverage_minor=coverage,
                                   premium_minor=premium, trigger_metric="rainfall_mm_total", comparator=comparator,
                                   threshold=threshold, window_start=window_start, window_end=window_end)

    def _fund(self, amt):
        self.led.ensure_wallet("farmer1")
        self.led.post(reference="topup-ins", entry_type="DEPOSIT", description="fund",
                      lines=[D(BANK, amt), C(wallet_code("farmer1"), amt)])

    def _capitalize_pool(self, amt):
        from agrotrust.modules.ledger.service import INSURANCE_POOL
        self.led.post(reference=f"pool-capital-{amt}", entry_type="CAPITAL", description="insurer capitalizes pool",
                      lines=[D(BANK, amt), C(INSURANCE_POOL, amt)])

    def test_buy_and_pay_premium(self):
        p = self._buy()
        self.assertEqual(p["state"], "PENDING_PAYMENT")
        self._fund(10_000_00)
        p = self.ins.pay_premium(self.farmer, p["id"])
        self.assertEqual(p["state"], "ACTIVE")
        self.assertEqual(self.led.wallet_balance("farmer1"), 5_000_00)
        self.assertEqual(self.led.balance("SYS:INSURANCE_POOL"), 5_000_00)

    def test_cannot_buy_for_others_farm(self):
        insert_user(self.db, "farmer2", "22222")
        farmer2 = make_principal("farmer2", Role.FARMER)
        with self.assertRaises(UnauthorizedResourceAccess):
            self.ins.buy_policy(farmer2, farm_id=self.farm["id"], coverage_minor=1000, premium_minor=100,
                                trigger_metric="rainfall_mm_total", comparator="below", threshold=50,
                                window_start="2026-01-01", window_end="2026-01-31")

    def test_validation(self):
        with self.assertRaises(ValidationFailed):
            self._buy(comparator="sideways")
        with self.assertRaises(ValidationFailed):
            self._buy(coverage=0)
        with self.assertRaises(ValidationFailed):
            self._buy(window_start="2026-06-30", window_end="2026-06-01")

    def test_cannot_pay_premium_twice(self):
        p = self._buy(premium=1_000_00)
        self._fund(5_000_00)
        self.ins.pay_premium(self.farmer, p["id"])
        with self.assertRaises(Conflict):
            self.ins.pay_premium(self.farmer, p["id"])

    def _activate(self, **kw):
        p = self._buy(**kw)
        self._fund(p["premium_minor"] or 1)
        return self.ins.pay_premium(self.farmer, p["id"])

    def test_drought_trigger_pays_out(self):
        self._capitalize_pool(500_000_00)
        p = self._activate(threshold=50.0, comparator="below", window_start="2026-06-01", window_end="2026-06-30",
                           premium=5_000_00, coverage=300_000_00)
        key = self.ins.station_key(IBADAN[0], IBADAN[1])
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-05", rainfall_mm=10.0, source="test")
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-15", rainfall_mm=15.0, source="test")
        self.clock.advance(days=200)   # move "now" past window_end
        claim = self.ins.evaluate(p["id"])
        self.assertEqual(claim["state"], "PAID")
        self.assertEqual(claim["payout_minor"], 300_000_00)
        self.assertEqual(self.led.wallet_balance("farmer1"), 300_000_00)
        self.assertEqual(self.ins.get(self.farmer, p["id"])["state"], "TRIGGERED")
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_sufficient_rainfall_does_not_trigger(self):
        p = self._activate(threshold=50.0, comparator="below", window_start="2026-06-01", window_end="2026-06-30")
        key = self.ins.station_key(IBADAN[0], IBADAN[1])
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-05", rainfall_mm=40.0, source="test")
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-15", rainfall_mm=30.0, source="test")
        self.clock.advance(days=200)
        claim = self.ins.evaluate(p["id"])
        self.assertIsNone(claim)
        self.assertEqual(self.ins.get(self.farmer, p["id"])["state"], "EXPIRED")
        self.assertEqual(self.led.wallet_balance("farmer1"), 0)

    def test_evaluate_before_window_closes_is_noop(self):
        p = self._activate(window_start="2026-06-01", window_end="2099-01-01")
        self.assertIsNone(self.ins.evaluate(p["id"]))
        self.assertEqual(self.ins.get(self.farmer, p["id"])["state"], "ACTIVE")

    def test_evaluate_is_idempotent(self):
        self._capitalize_pool(500_000_00)
        p = self._activate(threshold=50.0, comparator="below", window_start="2026-06-01", window_end="2026-06-30",
                           coverage=100_000_00, premium=1_000_00)
        key = self.ins.station_key(IBADAN[0], IBADAN[1])
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-05", rainfall_mm=5.0, source="test")
        self.clock.advance(days=200)
        a = self.ins.evaluate(p["id"])
        b = self.ins.evaluate(p["id"])
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.led.wallet_balance("farmer1"), 100_000_00)   # not double-paid

    def test_evaluate_due_worker_processes_multiple_policies(self):
        self._capitalize_pool(500_000_00)
        p1 = self._activate(threshold=50.0, comparator="below", window_start="2026-06-01", window_end="2026-06-30",
                            coverage=50_000_00, premium=500_00)
        insert_user(self.db, "farmer2", "33333")
        farmer2 = make_principal("farmer2", Role.FARMER)
        farm2 = self.farms.create(farmer2, name="F2", state="Oyo", lga="Ibadan", size_hectares=1, lat=IBADAN[0]+0.01,
                                  lon=IBADAN[1]+0.01)
        p2 = self.ins.buy_policy(farmer2, farm_id=farm2["id"], coverage_minor=60_000_00, premium_minor=0,
                                 trigger_metric="rainfall_mm_total", comparator="below", threshold=50.0,
                                 window_start="2026-06-01", window_end="2026-06-30")
        p2 = self.ins.pay_premium(farmer2, p2["id"])
        key = self.ins.station_key(IBADAN[0], IBADAN[1])
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-05", rainfall_mm=5.0, source="test")
        self.clock.advance(days=200)
        n = self.ins.evaluate_due()
        self.assertEqual(n, 2)
        self.assertEqual(self.led.wallet_balance("farmer1"), 50_000_00)
        self.assertEqual(self.led.wallet_balance("farmer2"), 60_000_00)


    def test_claim_rejected_when_pool_underfunded(self):
        # deliberately do NOT capitalize the pool beyond the tiny premium collected
        p = self._activate(threshold=50.0, comparator="below", window_start="2026-06-01", window_end="2026-06-30",
                           premium=100_00, coverage=300_000_00)
        key = self.ins.station_key(IBADAN[0], IBADAN[1])
        self.ins.ingest_observation(station_key=key, observed_on="2026-06-05", rainfall_mm=10.0, source="test")
        self.clock.advance(days=200)
        claim = self.ins.evaluate(p["id"])
        self.assertEqual(claim["state"], "REJECTED")
        self.assertEqual(self.led.wallet_balance("farmer1"), 0)
        self.assertTrue(self.led.trial_balance()["balanced"])

    def test_list_policies_scoped_to_holder(self):
        p = self._buy()
        insert_user(self.db, "farmer2", "22222")
        farmer2 = make_principal("farmer2", Role.FARMER)
        self.assertEqual([x["id"] for x in self.ins.list_policies(self.farmer)], [p["id"]])
        self.assertEqual(self.ins.list_policies(farmer2), [])


if __name__ == "__main__":
    unittest.main()
