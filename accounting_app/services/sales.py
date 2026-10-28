"""Transactional sales operations shared by checkout workers and tests."""
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from peewee import fn

from accounting_app.database.connection import DBManager
from accounting_app.database.models import Receipt, ReceiptProduct
from accounting_app.services.validation import validate_money, validate_quantity


def record_sale(cart, user, payed, *, edit_mode=False, receipt_to_edit=None):
    """Atomically create or update a receipt and all of its line items."""
    if not cart:
        raise ValueError("سبد خرید خالی است.")
    if user is None or getattr(user, "id", None) is None:
        raise ValueError("برای ثبت فروش باید کاربر واردشده معتبر باشد.")
    if edit_mode and receipt_to_edit is None:
        raise ValueError("رسید موردنظر برای ویرایش مشخص نشده است.")

    normalized_items = []
    total = Decimal("0")
    for product, quantity in cart.values():
        quantity = validate_quantity(quantity)
        buy_price = validate_money(getattr(product, "buy_price", None), "قیمت خرید")
        sell_price = validate_money(getattr(product, "sell_price", None), "قیمت فروش")
        product_id = getattr(product, "id", None)
        if product_id is None:
            raise ValueError("یکی از محصولات سبد خرید شناسه معتبر ندارد.")
        try:
            total += Decimal(str(sell_price)) * quantity
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("محاسبه مبلغ فاکتور نامعتبر است.") from exc
        normalized_items.append((product_id, buy_price, sell_price, quantity))

    now = datetime.now()
    day_start = datetime.combine(now.date(), time.min)
    next_day = day_start + timedelta(days=1)

    with DBManager():
        if edit_mode:
            receipt = Receipt.get_by_id(receipt_to_edit.id)
            receipt.user = user
            receipt.payed = bool(payed)
            receipt.total_price = float(total)
            receipt.save()
            ReceiptProduct.delete().where(ReceiptProduct.receipt == receipt).execute()
        else:
            highest_daily_id = (
                Receipt.select(fn.MAX(Receipt.day_receipt_id))
                .where(Receipt.created_at >= day_start, Receipt.created_at < next_day)
                .scalar()
                or 0
            )
            receipt = Receipt.create(
                user=user,
                payed=bool(payed),
                total_price=float(total),
                day_receipt_id=int(highest_daily_id) + 1,
            )

        ReceiptProduct.insert_many([
            {
                "receipt": receipt.id,
                "product": product_id,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "quantity": quantity,
            }
            for product_id, buy_price, sell_price, quantity in normalized_items
        ]).execute()
    return receipt
