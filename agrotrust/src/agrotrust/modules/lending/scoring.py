"""Rule-based, fully explainable credit scoring (spec section 19).

No ML black box here: every point added or subtracted is a named, documented factor, so a
rejected applicant can be told exactly why. ``ml_predictions``/sklearn-based scoring (spec
section 20) can layer on top later as an *additional*, separately-labelled signal - it must
never replace this explainable baseline for a decision that affects someone's access to credit.
"""
from __future__ import annotations

from dataclasses import dataclass

MODEL_VERSION = "rule-engine-v1"
_BASE = 500
_MIN, _MAX = 300, 850


@dataclass(frozen=True)
class ScoreResult:
    score: int
    risk_grade: str
    factors: dict[str, int]     # factor name -> point contribution (signed)
    features: dict[str, object]  # raw inputs, for audit/reproducibility


def _grade(score: int) -> str:
    if score >= 750:
        return "A"
    if score >= 650:
        return "B"
    if score >= 550:
        return "C"
    if score >= 450:
        return "D"
    return "E"


def score_applicant(*, farm_verified: bool, kyc_verified: bool, completed_orders: int,
                    completed_orders_value_minor: int, defaulted_loans: int, active_loans: int,
                    on_time_repayments: int, late_repayments: int) -> ScoreResult:
    factors: dict[str, int] = {}
    features = {"farm_verified": farm_verified, "kyc_verified": kyc_verified, "completed_orders": completed_orders,
                "completed_orders_value_minor": completed_orders_value_minor, "defaulted_loans": defaulted_loans,
                "active_loans": active_loans, "on_time_repayments": on_time_repayments,
                "late_repayments": late_repayments}

    factors["base"] = _BASE
    if farm_verified:
        factors["verified_farm"] = 100
    if kyc_verified:
        factors["kyc_verified"] = 50
    order_pts = min(completed_orders, 5) * 10
    if order_pts:
        factors["marketplace_track_record"] = order_pts
    volume_pts = min(completed_orders_value_minor // 100_000_00, 5) * 10   # +10 per ~100k NGN traded, capped
    if volume_pts:
        factors["trading_volume"] = int(volume_pts)
    ontime_pts = min(on_time_repayments, 10) * 8
    if ontime_pts:
        factors["on_time_repayment_history"] = ontime_pts
    if late_repayments:
        factors["late_repayment_history"] = -min(late_repayments, 10) * 15
    if defaulted_loans:
        factors["prior_default"] = -min(defaulted_loans, 3) * 120
    if active_loans >= 3:
        factors["existing_debt_load"] = -20

    raw = sum(factors.values())
    score = max(_MIN, min(_MAX, raw))
    if score != raw:
        factors["clamped_to_range"] = score - raw
    return ScoreResult(score=score, risk_grade=_grade(score), factors=factors, features=features)
