"""Server-side summary queries; clients receive aggregates, not full table dumps."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from peewee import fn

from accounting_app.database.connection import DBManager
from accounting_app.database.models import Receipt, ReceiptProduct
from server.app.dependencies import get_current_user
from server.app.schemas import ReportSummary

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummary)
def sales_summary(
    start_at: Optional[datetime] = Query(default=None),
    end_at: Optional[datetime] = Query(default=None),
    user=Depends(get_current_user),
):
    if start_at is not None and end_at is not None and start_at > end_at:
        raise HTTPException(status_code=422, detail="بازه تاریخ نامعتبر است.")

    filters = []
    if start_at is not None:
        filters.append(Receipt.created_at >= start_at)
    if end_at is not None:
        filters.append(Receipt.created_at <= end_at)
    if not user.is_admin:
        filters.append(Receipt.user == user.id)

    with DBManager():
        query = Receipt.select()
        if filters:
            query = query.where(*filters)
        receipt_count = query.count()
        sales_query = Receipt.select(fn.COALESCE(fn.SUM(Receipt.total_price), 0))
        if filters:
            sales_query = sales_query.where(*filters)
        sales_total = sales_query.scalar() or 0
        paid_count = Receipt.select().where(*(filters + [Receipt.payed == True])).count()
        unpaid_count = Receipt.select().where(*(filters + [Receipt.payed == False])).count()
        item_count = (
            ReceiptProduct.select(fn.COALESCE(fn.SUM(ReceiptProduct.quantity), 0))
            .where(ReceiptProduct.receipt.in_(query.select(Receipt.id))).scalar() or 0
        )
        return {
            "receipt_count": int(receipt_count),
            "sales_total": float(sales_total),
            "paid_count": int(paid_count),
            "unpaid_count": int(unpaid_count),
            "item_count": int(item_count),
        }


@router.get("/sales-trend")
def sales_trend(
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """Daily sales aggregates for trend charts without exposing raw receipt rows."""
    from datetime import timedelta

    start_at = datetime.now() - timedelta(days=days)
    filters = [Receipt.created_at >= start_at]
    if not user.is_admin:
        filters.append(Receipt.user == user.id)
    day_expr = fn.strftime("%Y-%m-%d", Receipt.created_at)
    with DBManager():
        rows = (
            Receipt.select(
                day_expr.alias("date"),
                fn.COALESCE(fn.SUM(Receipt.total_price), 0).alias("total"),
                fn.COUNT(Receipt.id).alias("receipt_count"),
            )
            .where(*filters)
            .group_by(day_expr)
            .order_by(day_expr)
            .dicts()
        )
        return [
            {
                "date": row["date"],
                "total": float(row["total"] or 0),
                "receipt_count": int(row["receipt_count"] or 0),
            }
            for row in rows
        ]


@router.get("/product-performance")
def product_performance(
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
):
    """Aggregate sold quantities and revenue for the top products."""
    from peewee import JOIN
    from accounting_app.database.models import Product

    filters = []
    if not user.is_admin:
        filters.append(Receipt.user == user.id)
    revenue = fn.SUM(ReceiptProduct.sell_price * ReceiptProduct.quantity)
    quantity = fn.SUM(ReceiptProduct.quantity)
    query = (
        ReceiptProduct.select(
            Product.id.alias("product_id"),
            Product.name.alias("name"),
            quantity.alias("quantity"),
            revenue.alias("revenue"),
        )
        .join(Receipt)
        .switch(ReceiptProduct)
        .join(Product, JOIN.LEFT_OUTER)
        .group_by(Product.id, Product.name)
        .order_by(revenue.desc())
        .limit(limit)
    )
    if filters:
        query = query.where(*filters)
    with DBManager():
        return [
            {
                "product_id": str(row["product_id"]) if row["product_id"] else None,
                "name": row["name"] or "محصول حذف‌شده",
                "quantity": int(row["quantity"] or 0),
                "revenue": float(row["revenue"] or 0),
            }
            for row in query.dicts()
        ]
