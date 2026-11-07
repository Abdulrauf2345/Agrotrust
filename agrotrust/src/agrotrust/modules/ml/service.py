"""ML module (spec sections 20, 47): yield prediction (scikit-learn) and price-anomaly detection
(numpy). Every prediction is persisted to ``ml_predictions`` with its input features and a
confidence figure, so any decision it informs can be explained and audited after the fact -
this supplements, but never replaces, the explainable rule-based credit score in
``modules/lending/scoring.py``.
"""
from __future__ import annotations

import json

import numpy as np

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import NotFound, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import new_id
from ...shared.money import from_milli

YIELD_MODEL = "yield_predictor"
YIELD_MODEL_VERSION_ML = "sklearn-linreg-v1"
YIELD_MODEL_VERSION_NAIVE = "naive-average-v1"
_MIN_TRAINING_ROWS = 5


class MLService:
    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    # ------------------------------------------------------------- yield model
    def _training_data(self) -> list[dict]:
        return self.db.all(
            "SELECT f.id AS farm_id, f.size_hectares, SUM(l.quantity_milli) AS total_qty_milli"
            " FROM farms f JOIN lots l ON l.farm_id=f.id GROUP BY f.id HAVING total_qty_milli > 0")

    def predict_yield(self, principal: Principal, farm_id: str) -> dict:
        farm = self.db.one("SELECT * FROM farms WHERE id=?", (farm_id,))
        if not farm:
            raise NotFound("farm not found")
        if farm["owner_user_id"] != principal.user_id and not principal.has("ml:manage") and not principal.is_admin:
            raise UnauthorizedResourceAccess("not your farm")
        rows = self._training_data()
        size = farm["size_hectares"]
        if len(rows) >= _MIN_TRAINING_ROWS:
            prediction, confidence, version, coeffs = self._sklearn_predict(rows, size)
        else:
            prediction, confidence, version, coeffs = self._naive_predict(rows, size)
        features = {"size_hectares": size, "training_rows": len(rows)}
        pid = new_id()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO ml_predictions(id,model_name,model_version,subject_type,subject_id,input_features,"
                "prediction,confidence,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, YIELD_MODEL, version, "farm", farm_id, json.dumps({**features, "coefficients": coeffs}),
                 prediction, confidence, self.ctx.now_iso()))
        return {"id": pid, "model_version": version, "predicted_yield_kg": round(prediction, 1),
                "confidence": confidence, "features": features}

    def _naive_predict(self, rows: list[dict], size: float) -> tuple[float, float | None, str, dict]:
        """Fallback with too little history: average observed kg/hectare across whatever data exists,
        or a documented rule-of-thumb (1000kg/ha) with zero data - never a fabricated 'confident' number."""
        if not rows:
            return size * 1000.0, None, YIELD_MODEL_VERSION_NAIVE, {"kg_per_hectare_assumed": 1000.0}
        per_ha = [float(from_milli(r["total_qty_milli"])) / r["size_hectares"] for r in rows if r["size_hectares"] > 0]
        avg = float(np.mean(per_ha)) if per_ha else 1000.0
        return size * avg, None, YIELD_MODEL_VERSION_NAIVE, {"kg_per_hectare_avg": round(avg, 2)}

    def _sklearn_predict(self, rows: list[dict], size: float) -> tuple[float, float | None, str, dict]:
        from sklearn.linear_model import LinearRegression
        X = np.array([[r["size_hectares"]] for r in rows], dtype=float)
        y = np.array([from_milli(r["total_qty_milli"]) for r in rows], dtype=float)
        model = LinearRegression().fit(X, y)
        pred = max(0.0, float(model.predict([[size]])[0]))
        r2 = float(model.score(X, y))
        return pred, round(r2, 3), YIELD_MODEL_VERSION_ML, {"slope": round(float(model.coef_[0]), 4),
                                                             "intercept": round(float(model.intercept_), 2)}

    def prediction_history(self, principal: Principal, farm_id: str) -> list[dict]:
        farm = self.db.one("SELECT owner_user_id FROM farms WHERE id=?", (farm_id,))
        if not farm:
            raise NotFound("farm not found")
        if farm["owner_user_id"] != principal.user_id and not principal.has("ml:manage") and not principal.is_admin:
            raise UnauthorizedResourceAccess("not your farm")
        return self.db.all("SELECT * FROM ml_predictions WHERE subject_type='farm' AND subject_id=? ORDER BY created_at",
                           (farm_id,))

    # -------------------------------------------------------- price anomaly detection
    def detect_price_anomalies(self, principal: Principal, crop_id: str, *, z_threshold: float = 2.5) -> list[dict]:
        """Flags ACTIVE listings whose price is a statistical outlier vs other listings of the same crop -
        a lightweight fraud/mispricing signal, not an automatic takedown (spec section 47: assistive, not autonomous)."""
        principal.require("ml:manage")
        if z_threshold <= 0:
            raise ValidationFailed("z_threshold must be positive")
        rows = self.db.all("SELECT id, price_minor FROM listings WHERE crop_id=? AND status='ACTIVE'", (crop_id,))
        if len(rows) < 5:
            return []
        prices = np.array([r["price_minor"] for r in rows], dtype=float)
        mean, std = float(np.mean(prices)), float(np.std(prices))
        if std == 0:
            return []
        flagged = []
        for r, p in zip(rows, prices):
            z = (p - mean) / std
            if abs(z) >= z_threshold:
                flagged.append({"listing_id": r["id"], "price_minor": r["price_minor"], "z_score": round(z, 2),
                                "mean_price_minor": round(mean, 2)})
        return flagged
