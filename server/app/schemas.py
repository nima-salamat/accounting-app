"""Explicit request/response contracts exposed by the public API."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=4, max_length=256)
    password: str = Field(min_length=4, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SetupRequest(StrictModel):
    username: str = Field(min_length=4, max_length=256)
    password: str = Field(min_length=4, max_length=1024)
    password_confirmation: str = Field(min_length=4, max_length=1024)
    schema_rows: List[dict] = Field(default_factory=list, max_length=300)


class UserOut(BaseModel):
    id: UUID
    username: str
    is_admin: bool
    buttons: str
    created_at: datetime
    updated_at: datetime


class UserCreate(StrictModel):
    username: str = Field(min_length=4, max_length=256)
    password: str = Field(min_length=4, max_length=1024)
    is_admin: bool = False
    buttons: str = Field(default="", max_length=256)


class UserUpdate(StrictModel):
    username: Optional[str] = Field(default=None, min_length=4, max_length=256)
    password: Optional[str] = Field(default=None, min_length=4, max_length=1024)
    is_admin: Optional[bool] = None
    buttons: Optional[str] = Field(default=None, max_length=256)


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


class ProductUpdate(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    buy_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    sell_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    image_path: Optional[str] = Field(default=None, max_length=256)
    custom_product: Optional[bool] = None
    category_id: Optional[UUID] = None


class ProductOut(BaseModel):
    id: UUID
    name: str
    buy_price: float
    sell_price: float
    image_path: Optional[str] = None
    custom_product: bool
    category_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


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


class ReportSummary(BaseModel):
    receipt_count: int
    sales_total: float
    paid_count: int
    unpaid_count: int
    item_count: int
