"""Small helpers shared by receipt and invoice history widgets."""


def receipt_is_paid(value):
    """Interpret JSON booleans and legacy textual statuses without treating 'false' as true."""
    if isinstance(value, str):
        return value.strip().casefold() in {
            "1", "true", "yes", "paid", "بله", "پرداخت‌شده", "پرداخت شده",
        }
    return bool(value)
