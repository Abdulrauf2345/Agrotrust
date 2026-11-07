import unittest
from decimal import Decimal

from agrotrust.shared.errors import ValidationFailed
from agrotrust.shared.money import Money, from_milli, line_total_minor, to_milli


class MoneyTests(unittest.TestCase):
    def test_from_decimal_exact(self):
        self.assertEqual(Money.from_decimal("100000").minor, 10_000_000)
        self.assertEqual(Money.from_decimal("0.10").minor, 10)
        self.assertEqual(str(Money.from_decimal("1234.5")), "NGN 1,234.50")

    def test_floats_rejected(self):
        with self.assertRaises(ValidationFailed):
            Money.from_decimal(0.1)

    def test_more_than_two_decimals_rejected_not_rounded(self):
        with self.assertRaises(ValidationFailed):
            Money.from_decimal("1.005")

    def test_arithmetic_and_currency_mismatch(self):
        a, b = Money(500), Money(250)
        self.assertEqual((a + b).minor, 750)
        self.assertEqual((a - b).minor, 250)
        with self.assertRaises(ValidationFailed):
            a + Money(1, "USD")

    def test_no_float_drift(self):
        total = sum((Money.from_decimal("0.10") for _ in range(10)), Money(0))
        self.assertEqual(total, Money.from_decimal("1.00"))

    def test_bps_bankers_rounding(self):
        self.assertEqual(Money(150).bps(100).minor, 2)   # 1.5 -> 2 (even)
        self.assertEqual(Money(250).bps(100).minor, 2)   # 2.5 -> 2 (even)
        self.assertEqual(Money(10_000_000).bps(150).minor, 150_000)

    def test_quantity(self):
        self.assertEqual(to_milli("12.5"), 12_500)
        self.assertEqual(from_milli(12_500), Decimal("12.500"))
        with self.assertRaises(ValidationFailed):
            to_milli("1.0001")
        with self.assertRaises(ValidationFailed):
            to_milli(1.5)

    def test_line_total(self):
        # 250.00 NGN/kg * 12.5 kg = 3125.00
        self.assertEqual(line_total_minor(25_000, 12_500), 312_500)
        # half-even at the kobo boundary: 1 kobo * 0.5 = 0.5 -> 0 ; 1 * 1.5 -> 2
        self.assertEqual(line_total_minor(1, 500), 0)
        self.assertEqual(line_total_minor(1, 1500), 2)
        self.assertEqual(line_total_minor(1, 2500), 2)


if __name__ == "__main__":
    unittest.main()
