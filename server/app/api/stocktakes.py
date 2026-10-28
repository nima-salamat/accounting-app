"""Physical stocktakes with draft counts, reviewable variances and one-shot application."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from accounting_app.database.connection import DBManager
from accounting_app.database.models import Product, StockMovement, Stocktake, StocktakeLine
from accounting_app.services.accounting_controls import FiscalPeriodClosedError, ensure_period_open
from accounting_app.services.audit import record_audit
from server.app.permissions import require_permission
from server.app.schemas import StocktakeCountInput, StocktakeCreate

router = APIRouter(tags=["physical stocktake"])


def _stocktake_payload(take, include_lines=True):
    result = {
        "id": str(take.id),
        "name": take.name,
        "status": take.status,
        "notes": take.notes,
        "created_by_name": take.created_by_name,
        "created_at": take.created_at.isoformat(),
        "applied_at": take.applied_at.isoformat() if take.applied_at else None,
    }
    if include_lines:
        result["lines"] = [
            {
                "id": str(line.id),
                "product_id": str(line.product_id),
                "product_name": line.product.name,
                "expected_quantity": line.expected_quantity,
                "counted_quantity": line.counted_quantity,
                "difference": line.difference,
            }
            for line in StocktakeLine.select().where(
                StocktakeLine.stocktake == take.id
            ).order_by(StocktakeLine.created_at)
        ]
    return result


@router.get("/stocktakes")
def list_stocktakes(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    _user=Depends(require_permission("warehouse", "read")),
):
    with DBManager():
        query = Stocktake.select()
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [
            _stocktake_payload(take, include_lines=False)
            for take in query.order_by(Stocktake.created_at.desc()).paginate(page, page_size)
        ]


@router.get("/stocktakes/{stocktake_id}")
def get_stocktake(stocktake_id: UUID, _user=Depends(require_permission("warehouse", "read"))):
    with DBManager():
        take = Stocktake.get_or_none(Stocktake.id == stocktake_id)
        if take is None:
            raise HTTPException(status_code=404, detail="برگهٔ شمارش موجودی پیدا نشد.")
        return _stocktake_payload(take)


@router.post("/stocktakes", status_code=status.HTTP_201_CREATED)
def create_stocktake(
    payload: StocktakeCreate,
    user=Depends(require_permission("warehouse", "create")),
):
    with DBManager():
        products = {
            item.id: item for item in Product.select().where(Product.id.in_(payload.product_ids))
        }
        if len(products) != len(payload.product_ids):
            raise HTTPException(status_code=422, detail="یک یا چند کالا پیدا نشد.")
        untracked = [item.name for item in products.values() if not item.track_stock]
        if untracked:
            raise HTTPException(
                status_code=409,
                detail="رهگیری موجودی این کالاها خاموش است: {}. ابتدا رهگیری موجودی را فعال کنید.".format(
                    "، ".join(untracked[:8])
                ),
            )
        take = Stocktake.create(
            name=payload.name.strip(),
            status="draft",
            notes=payload.notes,
            created_by=user.id,
            created_by_name=user.username,
        )
        for product_id in payload.product_ids:
            product = products[product_id]
            expected = float(product.stock_quantity or 0)
            StocktakeLine.create(
                stocktake=take.id,
                product=product.id,
                expected_quantity=expected,
                counted_quantity=expected,
                difference=0,
            )
        record_audit(
            user, "stocktake.created", "warehouse", take.id,
            {"name": take.name, "product_count": len(payload.product_ids), "status": "draft"},
        )
        return _stocktake_payload(take)


@router.patch("/stocktakes/{stocktake_id}/lines/{line_id}")
def update_stocktake_count(
    stocktake_id: UUID,
    line_id: UUID,
    payload: StocktakeCountInput,
    user=Depends(require_permission("warehouse", "update")),
):
    with DBManager():
        take = Stocktake.get_or_none(Stocktake.id == stocktake_id)
        if take is None:
            raise HTTPException(status_code=404, detail="برگهٔ شمارش پیدا نشد.")
        if take.status != "draft":
            raise HTTPException(status_code=409, detail="برگهٔ اعمال‌شده قابل ویرایش نیست.")
        line = StocktakeLine.get_or_none(
            (StocktakeLine.id == line_id) & (StocktakeLine.stocktake == take.id)
        )
        if line is None:
            raise HTTPException(status_code=404, detail="ردیف شمارش پیدا نشد.")
        line.counted_quantity = float(payload.counted_quantity)
        line.difference = round(line.counted_quantity - line.expected_quantity, 4)
        line.save(only=[
            StocktakeLine.counted_quantity, StocktakeLine.difference, StocktakeLine.updated_at,
        ])
        record_audit(
            user, "stocktake.counted", "warehouse", take.id,
            {
                "line_id": str(line.id), "product_id": str(line.product_id),
                "expected": line.expected_quantity, "counted": line.counted_quantity,
                "difference": line.difference,
            },
        )
        return _stocktake_payload(take)


@router.post("/stocktakes/{stocktake_id}/apply")
def apply_stocktake(
    stocktake_id: UUID,
    user=Depends(require_permission("warehouse", "update")),
):
    try:
        with DBManager():
            ensure_period_open(date.today(), actor=user, action="تطبیق شمارش موجودی")
            take = Stocktake.get_or_none(Stocktake.id == stocktake_id)
            if take is None:
                raise HTTPException(status_code=404, detail="برگهٔ شمارش پیدا نشد.")
            if take.status != "draft":
                raise HTTPException(status_code=409, detail="این شمارش قبلاً اعمال شده یا لغو شده است.")
            lines = list(StocktakeLine.select().where(StocktakeLine.stocktake == take.id))
            if not lines:
                raise HTTPException(status_code=409, detail="برگهٔ شمارش خالی است.")
            applied = []
            for line in lines:
                product = Product.get_or_none(Product.id == line.product_id)
                if product is None:
                    raise HTTPException(status_code=409, detail="یکی از کالاهای شمارش حذف شده است.")
                if not product.track_stock:
                    raise HTTPException(status_code=409, detail="رهگیری موجودی یکی از کالاها غیرفعال شده است.")
                current = float(product.stock_quantity or 0)
                expected = float(line.expected_quantity)
                target = float(line.counted_quantity)
                if target < 0:
                    raise HTTPException(status_code=422, detail="موجودی شمارش‌شده نمی‌تواند منفی باشد.")
                if abs(current - expected) > 1e-9:
                    raise HTTPException(
                        status_code=409,
                        detail="موجودی «{}» پس از شروع شمارش تغییر کرده است؛ این برگه را اعمال نکنید. شمارش تازه‌ای بسازید یا پس از بررسی مدیریتی دوباره شمارش کنید.".format(product.name),
                    )
                delta = round(target - current, 4)
                if abs(delta) > 1e-9:
                    updated = Product.update(
                        stock_quantity=target
                    ).where(
                        (Product.id == product.id)
                        & (Product.track_stock == True)
                        & (Product.stock_quantity == current)
                    ).execute()
                    if not updated:
                        raise HTTPException(
                            status_code=409,
                            detail="موجودی «{}» هم‌زمان تغییر کرده است؛ برگه را بازبینی کنید.".format(product.name),
                        )
                    StockMovement.create(
                        product=product.id, user=user.id, performed_by=user.username,
                        quantity_change=delta, stock_before=current, stock_after=target,
                        reason="stocktake", reference_id=str(take.id),
                        notes="تطبیق شمارش فیزیکی موجودی",
                    )
                # Preserve the original system snapshot so the variance remains auditable.
                line.difference = round(target - expected, 4)
                line.save(only=[StocktakeLine.difference, StocktakeLine.updated_at])
                applied.append({
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "before": current,
                    "counted": target,
                    "difference": delta,
                })
            take.status = "applied"
            take.applied_at = datetime.now()
            take.save(only=[Stocktake.status, Stocktake.applied_at, Stocktake.updated_at])
            record_audit(
                user, "stocktake.applied", "warehouse", take.id,
                {
                    "name": take.name,
                    "line_count": len(lines),
                    "changed_count": sum(1 for item in applied if abs(item["difference"]) > 1e-9),
                    "changes": applied,
                },
            )
            return _stocktake_payload(take)
    except FiscalPeriodClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
