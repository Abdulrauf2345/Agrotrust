"""Parametric weather insurance (spec section 24): a policy pays out automatically once an
observed weather metric crosses a threshold, with no manual loss adjustment needed.

Trigger config example (rainfall deficit / drought cover):
    {"metric": "rainfall_mm_total", "comparator": "below", "threshold": 50.0}
The engine sums ``weather_observations`` for the policy's station over [window_start,
window_end] and compares against the threshold. One claim per policy (schema UNIQUE), so the
evaluation job is naturally idempotent.
"""
from __future__ import annotations

import json

from ...security.permissions import Principal
from ...shared import geo
from ...shared.context import Context
from ...shared.errors import Conflict, NotFound, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import new_id
from ..ledger.service import BANK, INSURANCE_POOL, C, D, LedgerService, wallet_code

_COMPARATORS = {"below": lambda v, t: v < t, "above": lambda v, t: v > t}


class InsuranceService:
    def __init__(self, ctx: Context, ledger: LedgerService):
        self.ctx, self.db, self.ledger = ctx, ctx.db, ledger

    # ----------------------------------------------------------------- policy
    def buy_policy(self, principal: Principal, *, farm_id: str, coverage_minor: int, premium_minor: int,
                  trigger_metric: str, comparator: str, threshold: float, window_start: str, window_end: str,
                  insurer_org_id: str | None = None) -> dict:
        principal.require("insurance:buy")
        if comparator not in _COMPARATORS:
            raise ValidationFailed(f"comparator must be one of {sorted(_COMPARATORS)}")
        if coverage_minor <= 0 or premium_minor < 0:
            raise ValidationFailed("coverage must be positive and premium non-negative")
        if window_end < window_start:
            raise ValidationFailed("window_end must not precede window_start")
        farm = self.db.one("SELECT * FROM farms WHERE id=?", (farm_id,))
        if not farm:
            raise NotFound("farm not found")
        if farm["owner_user_id"] != principal.user_id:
            raise UnauthorizedResourceAccess("not your farm")
        pid = new_id()
        config = json.dumps({"metric": trigger_metric, "comparator": comparator, "threshold": threshold})
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO insurance_policies(id,farm_id,holder_id,insurer_org_id,coverage_minor,premium_minor,"
                "trigger_type,trigger_config,window_start,window_end,station_lat,station_lon,state,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'PENDING_PAYMENT',?)",
                (pid, farm_id, principal.user_id, insurer_org_id, coverage_minor, premium_minor, "WEATHER", config,
                 window_start, window_end, farm["lat"], farm["lon"], self.ctx.now_iso()))
        return self.db.one("SELECT * FROM insurance_policies WHERE id=?", (pid,))

    def pay_premium(self, principal: Principal, policy_id: str) -> dict:
        with self.db.transaction():
            policy = self.db.one("SELECT * FROM insurance_policies WHERE id=?", (policy_id,))
            if not policy:
                raise NotFound("policy not found")
            if policy["holder_id"] != principal.user_id:
                raise UnauthorizedResourceAccess("not your policy")
            if policy["state"] != "PENDING_PAYMENT":
                raise Conflict("premium already paid or policy no longer pending")
            if policy["premium_minor"] > 0:
                self.ledger.ensure_wallet(principal.user_id)
                self.ledger.post(reference=f"insurance_premium:{policy_id}", entry_type="INSURANCE_PREMIUM",
                                 description=f"Premium for policy {policy_id}",
                                 lines=[D(wallet_code(principal.user_id), policy["premium_minor"]),
                                        C(INSURANCE_POOL, policy["premium_minor"])], actor_id=principal.user_id)
            self.db.execute("UPDATE insurance_policies SET state='ACTIVE', premium_paid_at=? WHERE id=?",
                            (self.ctx.now_iso(), policy_id))
            self.ctx.publish("insurance.policy_active", "insurance_policy", policy_id, {})
        return self.db.one("SELECT * FROM insurance_policies WHERE id=?", (policy_id,))

    def get(self, principal: Principal, policy_id: str) -> dict:
        row = self.db.one("SELECT * FROM insurance_policies WHERE id=?", (policy_id,))
        if not row or (row["holder_id"] != principal.user_id and not principal.has("insurance:claim_view")
                       and not principal.is_admin):
            raise NotFound("policy not found")
        return row

    def list_policies(self, principal: Principal) -> list[dict]:
        """A farmer sees their own policies; an insurer org member or admin
        sees everything they are entitled to view. Added for the frontend's
        insurance screens - the original route set only exposed a
        single-policy read, with no "my policies" list."""
        if principal.is_admin or principal.has("insurance:claim_view"):
            return self.db.all("SELECT * FROM insurance_policies ORDER BY created_at DESC")
        return self.db.all("SELECT * FROM insurance_policies WHERE holder_id=? ORDER BY created_at DESC",
                           (principal.user_id,))

    # -------------------------------------------------------------- weather data
    def ingest_observation(self, *, station_key: str, observed_on: str, rainfall_mm: float, source: str) -> None:
        if rainfall_mm < 0:
            raise ValidationFailed("rainfall_mm cannot be negative")
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO weather_observations(station_key, observed_on, rainfall_mm, source) VALUES (?,?,?,?)"
                " ON CONFLICT(station_key, observed_on, source) DO UPDATE SET rainfall_mm=excluded.rainfall_mm",
                (station_key, observed_on, rainfall_mm, source))

    @staticmethod
    def station_key(lat: float, lon: float) -> str:
        """Coarse-grid station key (~0.1 degree, ~11km) so nearby farms share weather data."""
        geo.validate_point(lat, lon)
        return f"{round(lat, 1):.1f},{round(lon, 1):.1f}"

    def _observed_total_rainfall(self, policy: dict) -> float:
        key = self.station_key(policy["station_lat"], policy["station_lon"])
        row = self.db.one(
            "SELECT COALESCE(SUM(rainfall_mm),0) AS total FROM weather_observations WHERE station_key=?"
            " AND observed_on BETWEEN ? AND ?", (key, policy["window_start"], policy["window_end"]))
        return row["total"]

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, policy_id: str) -> dict | None:
        """Runs the trigger check for one policy; returns the claim if one was (or already was) created."""
        with self.db.transaction():
            policy = self.db.one("SELECT * FROM insurance_policies WHERE id=?", (policy_id,))
            if not policy:
                raise NotFound("policy not found")
            existing_claim = self.db.one("SELECT * FROM insurance_claims WHERE policy_id=?", (policy_id,))
            if existing_claim:
                return existing_claim
            if policy["state"] != "ACTIVE":
                return None
            if self.ctx.now_iso() < policy["window_end"]:
                return None   # window not yet closed; nothing to evaluate
            config = json.loads(policy["trigger_config"])
            observed = self._observed_total_rainfall(policy)
            triggered = _COMPARATORS[config["comparator"]](observed, config["threshold"])
            if not triggered:
                self.db.execute("UPDATE insurance_policies SET state='EXPIRED' WHERE id=?", (policy_id,))
                return None
            cid = new_id()
            self.db.execute(
                "INSERT INTO insurance_claims(id,policy_id,trigger_value,threshold,state,payout_minor,created_at)"
                " VALUES (?,?,?,?,'APPROVED',?,?)",
                (cid, policy_id, observed, config["threshold"], policy["coverage_minor"], self.ctx.now_iso()))
            self.db.execute("UPDATE insurance_policies SET state='TRIGGERED' WHERE id=?", (policy_id,))
            self._payout(cid, policy)
            self.ctx.publish("insurance.claim_triggered", "insurance_claim", cid,
                             {"policy_id": policy_id, "observed": observed, "threshold": config["threshold"]})
            return self.db.one("SELECT * FROM insurance_claims WHERE id=?", (cid,))

    def _payout(self, claim_id: str, policy: dict) -> None:
        if not self.db.in_transaction:
            raise RuntimeError("_payout must run inside a transaction")
        self.ledger.ensure_wallet(policy["holder_id"])
        try:
            self.ledger.post(reference=f"insurance_payout:{claim_id}", entry_type="INSURANCE_PAYOUT",
                             description=f"Parametric payout for claim {claim_id}",
                             lines=[D(INSURANCE_POOL, policy["coverage_minor"]),
                                    C(wallet_code(policy["holder_id"]), policy["coverage_minor"])])
            self.db.execute("UPDATE insurance_claims SET state='PAID' WHERE id=?", (claim_id,))
        except Exception:
            # pool under-capitalised: leave the claim APPROVED (not PAID) for manual/insurer top-up handling,
            # rather than silently losing the claim or crashing the evaluation job.
            self.db.execute("UPDATE insurance_claims SET state='REJECTED' WHERE id=?", (claim_id,))
            self.ctx.audit.record(actor_id=None, action="INSURANCE_PAYOUT_FAILED", resource_type="insurance_claim",
                                  resource_id=claim_id, context={"reason": "insufficient pool funds"})

    def evaluate_due(self) -> int:
        """Worker: evaluate every ACTIVE policy whose window has closed."""
        due = self.db.all("SELECT id FROM insurance_policies WHERE state='ACTIVE' AND window_end<=?",
                          (self.ctx.now_iso(),))
        n = 0
        for row in due:
            if self.evaluate(row["id"]):
                n += 1
        return n
