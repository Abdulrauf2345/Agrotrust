"""Geospatial helpers: validation, distance, polygons.

These run in Python so behaviour is identical on every backend and is unit-tested.
On PostgreSQL the same questions are answered by PostGIS (ST_DWithin, ST_Intersects)
using the GiST indexes in migrations/postgres_extras.sql; these functions remain the
input-validation layer in front of the database either way.
Coordinates are (lat, lon) in the public API and (lon, lat) inside GeoJSON rings.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Sequence

from .errors import ValidationFailed

EARTH_RADIUS_M = 6_371_008.8
Ring = list[tuple[float, float]]  # [(lon, lat), ...] closed


@dataclass(frozen=True)
class Bounds:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


def _num(v, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValidationFailed(f"{name} must be a number")
    if math.isnan(v) or math.isinf(v):
        raise ValidationFailed(f"{name} must be finite")
    return float(v)


def validate_point(lat, lon, bounds: Bounds | None = None) -> tuple[float, float]:
    lat, lon = _num(lat, "latitude"), _num(lon, "longitude")
    if not -90 <= lat <= 90:
        raise ValidationFailed("latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise ValidationFailed("longitude must be between -180 and 180")
    if bounds and not (bounds.min_lat <= lat <= bounds.max_lat and bounds.min_lon <= lon <= bounds.max_lon):
        raise ValidationFailed("coordinates are outside the supported operating region",
                               details={"lat": lat, "lon": lon})
    return lat, lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bbox_for_radius(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lon, max_lon) that fully contains the circle; SQL prefilter."""
    if radius_km <= 0 or radius_km > 5000:
        raise ValidationFailed("radius_km must be in (0, 5000]")
    dlat = math.degrees(radius_km * 1000 / EARTH_RADIUS_M)
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    dlon = min(180.0, math.degrees(radius_km * 1000 / (EARTH_RADIUS_M * cos_lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


# ---- polygons ---------------------------------------------------------------
def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _segments_intersect(p1, p2, p3, p4) -> bool:
    o1, o2, o3, o4 = _orient(p1, p2, p3), _orient(p1, p2, p4), _orient(p3, p4, p1), _orient(p3, p4, p2)
    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)) and 0 not in (o1, o2, o3, o4):
        return True
    return ((o1 == 0 and _on_segment(p1, p2, p3)) or (o2 == 0 and _on_segment(p1, p2, p4)) or
            (o3 == 0 and _on_segment(p3, p4, p1)) or (o4 == 0 and _on_segment(p3, p4, p2)))


def ring_is_simple(ring: Ring) -> bool:
    n = len(ring) - 1  # edges
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # adjacent edges share a vertex by design
            if _segments_intersect(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                return False
    return True


def parse_polygon_geojson(geojson, bounds: Bounds | None = None) -> Ring:
    if isinstance(geojson, str):
        try:
            geojson = json.loads(geojson)
        except json.JSONDecodeError as exc:
            raise ValidationFailed("boundary is not valid JSON") from exc
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        raise ValidationFailed("boundary must be a GeoJSON Polygon")
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or len(coords) != 1:
        raise ValidationFailed("boundary must have exactly one ring (holes are not supported)")
    ring_raw = coords[0]
    if not isinstance(ring_raw, list) or len(ring_raw) < 4:
        raise ValidationFailed("polygon ring needs at least 4 positions")
    ring: Ring = []
    for pos in ring_raw:
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            raise ValidationFailed("invalid position in polygon")
        lat, lon = validate_point(pos[1], pos[0], bounds)
        ring.append((lon, lat))
    if ring[0] != ring[-1]:
        raise ValidationFailed("polygon ring must be closed (first == last position)")
    if len(set(ring[:-1])) < 3:
        raise ValidationFailed("polygon needs at least 3 distinct positions")
    if not ring_is_simple(ring):
        raise ValidationFailed("polygon ring must not self-intersect")
    if ring_area_ha(ring) <= 0:
        raise ValidationFailed("polygon has zero area")
    return ring


def ring_area_ha(ring: Ring) -> float:
    """Area in hectares using a local equirectangular projection (accurate for farm-sized shapes)."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = math.cos(math.radians(lat0)) * math.pi / 180 * EARTH_RADIUS_M
    ky = math.pi / 180 * EARTH_RADIUS_M
    pts = [(p[0] * kx, p[1] * ky) for p in ring]
    s = sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))
    return abs(s) / 2 / 10_000


def ring_centroid(ring: Ring) -> tuple[float, float]:
    """(lat, lon) vertex-average centroid (fine for small, convex-ish farm plots)."""
    pts = ring[:-1]
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def point_in_ring(lat: float, lon: float, ring: Ring) -> bool:
    inside = False
    x, y = lon, lat
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if _orient((x1, y1), (x2, y2), (x, y)) == 0 and _on_segment((x1, y1), (x2, y2), (x, y)):
            return True  # boundary counts as inside
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def rings_intersect(a: Ring, b: Ring) -> bool:
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            if _segments_intersect(a[i], a[i + 1], b[j], b[j + 1]):
                return True
    return point_in_ring(a[0][1], a[0][0], b) or point_in_ring(b[0][1], b[0][0], a)


def distance_to_ring_m(lat: float, lon: float, ring: Ring) -> float:
    """0 if inside, else distance to the nearest vertex/edge sample (good enough for visit-proximity checks)."""
    if point_in_ring(lat, lon, ring):
        return 0.0
    lat0 = lat
    kx = math.cos(math.radians(lat0)) * math.pi / 180 * EARTH_RADIUS_M
    ky = math.pi / 180 * EARTH_RADIUS_M
    px, py = lon * kx, lat * ky
    best = float("inf")
    for i in range(len(ring) - 1):
        ax, ay = ring[i][0] * kx, ring[i][1] * ky
        bx, by = ring[i + 1][0] * kx, ring[i + 1][1] * ky
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def polygon_geojson(ring: Sequence[tuple[float, float]]) -> str:
    return json.dumps({"type": "Polygon", "coordinates": [[list(p) for p in ring]]})
