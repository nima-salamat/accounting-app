"""A bounded arithmetic evaluator that never executes Python source code."""
import ast
import math
import operator


class CalculatorExpressionError(ValueError):
    """Raised when an expression is not an allowed arithmetic expression."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_EXPRESSION_LENGTH = 256
_MAX_NODES = 64
_MAX_ABS_VALUE = 1e100
_MAX_EXPONENT = 100


def _validate_result(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculatorExpressionError("نتیجه معتبر نیست.")
    if abs(value) > _MAX_ABS_VALUE or not math.isfinite(float(value)):
        raise CalculatorExpressionError("نتیجه بیش از حد بزرگ است.")
    return value


def evaluate_expression(expression):
    """Evaluate numbers and basic arithmetic while rejecting calls and attributes."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalculatorExpressionError("عبارت محاسباتی خالی است.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise CalculatorExpressionError("عبارت محاسباتی بیش از حد طولانی است.")
    try:
        root = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, MemoryError) as exc:
        raise CalculatorExpressionError("عبارت محاسباتی معتبر نیست.") from exc
    if len(list(ast.walk(root))) > _MAX_NODES:
        raise CalculatorExpressionError("عبارت محاسباتی بیش از حد پیچیده است.")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CalculatorExpressionError("فقط اعداد و عملگرهای ریاضی مجاز هستند.")
            if abs(value) > _MAX_ABS_VALUE:
                raise CalculatorExpressionError("عدد واردشده بیش از حد بزرگ است.")
            return value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
                raise CalculatorExpressionError("توان واردشده بیش از حد بزرگ است.")
            return _validate_result(_BINARY_OPERATORS[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _validate_result(_UNARY_OPERATORS[type(node.op)](visit(node.operand)))
        raise CalculatorExpressionError("این عملگر یا عبارت پشتیبانی نمی‌شود.")

    try:
        result = _validate_result(visit(root))
    except CalculatorExpressionError:
        raise
    except (ArithmeticError, OverflowError, ValueError, TypeError) as exc:
        raise CalculatorExpressionError("محاسبه امکان‌پذیر نیست.") from exc
    return int(result) if isinstance(result, float) and result.is_integer() else result
