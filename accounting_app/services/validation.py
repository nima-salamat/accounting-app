"""Shared validation for credentials, money values and quantities."""
import math

from accounting_app.config import PASSWORD_MIN_LENGTH, USERNAME_MIN_LENGTH


def validate_username(username):
    if not isinstance(username, str):
        raise ValueError("نام کاربری معتبر نیست.")
    value = username.strip()
    if len(value) < USERNAME_MIN_LENGTH:
        raise ValueError("نام کاربری باید حداقل ۴ نویسه داشته باشد.")
    return value


def validate_password(password):
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError("رمز عبور باید حداقل ۴ نویسه داشته باشد.")
    return password


def validate_money(value, field_name="مبلغ"):
    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("{} باید عددی معتبر باشد.".format(field_name)) from exc
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("{} نمی‌تواند منفی یا نامتناهی باشد.".format(field_name))
    return amount


def validate_quantity(quantity):
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("تعداد هر محصول باید عدد صحیح مثبت باشد.")
    return quantity
