import json
import unittest

from bot import classify_availability, structured_availability


class AvailabilityTests(unittest.TestCase):
    def test_explicit_negative_wins(self):
        status, _ = classify_availability("Online nicht verfügbar. Weitere Produkte in den Warenkorb")
        self.assertFalse(status)

    def test_buy_button_means_available(self):
        status, _ = classify_availability("Produktdetails", buy_button_found=True)
        self.assertTrue(status)

    def test_unknown(self):
        status, _ = classify_availability("Nur technische Daten und Beschreibung")
        self.assertIsNone(status)

    def test_json_ld_in_stock(self):
        block = json.dumps({
            "@type": "Product",
            "offers": {"@type": "Offer", "availability": "https://schema.org/InStock", "price": "799", "priceCurrency": "EUR"},
        })
        status, _, price = structured_availability([block])
        self.assertTrue(status)
        self.assertEqual(price, "799 EUR")

    def test_json_ld_out_of_stock(self):
        block = json.dumps({"offers": {"availability": "https://schema.org/OutOfStock"}})
        status, _, _ = structured_availability([block])
        self.assertFalse(status)


if __name__ == "__main__":
    unittest.main()
