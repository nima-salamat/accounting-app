import unittest

from accounting_app.services.calculator import CalculatorExpressionError, evaluate_expression


class CalculatorTests(unittest.TestCase):
    def test_basic_arithmetic_and_precedence(self):
        self.assertEqual(evaluate_expression("2 + 3 * 4"), 14)
        self.assertEqual(evaluate_expression("(10 - 4) / 2"), 3)
        self.assertEqual(evaluate_expression("2 ** 5"), 32)

    def test_integer_looking_float_is_normalized(self):
        self.assertEqual(evaluate_expression("8 / 2"), 4)

    def test_rejects_python_execution_and_attributes(self):
        for expression in (
            "__import__('os').system('echo unsafe')",
            "().__class__",
            "open('/tmp/unsafe', 'w')",
        ):
            with self.subTest(expression=expression):
                with self.assertRaises(CalculatorExpressionError):
                    evaluate_expression(expression)

    def test_limits_exponents_and_expression_size(self):
        with self.assertRaises(CalculatorExpressionError):
            evaluate_expression("2 ** 1000")
        with self.assertRaises(CalculatorExpressionError):
            evaluate_expression("1" * 300)

    def test_division_by_zero_is_reported_as_calculator_error(self):
        with self.assertRaises(CalculatorExpressionError):
            evaluate_expression("1 / 0")


if __name__ == "__main__":
    unittest.main()
