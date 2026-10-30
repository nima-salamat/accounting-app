"""Transactional sales endpoints, receipt reads, and idempotent sale creation."""
import hashlib
import json
from typing import List, Optional
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from peewee import ForeignKeyField, IntegrityError, fn

from accounting_app.database.connection import DBManager
from accounting_app.services.kiosk_config import enforce_kiosk_products, load_kiosk_settings, validate_kiosk_seat
from accounting_app.database.models import (
    IdempotencyRecord, Product, Receipt, ReceiptProduct, SaleReturnLine,
)
from accounting_app.services.sales import InsufficientStockError, record_sale
from accounting_app.services.accounting_controls import FiscalPeriodClosedError
from accounting_app.services.schema_registry import cleanup_builtin_extension_values_many
from server.app.dependencies import get_current_user
from server.app.permissions import require_permission
from server.app.schemas import ReceiptDetailOut, ReceiptOut, SaleCreate

router = APIRouter(tags=["sales"])


def _serialize(record):
    result = {}
    for name, field in record._meta.fields.items():
        if isinstance(field, ForeignKeyField):
            key, value = name + "_id", getattr(record, name + "_id")
        else:
            key, value = name, getattr(record, name)
        result[key] = str(value) if isinstance(value, UUID) else value
    return result


def _receipt_detail(receipt):
    result = _serialize(receipt)
    returned = {
        str(row["original_line_id"]): int(row["total"] or 0)
        for row in (
            SaleReturnLine.select(
                SaleReturnLine.original_line.alias("original_line_id"),
                fn.SUM(SaleReturnLine.quantity).alias("total"),
            )
            .join(ReceiptProduct, on=(SaleReturnLine.original_line == ReceiptProduct.id))
            .where(ReceiptProduct.receipt == receipt.id)
            .group_by(SaleReturnLine.original_line)
            .dicts()
        )
    }
    result["items"] = []
    for item in ReceiptProduct.select().where(
        ReceiptProduct.receipt == receipt.id
    ).order_by(ReceiptProduct.created_at):
        returned_quantity = returned.get(str(item.id), 0)
        result["items"].append(dict(
            _serialize(item),
            product_name=(item.product_name or (item.product.name if item.product_id else "محصول حذف‌شده")),
            returned_quantity=returned_quantity,
            returnable_quantity=max(0, int(item.quantity) - returned_quantity),
        ))
    return result


