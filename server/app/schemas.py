"""Explicit request/response contracts exposed by the public API."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=4, max_length=256)
    password: str = Field(min_length=4, max_length=1024)
    client_name: str = Field(default="Desktop client", min_length=1, max_length=256)


class SessionStatusRequest(StrictModel):
    ticket: str = Field(min_length=16, max_length=4096)


class SessionRevokeRequest(StrictModel):
    reason: str = Field(default="revoked_by_admin", max_length=256)


class LoginResponse(BaseModel):
    status: str
    access_token: Optional[str] = None
    session_ticket: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    message: Optional[str] = None
    user: Optional[dict] = None


class TokenResponse(BaseModel):
    status: str = "active"
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Optional[dict] = None


class SetupRequest(StrictModel):
    username: str = Field(min_length=4, max_length=256)
    password: str = Field(min_length=4, max_length=1024)
    password_confirmation: str = Field(min_length=4, max_length=1024)
    schema_rows: List[dict] = Field(default_factory=list, max_length=300)
    company_name: str = Field(default="کسب‌وکار من", min_length=1, max_length=256)
    business_profile: str = Field(default="general", pattern=r"^(general|supermarket|cafe|service|real_estate)$")
    setup_token: Optional[str] = Field(default=None, max_length=256)


class UserOut(BaseModel):
    id: UUID
    username: str
    is_admin: bool
    buttons: str
    is_active: bool = True
    requires_session_activation: bool = False
    created_at: datetime
    updated_at: datetime


class UserCreate(StrictModel):
    username: str = Field(min_length=4, max_length=256)
    password: str = Field(min_length=4, max_length=1024)
    is_admin: bool = False
    buttons: str = Field(default="", max_length=256)
    is_active: bool = True
    requires_session_activation: bool = True


class UserUpdate(StrictModel):
    username: Optional[str] = Field(default=None, min_length=4, max_length=256)
    password: Optional[str] = Field(default=None, min_length=4, max_length=1024)
    is_admin: Optional[bool] = None
    buttons: Optional[str] = Field(default=None, max_length=256)
    is_active: Optional[bool] = None
    requires_session_activation: Optional[bool] = None


class CategoryCreate(StrictModel):
    name: str = Field(min_length=1, max_length=256)


class CategoryUpdate(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)


class CategoryOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ProductCreate(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    buy_price: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    sell_price: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    image_path: Optional[str] = Field(default=None, max_length=256)
    custom_product: bool = False
    category_id: Optional[UUID] = None
    track_stock: bool = False
    reorder_level: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=4)


class ProductUpdate(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    buy_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    sell_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    image_path: Optional[str] = Field(default=None, max_length=256)
    custom_product: Optional[bool] = None
    category_id: Optional[UUID] = None
    track_stock: Optional[bool] = None
    reorder_level: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)


class ProductOut(BaseModel):
    id: UUID
    name: str
    buy_price: float
    sell_price: float
    image_path: Optional[str] = None
    custom_product: bool
    category_id: Optional[UUID] = None
    track_stock: bool = False
    stock_quantity: float = 0
    reorder_level: float = 0
    created_at: datetime
    updated_at: datetime


class ProductPageOut(BaseModel):
    items: List[ProductOut]
    page: int
    page_size: int
    total: int


class InventoryAdjustmentInput(StrictModel):
    product_id: UUID
    quantity_change: Decimal = Field(max_digits=16, decimal_places=4)
    reason: str = Field(default="correction", pattern=r"^(opening|purchase|correction|return|damage)$")
    notes: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_non_zero_adjustment(self):
        if self.quantity_change == 0:
            raise ValueError("مقدار اصلاح موجودی نباید صفر باشد.")
        return self


class StockMovementOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    user_id: Optional[UUID] = None
    username: str
    quantity_change: float
    stock_before: float
    stock_after: float
    reason: str
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class StockMovementPageOut(BaseModel):
    items: List[StockMovementOut]
    page: int
    page_size: int
    total: int


class WarehouseCreate(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    price: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    unit: str = Field(min_length=1, max_length=10)


class WarehouseUpdate(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    price: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    amount: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=10)


class WarehouseOut(BaseModel):
    id: UUID
    name: str
    price: float
    amount: float
    unit: str
    created_at: datetime
    updated_at: datetime


class CheckCreate(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    check_id: str = Field(min_length=1, max_length=256)
    price: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    date: str = Field(min_length=1, max_length=256)
    payed: bool = False


class CheckUpdate(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    check_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    price: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    date: Optional[str] = Field(default=None, min_length=1, max_length=256)
    payed: Optional[bool] = None


class CheckOut(BaseModel):
    id: UUID
    name: str
    check_id: str
    price: float
    date: str
    payed: bool
    created_at: datetime
    updated_at: datetime


class SaleItemCreate(StrictModel):
    product_id: UUID
    quantity: int = Field(gt=0, le=100000)


class SaleCreate(StrictModel):
    items: List[SaleItemCreate] = Field(min_length=1, max_length=500)
    paid: bool = False

    @model_validator(mode="after")
    def validate_unique_products(self):
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("هر محصول باید فقط یک بار در اقلام فروش ارسال شود.")
        return self


class ReceiptProductOut(BaseModel):
    id: UUID
    receipt_id: UUID
    product_id: Optional[UUID] = None
    buy_price: float
    sell_price: float
    quantity: int
    product_name: str = "محصول حذف‌شده"
    returned_quantity: int = 0
    returnable_quantity: int = 0
    created_at: datetime
    updated_at: datetime


class ReceiptOut(BaseModel):
    id: UUID
    payed: bool
    total_price: float
    user_id: UUID
    day_receipt_id: int
    created_at: datetime
    updated_at: datetime


class ReceiptDetailOut(ReceiptOut):
    items: List[ReceiptProductOut]


class SaleReturnItemCreate(StrictModel):
    original_line_id: UUID
    quantity: int = Field(gt=0, le=100000)


class SaleReturnCreate(StrictModel):
    receipt_id: UUID
    items: List[SaleReturnItemCreate] = Field(min_length=1, max_length=200)
    refund_method: Literal["cash", "card", "bank_transfer", "store_credit"] = "cash"
    reason: str = Field(default="customer_return", min_length=1, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def unique_original_lines(self):
        ids = [item.original_line_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("هر ردیف فاکتور فقط یک بار در سند مرجوعی وارد شود.")
        return self


class FiscalYearCreate(StrictModel):
    name: str = Field(min_length=2, max_length=256)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_period(self):
        if self.start_date > self.end_date:
            raise ValueError("تاریخ شروع سال مالی باید قبل از پایان آن باشد.")
        return self


class FiscalYearReopen(StrictModel):
    reason: str = Field(min_length=10, max_length=1000)


class LedgerAccountCreate(StrictModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=2, max_length=256)
    account_type: Literal["asset", "liability", "equity", "income", "expense"]
    description: Optional[str] = Field(default=None, max_length=1000)


class JournalLineCreate(StrictModel):
    account_id: UUID
    description: str = Field(default="", max_length=256)
    debit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    credit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)

    @model_validator(mode="after")
    def one_side_only(self):
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("هر ردیف باید دقیقاً یک مبلغ بدهکار یا بستانکار مثبت داشته باشد.")
        return self


class JournalEntryCreate(StrictModel):
    entry_date: date
    description: str = Field(min_length=3, max_length=2000)
    reference: Optional[str] = Field(default=None, max_length=256)
    lines: List[JournalLineCreate] = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def balanced_totals(self):
        debit = sum((line.debit for line in self.lines), Decimal("0"))
        credit = sum((line.credit for line in self.lines), Decimal("0"))
        if debit <= 0 or debit != credit:
            raise ValueError("سند حسابداری باید دارای جمع بدهکار و بستانکار برابر و مثبت باشد.")
        return self


class ReportSummary(BaseModel):
    receipt_count: int
    sales_total: float
    paid_count: int
    unpaid_count: int
    item_count: int
