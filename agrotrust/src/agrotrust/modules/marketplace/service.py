"""Marketplace listings: create, search (FTS + filters + geo), atomic stock reservation."""
from __future__ import annotations

from decimal import Decimal

from ...db.database import fts_query
from ...security.permissions import Principal
from ...shared import geo
from ...shared.context import Context
from ...shared.errors import Conflict, NotFound, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import new_id
from ...shared.money import Money, from_milli, to_milli

_SORTS = {"newest": "l.created_at DESC", "price_asc": "l.price_minor ASC, l.created_at DESC",
          "price_desc": "l.price_minor DESC, l.created_at DESC", "quantity": "l.quantity_available_milli DESC"}
_UNITS = {"KG", "TONNE", "BAG", "CRATE", "BASKET", "PIECE", "LITRE"}


class MarketplaceService:
    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    def list_crops(self) -> list[dict]:
        """Active crop reference data, for populating a listing-creation form's crop picker.
        Public: crops are catalog data, not anything principal-specific."""
        rows = self.db.all("SELECT id, code, name, default_unit FROM crops WHERE active=1 ORDER BY name")
        return [dict(r) for r in rows]

    def create_listing(self, principal: Principal, *, crop_id: str, title: str, quantity, unit: str, price,
                       state: str, lga: str, description: str = "", lat=None, lon=None, farm_id: str | None = None,
                       org_id: str | None = None, quality_grade: str = "UNGRADED") -> dict:
        principal.require("listing:create")
        title = (title or "").strip()
        if not 3 <= len(title) <= 120:
            raise ValidationFailed("title must be 3-120 characters")
        if unit not in _UNITS:
            raise ValidationFailed(f"unit must be one of {sorted(_UNITS)}")
        if quality_grade not in ("A", "B", "C", "UNGRADED"):
            raise ValidationFailed("invalid quality_grade")
        qty = to_milli(quantity)
        if qty <= 0:
            raise ValidationFailed("quantity must be positive")
        price_minor = Money.from_decimal(price).minor
        if price_minor <= 0:
            raise ValidationFailed("price must be positive")
        if not state or not lga:
            raise ValidationFailed("state and lga are required")
        if (lat is None) != (lon is None):
            raise ValidationFailed("lat and lon must be provided together")
        if lat is not None:
            geo.validate_point(lat, lon)
        with self.db.transaction():
            if not self.db.one("SELECT 1 FROM crops WHERE id=? AND active=1", (crop_id,)):
                raise ValidationFailed("unknown crop")
            verified = 0
            if farm_id:
                farm = self.db.one("SELECT owner_user_id, verification_status FROM farms WHERE id=?", (farm_id,))
                if not farm or farm["owner_user_id"] != principal.user_id:
                    raise UnauthorizedResourceAccess("farm does not belong to you")
                verified = 1 if farm["verification_status"] == "VERIFIED" else 0
            if org_id and not principal.is_org_member(org_id) and not principal.is_admin:
                raise UnauthorizedResourceAccess("not a member of that organization")
            lid, now = new_id(), self.ctx.now_iso()
            self.db.execute(
                "INSERT INTO listings(id,seller_id,org_id,farm_id,crop_id,title,description,quantity_total_milli,"
                "quantity_available_milli,unit,price_minor,state,lga,lat,lon,quality_grade,farm_verified,created_at,"
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lid, principal.user_id, org_id, farm_id, crop_id, title, description[:2000], qty, qty, unit,
                 price_minor, state, lga, lat, lon, quality_grade, verified, now, now))
            self.ctx.audit.record(actor_id=principal.user_id, action="LISTING_CREATED", resource_type="listing",
                                  resource_id=lid, new={"qty_milli": qty, "price_minor": price_minor})
            self.ctx.publish("listing.created", "listing", lid, {"crop_id": crop_id})
        return self.get(lid)

    def get(self, listing_id: str) -> dict:
        row = self.db.one("SELECT * FROM listings WHERE id=?", (listing_id,))
        if not row:
            raise NotFound("listing not found")
        return self._present(row)

    @staticmethod
    def _present(row: dict) -> dict:
        out = dict(row)
        out["quantity_available"] = str(from_milli(row["quantity_available_milli"]))
        out["price"] = str(Money(row["price_minor"]).to_decimal())
        return out

    def search(self, *, text: str | None = None, crop_id: str | None = None, state: str | None = None,
               lga: str | None = None, min_price=None, max_price=None, verified_only: bool = False,
               near: tuple[float, float, float] | None = None, sort: str = "newest", limit: int = 20,
               offset: int = 0) -> dict:
        if sort not in _SORTS:
            raise ValidationFailed(f"sort must be one of {sorted(_SORTS)}")
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        where, params = ["l.status='ACTIVE'", "l.quantity_available_milli > 0"], []
        if text:
            q = fts_query(text)
            if not q:
                raise ValidationFailed("search text has no searchable words")
            where.append(self.db.text_search_clause("l"))
            params.append(q)
        for col, val in (("l.crop_id", crop_id), ("l.state", state), ("l.lga", lga)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if min_price is not None:
            where.append("l.price_minor>=?")
            params.append(Money.from_decimal(min_price).minor)
        if max_price is not None:
            where.append("l.price_minor<=?")
            params.append(Money.from_decimal(max_price).minor)
        if verified_only:
            where.append("l.farm_verified=1")
        if near:
            lat, lon, radius_m = near
            geo.validate_point(lat, lon)
            if not 0 < radius_m <= 500_000:
                raise ValidationFailed("radius must be between 1m and 500km")
            min_lat, max_lat, min_lon, max_lon = geo.bbox_for_radius(lat, lon, radius_m / 1000)  # index-friendly prefilter
            where.append("l.lat BETWEEN ? AND ? AND l.lon BETWEEN ? AND ?")
            params += [min_lat, max_lat, min_lon, max_lon]
        sql = f"SELECT l.* FROM listings l WHERE {' AND '.join(where)} ORDER BY {_SORTS[sort]}"
        rows = self.db.all(sql, params)
        if near:   # exact great-circle filter after the bbox prefilter
            rows = [r for r in rows if geo.haversine_m(near[0], near[1], r["lat"], r["lon"]) <= near[2]]
            if sort == "newest":
                rows.sort(key=lambda r: geo.haversine_m(near[0], near[1], r["lat"], r["lon"]))
        total = len(rows)
        return {"total": total, "items": [self._present(r) for r in rows[offset:offset + limit]]}

    def _own(self, principal: Principal, listing_id: str) -> dict:
        row = self.db.one("SELECT * FROM listings WHERE id=?", (listing_id,))
        if not row:
            raise NotFound("listing not found")
        if row["seller_id"] != principal.user_id and not principal.has("listing:moderate"):
            raise UnauthorizedResourceAccess("not your listing")
        return row

    def set_status(self, principal: Principal, listing_id: str, status: str) -> dict:
        if status not in ("ACTIVE", "PAUSED", "CLOSED"):
            raise ValidationFailed("status must be ACTIVE, PAUSED or CLOSED")
        with self.db.transaction():
            row = self._own(principal, listing_id)
            if row["status"] == "CLOSED":
                raise Conflict("closed listings cannot be reopened")
            if status == "ACTIVE" and row["quantity_available_milli"] == 0:
                raise Conflict("no stock available")
            self.db.execute("UPDATE listings SET status=?, version=version+1, updated_at=? WHERE id=?",
                            (status, self.ctx.now_iso(), listing_id))
            self.ctx.audit.record(actor_id=principal.user_id, action="LISTING_STATUS", resource_type="listing",
                                  resource_id=listing_id, old={"status": row["status"]}, new={"status": status})
        return self.get(listing_id)

    def update_price(self, principal: Principal, listing_id: str, price) -> dict:
        p = Money.from_decimal(price).minor
        if p <= 0:
            raise ValidationFailed("price must be positive")
        with self.db.transaction():
            row = self._own(principal, listing_id)   # existing orders keep the price they were created at
            self.db.execute("UPDATE listings SET price_minor=?, version=version+1, updated_at=? WHERE id=?",
                            (p, self.ctx.now_iso(), listing_id))
            self.ctx.audit.record(actor_id=principal.user_id, action="LISTING_PRICE", resource_type="listing",
                                  resource_id=listing_id, old={"price_minor": row["price_minor"]}, new={"price_minor": p})
        return self.get(listing_id)

    # ---- stock (called by OrderService inside its transaction) -------------------------------
    def reserve(self, listing_id: str, qty_milli: int) -> dict:
        """Atomic guarded decrement: succeeds only if stock is sufficient. Cannot oversell."""
        if not self.db.in_transaction:
            raise RuntimeError("reserve must run inside a transaction")
        res = self.db.execute(
            "UPDATE listings SET quantity_available_milli = quantity_available_milli - ?,"
            " status = CASE WHEN quantity_available_milli - ? = 0 THEN 'SOLD_OUT' ELSE status END,"
            " version=version+1, updated_at=? WHERE id=? AND status='ACTIVE' AND quantity_available_milli >= ?",
            (qty_milli, qty_milli, self.ctx.now_iso(), listing_id, qty_milli))
        if res.rowcount != 1:
            listing = self.db.one("SELECT status FROM listings WHERE id=?", (listing_id,))
            if not listing:
                raise NotFound("listing not found")
            raise Conflict("listing is not available in the requested quantity",
                           details={"status": listing["status"]})
        return self.db.one("SELECT * FROM listings WHERE id=?", (listing_id,))

    def release(self, listing_id: str, qty_milli: int) -> None:
        if not self.db.in_transaction:
            raise RuntimeError("release must run inside a transaction")
        self.db.execute(
            "UPDATE listings SET quantity_available_milli = quantity_available_milli + ?,"
            " status = CASE WHEN status='SOLD_OUT' THEN 'ACTIVE' ELSE status END,"
            " version=version+1, updated_at=? WHERE id=?", (qty_milli, self.ctx.now_iso(), listing_id))
