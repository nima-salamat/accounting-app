import unittest

from accounting_app.services.validation import validate_money, validate_password, validate_quantity, validate_username


class ValidationTests(unittest.TestCase):
    def test_username_is_trimmed(self):
        self.assertEqual(validate_username("  admin  "), "admin")

    def test_short_credentials_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_username("abc")
        with self.assertRaises(ValueError):
            validate_password("abc")

    def test_money_requires_finite_non_negative_number(self):
        self.assertEqual(validate_money("12.5"), 12.5)
        for invalid in ("-1", "nan", "inf", None, "not money"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_money(invalid)

    def test_quantity_must_be_positive_integer_not_bool(self):
        self.assertEqual(validate_quantity(3), 3)
        for invalid in (0, -1, 1.0, True, "2"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_quantity(invalid)


if __name__ == "__main__":
    unittest.main()
