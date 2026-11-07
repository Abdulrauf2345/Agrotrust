import unittest

from agrotrust.shared import geo
from agrotrust.shared.errors import ValidationFailed

NG = geo.Bounds(3.9, 14.8, 2.5, 15.0)
# ~1.1 km square near Sokoto (approx 0.01 deg)
SQUARE = {"type": "Polygon", "coordinates": [[[5.20, 13.00], [5.21, 13.00], [5.21, 13.01], [5.20, 13.01], [5.20, 13.00]]]}


class GeoTests(unittest.TestCase):
    def test_haversine_known_distances(self):
        # Lagos -> Abuja ~ 526 km (cross-checked by hand: sqrt(283.8^2 + 442.8^2))
        d = geo.haversine_m(6.5244, 3.3792, 9.0765, 7.3986) / 1000
        self.assertAlmostEqual(d, 526, delta=3)
        self.assertEqual(geo.haversine_m(1, 1, 1, 1), 0)
        # 1 degree of latitude ~ 111.2 km
        self.assertAlmostEqual(geo.haversine_m(0, 0, 1, 0) / 1000, 111.2, delta=0.3)

    def test_validate_point(self):
        self.assertEqual(geo.validate_point(6.5, 3.4, NG), (6.5, 3.4))
        for bad in [(91, 0), (0, 181), (float("nan"), 1), ("6", "3"), (True, 3), (51.5, -0.1)]:
            with self.assertRaises(ValidationFailed):
                geo.validate_point(*bad, NG)

    def test_bbox_contains_circle(self):
        min_lat, max_lat, min_lon, max_lon = geo.bbox_for_radius(13.0, 5.2, 10)
        for brg_lat, brg_lon in ((13.0, 5.2), (13.09, 5.2), (13.0, 5.29)):
            d = geo.haversine_m(13.0, 5.2, brg_lat, brg_lon)
            if d <= 10_000:
                self.assertTrue(min_lat <= brg_lat <= max_lat and min_lon <= brg_lon <= max_lon)
        with self.assertRaises(ValidationFailed):
            geo.bbox_for_radius(1, 1, 0)

    def test_polygon_parse_area_centroid(self):
        ring = geo.parse_polygon_geojson(SQUARE, NG)
        # 0.01deg x 0.01deg at 13N ~ 1.11km x 1.08km ~ 120 ha
        self.assertAlmostEqual(geo.ring_area_ha(ring), 120, delta=4)
        lat, lon = geo.ring_centroid(ring)
        self.assertAlmostEqual(lat, 13.005, places=3)
        self.assertAlmostEqual(lon, 5.205, places=3)

    def test_polygon_rejections(self):
        bad_cases = {
            "not polygon": {"type": "Point", "coordinates": [1, 2]},
            "unclosed": {"type": "Polygon", "coordinates": [[[5.2, 13], [5.21, 13], [5.21, 13.01], [5.2, 13.01]]]},
            "too few": {"type": "Polygon", "coordinates": [[[5.2, 13], [5.21, 13], [5.2, 13]]]},
            "hole": {"type": "Polygon", "coordinates": [SQUARE["coordinates"][0], SQUARE["coordinates"][0]]},
            "bowtie": {"type": "Polygon", "coordinates": [[[5.2, 13], [5.21, 13.01], [5.21, 13], [5.2, 13.01], [5.2, 13]]]},
            "outside region": {"type": "Polygon", "coordinates": [[[0, 51], [0.01, 51], [0.01, 51.01], [0, 51]]]},
            "degenerate line": {"type": "Polygon", "coordinates": [[[5.2, 13], [5.21, 13], [5.22, 13], [5.2, 13]]]},
        }
        for name, g in bad_cases.items():
            with self.subTest(name), self.assertRaises(ValidationFailed):
                geo.parse_polygon_geojson(g, NG)
        with self.assertRaises(ValidationFailed):
            geo.parse_polygon_geojson("{not json", NG)

    def test_point_in_ring_and_boundary(self):
        ring = geo.parse_polygon_geojson(SQUARE, NG)
        self.assertTrue(geo.point_in_ring(13.005, 5.205, ring))
        self.assertTrue(geo.point_in_ring(13.0, 5.205, ring))       # on edge
        self.assertFalse(geo.point_in_ring(13.02, 5.205, ring))

    def test_rings_intersect(self):
        a = geo.parse_polygon_geojson(SQUARE, NG)
        overlap = geo.parse_polygon_geojson({"type": "Polygon", "coordinates": [[[5.205, 13.005], [5.215, 13.005], [5.215, 13.015], [5.205, 13.015], [5.205, 13.005]]]}, NG)
        inside = geo.parse_polygon_geojson({"type": "Polygon", "coordinates": [[[5.203, 13.003], [5.207, 13.003], [5.207, 13.007], [5.203, 13.003]]]}, NG)
        far = geo.parse_polygon_geojson({"type": "Polygon", "coordinates": [[[6.0, 12.0], [6.01, 12.0], [6.01, 12.01], [6.0, 12.0]]]}, NG)
        self.assertTrue(geo.rings_intersect(a, overlap))
        self.assertTrue(geo.rings_intersect(a, inside))   # containment without edge crossing
        self.assertFalse(geo.rings_intersect(a, far))

    def test_distance_to_ring(self):
        ring = geo.parse_polygon_geojson(SQUARE, NG)
        self.assertEqual(geo.distance_to_ring_m(13.005, 5.205, ring), 0)
        d = geo.distance_to_ring_m(13.0, 5.19, ring)          # 0.01 deg west of the west edge ~ 1.08 km
        self.assertAlmostEqual(d, 1083, delta=25)


if __name__ == "__main__":
    unittest.main()