def _apply_receipt_filters(query, *, q=None, payed_filter=None, start_date=None, end_date=None):
    """Apply consistent, server-side search and filters to receipt queries."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="تاریخ شروع نباید بعد از تاریخ پایان باشد.")
    if payed_filter == "paid":
        query = query.where(Receipt.payed == True)
    elif payed_filter == "unpaid":
        query = query.where(Receipt.payed == False)
    if start_date is not None:
        query = query.where(Receipt.created_at >= datetime.combine(start_date, time.min))
    if end_date is not None:
        query = query.where(Receipt.created_at < datetime.combine(end_date + timedelta(days=1), time.min))

    term = str(q or "").strip()
    if not term:
        return query
    normalized = term.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    search_filter = (
        Receipt.day_receipt_id.cast("text").contains(term)
        | Receipt.invoice_number.contains(term)
        | Receipt.id.cast("text").contains(term)
        | Receipt.seat_number.contains(term)
        | Receipt.payment_method.contains(term)
        | Receipt.created_at.cast("text").contains(term)
        | Receipt.total_price.cast("text").contains(term)
        | Receipt.id.in_(
            ReceiptProduct.select(ReceiptProduct.receipt).where(
                ReceiptProduct.product_name.contains(term)
            )
        )
    )
    for label, method in (
        ("نقدی", "cash"),
        ("کارت", "card"),
        ("انتقال بانکی", "bank_transfer"),
        ("اعتباری", "store_credit"),
    ):
        if normalized and normalized in label:
            search_filter |= Receipt.payment_method == method
    if "پرداخت" in normalized and ("نشده" in normalized or "نشد" in normalized):
        search_filter |= Receipt.payed == False
    elif "پرداخت" in normalized and "شده" in normalized:
        search_filter |= Receipt.payed == True
    return query.where(search_filter)


def _sort_receipts(query, *, sort_by="created_at", sort_order="desc"):
    """Sort using a strict whitelist so user input never becomes a SQL expression."""
    columns = {
        "created_at": Receipt.created_at,
        "total_price": Receipt.total_price,
        "day_receipt_id": Receipt.day_receipt_id,
        "invoice_number": Receipt.invoice_number,
    }
    sort_key = str(sort_by or "created_at")
    if sort_key not in columns:
        sort_key = "created_at"
    column = columns[sort_key]
    descending = str(sort_order or "desc").lower() != "asc"
    primary = column.desc() if descending else column.asc()
    if sort_key == "created_at":
        return query.order_by(primary)
    return query.order_by(primary, Receipt.created_at.desc())


def _payload_hash(payload):
    canonical = {
        "paid": payload.paid,
        "payment_method": payload.payment_method,
        "seat_number": payload.seat_number,
        "items": sorted(
            [
                {"product_id": str(item.product_id), "quantity": item.quantity}
                for item in payload.items
            ],
            key=lambda item: item["product_id"],
        ),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _get_replay(user, key, digest):
    with DBManager():
        prior = IdempotencyRecord.get_or_none(
            (IdempotencyRecord.user == user.id) & (IdempotencyRecord.key == key)
        )
        if prior is None:
            return None
        if prior.request_hash != digest:
            raise HTTPException(
                status_code=409,
                detail="این Idempotency-Key قبلاً برای درخواست متفاوتی استفاده شده است.",
            )
        receipt = Receipt.get_or_none(Receipt.id == prior.receipt_id)
        if receipt is None:
            raise HTTPException(status_code=409, detail="رسید مربوط به درخواست قبلی دیگر موجود نیست.")
        return _receipt_detail(receipt)


@router.post("/sales/quote")
def quote_sale(
    payload: SaleCreate,
    user=Depends(require_permission("sales", "create")),
    _catalog_access=Depends(require_permission("products", "read")),
):
    """Return server-authoritative totals before a payment terminal is charged."""
    from decimal import Decimal
    from datetime import date
    from accounting_app.services.accounting_controls import FiscalPeriodClosedError, ensure_period_open

    try:
        with DBManager():
            ensure_period_open(date.today(), actor=user, action="فروش")
            product_ids = [item.product_id for item in payload.items]
            enforce_kiosk_products(user, product_ids)
            validate_kiosk_seat(user, payload.seat_number)
            products = {
                product.id: product
                for product in Product.select().where(Product.id.in_(product_ids))
            }
            if len(products) != len(product_ids):
                raise HTTPException(status_code=422, detail="یک یا چند محصول وجود ندارد.")
            items = []
            total = Decimal("0")
            for requested in payload.items:
                product = products[requested.product_id]
                if product.track_stock and float(product.stock_quantity or 0) < requested.quantity:
                    raise HTTPException(
                        status_code=409,
                        detail="موجودی کالای «{}» برای این تعداد کافی نیست.".format(product.name),
                    )
                unit_price = Decimal(str(product.sell_price)).quantize(Decimal("0.01"))
                line_total = unit_price * requested.quantity
                total += line_total
                items.append({
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "quantity": requested.quantity,
                    "unit_price": str(unit_price),
                    "line_total": str(line_total),
                })
            return {"total": str(total), "items": items, "currency": "LOCAL"}
    except FiscalPeriodClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sales", response_model=ReceiptDetailOut, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user=Depends(require_permission("sales", "create")),
    _catalog_access=Depends(require_permission("products", "read")),
):
    digest = _payload_hash(payload)
    replay = _get_replay(user, idempotency_key, digest)
    if replay is not None:
        return replay

    try:
        with DBManager():
            product_ids = [item.product_id for item in payload.items]
            enforce_kiosk_products(user, product_ids)
            validate_kiosk_seat(user, payload.seat_number)
            products = {
                product.id: product
                for product in Product.select().where(Product.id.in_(product_ids))
            }
            if len(products) != len(product_ids):
                raise HTTPException(status_code=422, detail="یک یا چند محصول وجود ندارد.")
            cart = {
                product_id: (products[product_id], item.quantity)
                for product_id, item in ((item.product_id, item) for item in payload.items)
            }
            receipt = record_sale(cart, user, payload.paid, payment_method=payload.payment_method)
            receipt.seat_number = payload.seat_number.strip() if payload.seat_number else None
            receipt.save(only=[Receipt.seat_number, Receipt.updated_at])
            IdempotencyRecord.create(
                key=idempotency_key,
                user=user.id,
                request_hash=digest,
                receipt=receipt.id,
            )
            return _receipt_detail(receipt)
    except (InsufficientStockError, FiscalPeriodClosedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError:
        # A concurrent retry can win the unique (user, key) constraint.
        replay = _get_replay(user, idempotency_key, digest)
        if replay is not None:
            return replay
        raise HTTPException(status_code=409, detail="درخواست فروش هم‌زمان تداخل پیدا کرد؛ وضعیت را بازخوانی کنید.")


@router.put("/sales/{receipt_id}", response_model=ReceiptDetailOut)
def update_sale(
    receipt_id: UUID, payload: SaleCreate,
    user=Depends(require_permission("sales", "update")),
    _catalog_access=Depends(require_permission("products", "read")),
):
    with DBManager():
        receipt = Receipt.get_or_none(Receipt.id == receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="رسید پیدا نشد.")
        if not user.is_admin and receipt.user_id != user.id:
            raise HTTPException(status_code=403, detail="اجازه ویرایش این رسید را ندارید.")
        product_ids = [item.product_id for item in payload.items]
        validate_kiosk_seat(user, payload.seat_number)
        products = {
            product.id: product
            for product in Product.select().where(Product.id.in_(product_ids))
        }
        if len(products) != len(product_ids):
            raise HTTPException(status_code=422, detail="یک یا چند محصول وجود ندارد.")
        cart = {
            item.product_id: (products[item.product_id], item.quantity)
            for item in payload.items
        }
        try:
            updated = record_sale(
                cart, user, payload.paid, edit_mode=True, receipt_to_edit=receipt,
                payment_method=payload.payment_method,
            )
        except (InsufficientStockError, FiscalPeriodClosedError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        updated.seat_number = payload.seat_number.strip() if payload.seat_number else None
        updated.save(only=[Receipt.seat_number, Receipt.updated_at])
        return _receipt_detail(updated)


@router.get("/sales/recent-receipts")
def list_recent_receipts(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=200),
    payed_filter: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user=Depends(require_permission("receipts", "read")),
):
    """Receipts within the configured history window, optionally filtered and sorted."""
    with DBManager():
        hours = load_kiosk_settings()["receipt_history_hours"]
        cutoff = datetime.now() - timedelta(hours=hours)
        query = Receipt.select().where(Receipt.created_at >= cutoff)
        if not user.is_admin:
            query = query.where(Receipt.user == user.id)

        query = _apply_receipt_filters(
            query, q=q, payed_filter=payed_filter, start_date=start_date, end_date=end_date
        )

        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-History-Hours"] = str(hours)
        return [
            _serialize(item)
            for item in _sort_receipts(query, sort_by=sort_by, sort_order=sort_order).paginate(page, page_size)
        ]


@router.get("/receipts", response_model=List[ReceiptOut])
def list_receipts(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=200),
    payed_filter: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user=Depends(require_permission("receipts", "read")),
):
    with DBManager():
        query = Receipt.select()
        if not user.is_admin:
            query = query.where(Receipt.user == user.id)
        query = _apply_receipt_filters(
            query, q=q, payed_filter=payed_filter, start_date=start_date, end_date=end_date
        )
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        ordered = _sort_receipts(query, sort_by=sort_by, sort_order=sort_order)
        return [_serialize(item) for item in ordered.paginate(page, page_size)]


@router.get("/receipts/{receipt_id}", response_model=ReceiptDetailOut)
def get_receipt(receipt_id: UUID, user=Depends(require_permission("receipts", "read"))):
    with DBManager():
        receipt = Receipt.get_or_none(Receipt.id == receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="رسید پیدا نشد.")
        if not user.is_admin and receipt.user_id != user.id:
            raise HTTPException(status_code=403, detail="اجازه مشاهده این رسید را ندارید.")
        return _receipt_detail(receipt)


@router.delete("/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_receipt(receipt_id: UUID, user=Depends(require_permission("receipts", "delete"))):
    with DBManager():
        receipt = Receipt.get_or_none(Receipt.id == receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="رسید پیدا نشد.")
        if not user.is_admin and receipt.user_id != user.id:
            raise HTTPException(status_code=403, detail="اجازه حذف این رسید را ندارید.")
        item_ids = [
            item.id for item in ReceiptProduct.select().where(
                ReceiptProduct.receipt == receipt.id
            )
        ]
        cleanup_builtin_extension_values_many("receipt_products", item_ids)
        cleanup_builtin_extension_values_many("receipts", [receipt.id])
        if item_ids:
            ReceiptProduct.delete().where(ReceiptProduct.id.in_(item_ids)).execute()
        receipt.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
