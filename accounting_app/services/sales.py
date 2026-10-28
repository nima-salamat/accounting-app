"""Transactional sales operations shared by checkout workers and tests."""
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import uuid

from peewee import fn

from accounting_app.database.connection import DBManager
from accounting_app.database.models import Product, Receipt, ReceiptProduct, StockMovement
from accounting_app.services.validation import validate_money, validate_quantity
from accounting_app.services.audit import record_audit
from accounting_app.services.accounting_controls import ensure_period_open


class InsufficientStockError(ValueError):
    """Raised when a tracked item does not have enough available stock."""


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
        normalized_items.append((product_id, buy_price, sell_price, quantity, str(getattr(product, "name", ""))))

    now = datetime.now()
    day_start = datetime.combine(now.date(), time.min)
    next_day = day_start + timedelta(days=1)

    with DBManager():
        ensure_period_open(now.date(), actor=user, action="sale")
        if edit_mode:
            receipt = Receipt.get_by_id(receipt_to_edit.id)
            # Reverse only the inventory movements previously recorded for this receipt.
            # A net negative movement means stock was consumed by the earlier version.
            previous = {}
            for movement in StockMovement.select().where(
                (StockMovement.reference_id == str(receipt.id))
                & StockMovement.reason.in_(("sale", "sale_edit_restore", "sale_edit_issue"))
            ):
                previous[movement.product_id] = previous.get(movement.product_id, 0.0) + float(movement.quantity_change)
            for product_id, net_change in previous.items():
                if abs(net_change) < 1e-9:
                    continue
                product = Product.get_or_none(Product.id == product_id)
                if product is None:
                    continue
                before = float(product.stock_quantity or 0)
                after = before - net_change
                product.stock_quantity = after
                product.save(only=[Product.stock_quantity, Product.updated_at])
                StockMovement.create(
                    product=product.id, user=user.id, performed_by=user.username,
                    quantity_change=-net_change, stock_before=before, stock_after=after,
                    reason="sale_edit_restore", reference_id=str(receipt.id),
                    notes="برگشت اثر نسخهٔ قبلی رسید برای ویرایش",
                )
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

        # Conditional SQL update protects against two clients selling the same final units.
        for product_id, _buy_price, _sell_price, quantity, _product_name in normalized_items:
            product = Product.get_by_id(product_id)
            if not product.track_stock:
                continue
            before = float(product.stock_quantity or 0)
            changed = Product.update(
                stock_quantity=Product.stock_quantity - quantity
            ).where(
                (Product.id == product_id)
                & (Product.track_stock == True)
                & (Product.stock_quantity >= quantity)
            ).execute()
            if not changed:
                available = Product.get_by_id(product_id).stock_quantity
                raise InsufficientStockError(
                    "موجودی «{}» کافی نیست؛ موجودی فعلی {} و تعداد درخواستی {} است.".format(
                        product.name, available, quantity
                    )
                )
            updated_product = Product.get_by_id(product_id)
            StockMovement.create(
                product=product_id, user=user.id, performed_by=user.username,
                quantity_change=-float(quantity), stock_before=before,
                stock_after=float(updated_product.stock_quantity),
                reason="sale_edit_issue" if edit_mode else "sale",
                reference_id=str(receipt.id),
                notes="مصرف موجودی هنگام ثبت فروش",
            )

        ReceiptProduct.insert_many([
            {
                # Bulk inserts bypass the per-model defaults, so provide all BaseModel fields.
                "id": uuid.uuid4(),
                "created_at": now,
                "updated_at": now,
                "receipt": receipt.id,
                "product": product_id,
                "product_name": product_name,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "quantity": quantity,
            }
            for product_id, buy_price, sell_price, quantity, product_name in normalized_items
        ]).execute()
        record_audit(
            user,
            action="sale.updated" if edit_mode else "sale.created",
            resource="sales",
            target_id=receipt.id,
            details={
                "day_receipt_id": receipt.day_receipt_id,
                "total_price": str(total),
                "paid": bool(payed),
                "line_count": len(normalized_items),
                "tracked_quantity": sum(quantity for _pid, _buy, _sell, quantity, _name in normalized_items),
            },
        )
    return receipt
