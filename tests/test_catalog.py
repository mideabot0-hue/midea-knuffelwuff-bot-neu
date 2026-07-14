import json
import unittest

from bot import CatalogItem, compare_catalog_items, structured_catalog_items


class CatalogTests(unittest.TestCase):
    def item(self, key: str, available):
        return CatalogItem(
            key=key,
            name=f"Produkt {key}",
            url=f"https://www.knuffelwuff.de/{key}",
            available=available,
        )

    def test_first_run_does_not_notify(self):
        current = {"one": self.item("one", True)}
        self.assertEqual(compare_catalog_items(current, {}, initialized=False), [])

    def test_new_available_product_notifies(self):
        current = {"one": self.item("one", True)}
        events = compare_catalog_items(current, {}, initialized=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "new")

    def test_new_unavailable_product_does_not_notify(self):
        current = {"one": self.item("one", False)}
        self.assertEqual(compare_catalog_items(current, {}, initialized=True), [])

    def test_restock_notifies(self):
        current = {"one": self.item("one", True)}
        old = {"one": {"available": False}}
        events = compare_catalog_items(current, old, initialized=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "restocked")

    def test_still_available_does_not_notify(self):
        current = {"one": self.item("one", True)}
        old = {"one": {"available": True}}
        self.assertEqual(compare_catalog_items(current, old, initialized=True), [])

    def test_extracts_json_ld_product(self):
        block = json.dumps({
            "@type": "Product",
            "name": "Knuffelwuff Hundebett Test",
            "url": "/Hundebett-Test",
            "offers": {
                "availability": "https://schema.org/InStock",
                "price": "49.95",
                "priceCurrency": "EUR",
            },
        })
        items = structured_catalog_items([block], "https://www.knuffelwuff.de/Schlafplatz")
        self.assertEqual(len(items), 1)
        item = next(iter(items.values()))
        self.assertTrue(item.available)
        self.assertEqual(item.price, "49.95 EUR")
        self.assertEqual(item.url, "https://www.knuffelwuff.de/Hundebett-Test")


if __name__ == "__main__":
    unittest.main()
