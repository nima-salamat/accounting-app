"""Transactional sales endpoints, receipt reads, and idempotent sale creation."""
import hashlib
import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from peewee import ForeignKeyField, IntegrityError

from accounting_app.database.connection import DBManager
from accounting_app.database.models import (
    IdempotencyRecord, Product, Receipt, ReceiptProduct,
)
from accounting_app.services.sales import InsufficientStockError, record_sale
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
    result["items"] = [
        dict(_serialize(item), product_name=(item.product.name if item.product_id else "محصول حذف‌شده"))
        for item in ReceiptProduct.select().where(
            ReceiptProduct.receipt == receipt.id
        ).order_by(ReceiptProduct.created_at)
    ]
    return result


def _payload_hash(payload):
    canonical = {
        "paid": payload.paid,
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


@router.post("/sales", response_model=ReceiptDetailOut, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user=Depends(require_permission("sales", "create")),
):
    digest = _payload_hash(payload)
    replay = _get_replay(user, idempotency_key, digest)
    if replay is not None:
        return replay

    try:
        with DBManager():
            product_ids = [item.product_id for item in payload.items]
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
            receipt = record_sale(cart, user, payload.paid)
            IdempotencyRecord.create(
                key=idempotency_key,
                user=user.id,
                request_hash=digest,
                receipt=receipt.id,
            )
            return _receipt_detail(receipt)
    except InsufficientStockError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError:
        # A concurrent retry can win the unique (user, key) constraint.
        replay = _get_replay(user, idempotency_key, digest)
        if replay is not None:
            return replay
        raise HTTPException(status_code=409, detail="درخواست فروش هم‌زمان تداخل پیدا کرد؛ وضعیت را بازخوانی کنید.")


@router.put("/sales/{receipt_id}", response_model=ReceiptDetailOut)
def update_sale(receipt_id: UUID, payload: SaleCreate, user=Depends(require_permission("sales", "update"))):
    with DBManager():
        receipt = Receipt.get_or_none(Receipt.id == receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="رسید پیدا نشد.")
        if not user.is_admin and receipt.user_id != user.id:
            raise HTTPException(status_code=403, detail="اجازه ویرایش این رسید را ندارید.")
        product_ids = [item.product_id for item in payload.items]
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
                cart, user, payload.paid, edit_mode=True, receipt_to_edit=receipt
            )
        except InsufficientStockError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _receipt_detail(updated)


@router.get("/receipts", response_model=List[ReceiptOut])
def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    user=Depends(require_permission("receipts", "read")),
):
    with DBManager():
        query = Receipt.select()
        if not user.is_admin:
            query = query.where(Receipt.user == user.id)
        return [_serialize(item) for item in query.order_by(Receipt.created_at.desc()).paginate(page, page_size)]


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
