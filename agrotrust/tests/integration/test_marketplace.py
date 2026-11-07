import unittest

from agrotrust.modules.marketplace.service import MarketplaceService
from agrotrust.security.permissions import Role
from agrotrust.shared.errors import (Conflict, NotFound, UnauthorizedResourceAccess, ValidationFailed)
from tests.helpers_ctx import CtxTestCase, insert_crop, insert_user, make_principal


class MarketplaceTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.market = MarketplaceService(self.ctx)
        self.crop = insert_crop(self.db, "MAIZE")
        insert_user(self.db, "farmer1", "11111")
        insert_user(self.db, "buyer1", "22222")
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.buyer = make_principal("buyer1", Role.BUYER)

    def _listing(self, qty="100", price="500", **kw):
        return self.market.create_listing(self.farmer, crop_id=self.crop, title="Fresh Maize", quantity=qty,
                                          unit="KG", price=price, state="Oyo", lga="Ibadan North", **kw)

    def test_create_and_search(self):
        l = self._listing()
        self.assertEqual(l["quantity_available"], "100.000")
        found = self.market.search(text="maize")
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["items"][0]["id"], l["id"])
        self.assertEqual(self.market.search(text="rice")["total"], 0)

    def test_buyer_cannot_create(self):
        from agrotrust.shared.errors import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.market.create_listing(self.buyer, crop_id=self.crop, title="x", quantity="1", unit="KG",
                                       price="1", state="Oyo", lga="Ibadan")

    def test_validation(self):
        with self.assertRaises(ValidationFailed):
            self._listing(qty="0")
        with self.assertRaises(ValidationFailed):
            self._listing(price="0")
        with self.assertRaises(ValidationFailed):
            self.market.create_listing(self.farmer, crop_id=self.crop, title="a", quantity="1", unit="KG",
                                       price="1", state="Oyo", lga="Ibadan")

    def test_geo_filter(self):
        near = self._listing()
        with self.db.transaction():
            self.db.execute("UPDATE listings SET lat=7.3775, lon=3.9470 WHERE id=?", (near["id"],))  # Ibadan
        far = self._listing()
        with self.db.transaction():
            self.db.execute("UPDATE listings SET lat=9.0765, lon=7.3986 WHERE id=?", (far["id"],))  # Abuja
        res = self.market.search(near=(7.3775, 3.9470, 50_000))
        ids = [i["id"] for i in res["items"]]
        self.assertIn(near["id"], ids)
        self.assertNotIn(far["id"], ids)

    def test_reserve_cannot_oversell_concurrently(self):
        import threading
        l = self._listing(qty="10")
        ok = []
        def go():
            try:
                with self.db.transaction():
                    self.market.reserve(l["id"], 4000)  # 4 kg in milli
                ok.append(1)
            except Conflict:
                ok.append(0)
        ts = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(ok), 2)
        row = self.db.one("SELECT quantity_available_milli, status FROM listings WHERE id=?", (l["id"],))
        self.assertEqual(row["quantity_available_milli"], 2000)

    def test_ownership_and_pause(self):
        l = self._listing()
        with self.assertRaises(UnauthorizedResourceAccess):
            self.market.set_status(self.buyer, l["id"], "PAUSED")
        self.market.set_status(self.farmer, l["id"], "PAUSED")
        self.assertEqual(self.market.search(text="maize")["total"], 0)  # paused hidden from search


if __name__ == "__main__":
    unittest.main()
