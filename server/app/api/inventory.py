"""Inventory browsing, movement history and audited stock adjustments."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from accounting_app.database.connection import DBManager
from accounting_app.database.models import Product, StockMovement, User
from server.app.permissions import require_permission
from server.app.schemas import InventoryAdjustmentInput, ProductOut, StockMovementOut

router = APIRouter(tags=["inventory"])


@router.get("/inventory", response_model=list[ProductOut])
def list_inventory(
    q: Optional[str] = None,
    low_stock_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _user=Depends(require_permission("warehouse", "read")),
):
    """List products with stock tracking and reorder information."""
    with DBManager():
        query = Product.select()
        if q and q.strip():
            query = query.where(Product.name.contains(q.strip()))
        if low_stock_only:
            query = query.where(
                (Product.track_stock == True)
                & (Product.stock_quantity <= Product.reorder_level)
            )
        return [
            {
                "id": item.id,
                "name": item.name,
                "buy_price": item.buy_price,
                "sell_price": item.sell_price,
                "image_path": item.image_path,
                "custom_product": item.custom_product,
                "category_id": item.category_id,
                "track_stock": item.track_stock,
                "stock_quantity": item.stock_quantity,
                "reorder_level": item.reorder_level,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in query.order_by(Product.name).paginate(page, page_size)
        ]


@router.get("/inventory/movements", response_model=list[StockMovementOut])
def list_stock_movements(
    product_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _user=Depends(require_permission("warehouse", "read")),
):
    with DBManager():
        query = StockMovement.select().join(Product).switch(StockMovement).join(User)
        if product_id is not None:
            query = query.where(StockMovement.product == product_id)
        query = query.order_by(StockMovement.created_at.desc()).paginate(page, page_size)
        result = []
        for movement in query:
            result.append({
                "id": movement.id,
                "product_id": movement.product_id,
                "product_name": movement.product.name,
                "user_id": movement.user_id,
                "username": movement.user.username,
                "quantity_change": movement.quantity_change,
                "stock_before": movement.stock_before,
                "stock_after": movement.stock_after,
                "reason": movement.reason,
                "reference_id": movement.reference_id,
                "notes": movement.notes,
                "created_at": movement.created_at,
            })
        return result


@router.post(
    "/inventory/adjustments",
    response_model=StockMovementOut,
    status_code=status.HTTP_201_CREATED,
)
def adjust_inventory(
    payload: InventoryAdjustmentInput,
    user=Depends(require_permission("warehouse", "create")),
):
    delta = float(payload.quantity_change)
    with DBManager():
        product = Product.get_or_none(Product.id == payload.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
        if not product.track_stock:
            raise HTTPException(
                status_code=409,
                detail="رهگیری موجودی برای این کالا فعال نیست؛ ابتدا آن را در مشخصات کالا فعال کنید.",
            )
        updated = Product.update(
            stock_quantity=Product.stock_quantity + delta
        ).where(
            (Product.id == product.id)
            & (Product.track_stock == True)
            & (Product.stock_quantity + delta >= 0)
        ).execute()
        if not updated:
            current = Product.get_by_id(product.id).stock_quantity
            raise HTTPException(
                status_code=409,
                detail="موجودی نمی‌تواند منفی شود؛ مقدار فعلی {} و تغییر درخواستی {} است.".format(current, delta),
            )
        updated_product = Product.get_by_id(product.id)
        after = float(updated_product.stock_quantity)
        before = after - delta
        movement = StockMovement.create(
            product=product.id,
            user=user.id,
            quantity_change=delta,
            stock_before=before,
            stock_after=after,
            reason=payload.reason,
            notes=payload.notes,
        )
        return {
            "id": movement.id,
            "product_id": product.id,
            "product_name": product.name,
            "user_id": user.id,
            "username": user.username,
            "quantity_change": movement.quantity_change,
            "stock_before": movement.stock_before,
            "stock_after": movement.stock_after,
            "reason": movement.reason,
            "reference_id": movement.reference_id,
            "notes": movement.notes,
            "created_at": movement.created_at,
        }
