"""Receipt-linked returns and refunds with quantity limits, stock restoration and audit logging."""
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from peewee import fn

from accounting_app.database.connection import DBManager
from accounting_app.database.models import (
    Product, Receipt, ReceiptProduct, SaleReturn, SaleReturnLine, StockMovement,
)
from accounting_app.services.accounting_controls import FiscalPeriodClosedError, ensure_period_open
from accounting_app.services.audit import record_audit
from server.app.dependencies import get_current_user
from server.app.permissions import require_permission
from server.app.schemas import SaleReturnCreate

router = APIRouter(tags=["returns and refunds"])


def _return_payload(item, include_lines=True):
    result = {
        "id": str(item.id),
        "receipt_id": str(item.receipt_id),
        "day_receipt_id": item.receipt.day_receipt_id,
        "operator_name": item.operator_name,
        "user_id": str(item.user_id) if item.user_id else None,
        "refund_method": item.refund_method,
        "reason": item.reason,
        "total_amount": str(item.total_amount),
        "notes": item.notes,
        "created_at": item.created_at.isoformat(),
    }
    if include_lines:
        result["items"] = [
            {
                "id": str(line.id),
                "original_line_id": str(line.original_line_id),
                "product_id": str(line.product_id) if line.product_id else None,
                "product_name": line.product_name,
                "quantity": line.quantity,
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
            }
            for line in SaleReturnLine.select().where(
                SaleReturnLine.sale_return == item.id
            ).order_by(SaleReturnLine.created_at)
        ]
    return result


@router.get("/returns")
def list_returns(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    user=Depends(require_permission("returns", "read")),
):
    with DBManager():
        query = SaleReturn.select().join(Receipt)
        if not user.is_admin:
            query = query.where(SaleReturn.user == user.id)
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [
            _return_payload(item, include_lines=False)
            for item in query.order_by(SaleReturn.created_at.desc()).paginate(page, page_size)
        ]


@router.get("/returns/{return_id}")
def get_return(return_id: UUID, user=Depends(require_permission("returns", "read"))):
    with DBManager():
        item = SaleReturn.get_or_none(SaleReturn.id == return_id)
        if item is None:
            raise HTTPException(status_code=404, detail="سند مرجوعی پیدا نشد.")
        if not user.is_admin and item.user_id != user.id:
            raise HTTPException(status_code=403, detail="اجازه مشاهده این سند مرجوعی را ندارید.")
        return _return_payload(item)


@router.post("/returns", status_code=status.HTTP_201_CREATED)
def create_return(
    payload: SaleReturnCreate,
    user=Depends(require_permission("returns", "create")),
    _receipt_access=Depends(require_permission("receipts", "read")),
):
    now = date.today()
    try:
        with DBManager():
            ensure_period_open(now, actor=user, action="مرجوعی / استرداد")
            receipt = Receipt.get_or_none(Receipt.id == payload.receipt_id)
            if receipt is None:
                raise HTTPException(status_code=404, detail="فاکتور اصلی پیدا نشد.")
            if not user.is_admin and receipt.user_id != user.id:
                raise HTTPException(status_code=403, detail="فقط مدیر یا ثبت‌کننده فاکتور اجازه ثبت مرجوعی آن را دارد.")

            normalized = []
            total = Decimal("0")
            for requested in payload.items:
                line = ReceiptProduct.get_or_none(ReceiptProduct.id == requested.original_line_id)
                if line is None or line.receipt_id != receipt.id:
                    raise HTTPException(status_code=422, detail="یک ردیف انتخاب‌شده متعلق به فاکتور اصلی نیست.")
                already_returned = (
                    SaleReturnLine.select(fn.COALESCE(fn.SUM(SaleReturnLine.quantity), 0))
                    .where(SaleReturnLine.original_line == line.id)
                    .scalar() or 0
                )
                remaining = int(line.quantity) - int(already_returned)
                if requested.quantity > remaining:
                    raise HTTPException(
                        status_code=409,
                        detail="برای «{}» فقط {} عدد قابل مرجوعی باقی مانده است.".format(
                            line.product_name or "کالای فاکتور", max(0, remaining)
                        ),
                    )
                unit_price = Decimal(str(line.sell_price)).quantize(Decimal("0.01"))
                amount = unit_price * requested.quantity
                total += amount
                normalized.append((line, requested.quantity, unit_price, amount))

            return_record = SaleReturn.create(
                receipt=receipt.id,
                user=user.id,
                operator_name=user.username,
                refund_method=payload.refund_method,
                reason=payload.reason,
                total_amount=total,
                notes=payload.notes,
            )
            for line, quantity, unit_price, amount in normalized:
                SaleReturnLine.create(
                    sale_return=return_record.id,
                    original_line=line.id,
                    product=line.product_id,
                    product_name=line.product_name or (line.product.name if line.product_id else "محصول حذف‌شده"),
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=amount,
                )
                product = Product.get_or_none(Product.id == line.product_id) if line.product_id else None
                if product is not None and product.track_stock:
                    before = float(product.stock_quantity or 0)
                    Product.update(
                        stock_quantity=Product.stock_quantity + quantity
                    ).where(Product.id == product.id).execute()
                    product = Product.get_by_id(product.id)
                    StockMovement.create(
                        product=product.id,
                        user=user.id,
                        performed_by=user.username,
                        quantity_change=float(quantity),
                        stock_before=before,
                        stock_after=float(product.stock_quantity),
                        reason="return",
                        reference_id=str(return_record.id),
                        notes="بازگشت موجودی ناشی از مرجوعی فروش",
                    )
            record_audit(
                user, "return.created", "returns", return_record.id,
                {
                    "receipt_id": str(receipt.id),
                    "day_receipt_id": receipt.day_receipt_id,
                    "total_amount": str(total),
                    "refund_method": payload.refund_method,
                    "reason": payload.reason,
                    "line_count": len(normalized),
                    "quantities": [
                        {"original_line_id": str(line.id), "quantity": quantity}
                        for line, quantity, _price, _amount in normalized
                    ],
                },
            )
            return _return_payload(return_record)
    except FiscalPeriodClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
