"""Authenticated CRUD endpoints for the primary accounting records."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from peewee import ForeignKeyField, IntegrityError

from accounting_app.database.connection import DBManager
from accounting_app.database.models import (
    Category as CategoryModel,
    CheckIn as CheckInModel,
    CheckOut as CheckOutModel,
    Product as ProductModel,
    User as UserModel,
    Warehouse as WarehouseModel,
)
from accounting_app.services.schema_registry import cleanup_builtin_extension_values_many
from server.app.dependencies import get_current_user, require_admin
from server.app.schemas import (
    CategoryCreate, CategoryOut, CategoryUpdate,
    CheckCreate, CheckOut, CheckUpdate,
    ProductCreate, ProductOut, ProductUpdate,
    UserCreate, UserOut, UserUpdate,
    WarehouseCreate, WarehouseOut, WarehouseUpdate,
)

router = APIRouter(tags=["resources"])


def _serialize(record, *, exclude=()):
    result = {}
    excluded = set(exclude)
    for name, field in record._meta.fields.items():
        if name in excluded:
            continue
        if isinstance(field, ForeignKeyField):
            key = name + "_id"
            value = getattr(record, key)
        else:
            key = name
            value = getattr(record, name)
        result[key] = str(value) if isinstance(value, UUID) else value
    return result


def _not_found(label):
    raise HTTPException(status_code=404, detail="{} پیدا نشد.".format(label))


def _clean_name(value):
    value = value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="نام نمی‌تواند خالی باشد.")
    return value


def _check_category(category_id):
    if category_id is not None and CategoryModel.get_or_none(CategoryModel.id == category_id) is None:
        raise HTTPException(status_code=422, detail="دسته‌بندی انتخاب‌شده وجود ندارد.")


def _save_patch(record, values):
    for key, value in values.items():
        if key in ("buy_price", "sell_price", "price", "amount") and value is not None:
            value = float(value)
        if key == "name" and value is not None:
            value = _clean_name(value)
        if key == "category_id":
            record.category = value
        else:
            setattr(record, key, value)
    record.save()
    return record


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _user=Depends(get_current_user),
):
    with DBManager():
        query = CategoryModel.select()
        if q and q.strip():
            query = query.where(CategoryModel.name.contains(q.strip()))
        return [_serialize(item) for item in query.order_by(CategoryModel.name).paginate(page, page_size)]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, _admin=Depends(require_admin)):
    with DBManager():
        record = CategoryModel.create(name=_clean_name(payload.name))
        return _serialize(record)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: UUID, payload: CategoryUpdate, _admin=Depends(require_admin)):
    with DBManager():
        record = CategoryModel.get_or_none(CategoryModel.id == category_id)
        if record is None:
            _not_found("دسته‌بندی")
        values = payload.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = _clean_name(values["name"])
        return _serialize(_save_patch(record, values))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: UUID, _admin=Depends(require_admin)):
    with DBManager():
        record = CategoryModel.get_or_none(CategoryModel.id == category_id)
        if record is None:
            _not_found("دسته‌بندی")
        cleanup_builtin_extension_values_many("categories", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/products", response_model=List[ProductOut])
def list_products(
    q: Optional[str] = None,
    category_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _user=Depends(get_current_user),
):
    with DBManager():
        query = ProductModel.select()
        if q and q.strip():
            query = query.where(ProductModel.name.contains(q.strip()))
        if category_id is not None:
            query = query.where(ProductModel.category == category_id)
        return [_serialize(item) for item in query.order_by(ProductModel.name).paginate(page, page_size)]


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, _admin=Depends(require_admin)):
    with DBManager():
        _check_category(payload.category_id)
        record = ProductModel.create(
            name=_clean_name(payload.name),
            buy_price=float(payload.buy_price),
            sell_price=float(payload.sell_price),
            image_path=payload.image_path,
            custom_product=payload.custom_product,
            category=payload.category_id,
        )
        return _serialize(record)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: UUID, payload: ProductUpdate, _admin=Depends(require_admin)):
    with DBManager():
        record = ProductModel.get_or_none(ProductModel.id == product_id)
        if record is None:
            _not_found("محصول")
        values = payload.model_dump(exclude_unset=True)
        if "category_id" in values:
            _check_category(values["category_id"])
        return _serialize(_save_patch(record, values))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: UUID, _admin=Depends(require_admin)):
    with DBManager():
        record = ProductModel.get_or_none(ProductModel.id == product_id)
        if record is None:
            _not_found("محصول")
        cleanup_builtin_extension_values_many("products", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/warehouses", response_model=List[WarehouseOut])
def list_warehouses(_user=Depends(get_current_user)):
    with DBManager():
        return [_serialize(item) for item in WarehouseModel.select().order_by(WarehouseModel.name)]


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(payload: WarehouseCreate, _admin=Depends(require_admin)):
    if payload.unit not in ("kg", "m", "l", "pcs"):
        raise HTTPException(status_code=422, detail="واحد انبار معتبر نیست.")
    with DBManager():
        record = WarehouseModel.create(
            name=_clean_name(payload.name), price=float(payload.price),
            amount=float(payload.amount), unit=payload.unit,
        )
        return _serialize(record)


@router.patch("/warehouses/{record_id}", response_model=WarehouseOut)
def update_warehouse(record_id: UUID, payload: WarehouseUpdate, _admin=Depends(require_admin)):
    with DBManager():
        record = WarehouseModel.get_or_none(WarehouseModel.id == record_id)
        if record is None:
            _not_found("رکورد انبار")
        values = payload.model_dump(exclude_unset=True)
        if "unit" in values and values["unit"] not in ("kg", "m", "l", "pcs"):
            raise HTTPException(status_code=422, detail="واحد انبار معتبر نیست.")
        return _serialize(_save_patch(record, values))


@router.delete("/warehouses/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(record_id: UUID, _admin=Depends(require_admin)):
    with DBManager():
        record = WarehouseModel.get_or_none(WarehouseModel.id == record_id)
        if record is None:
            _not_found("رکورد انبار")
        cleanup_builtin_extension_values_many("warehouses", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _list_checks(model, entity, q, page, page_size):
    with DBManager():
        query = model.select()
        if q and q.strip():
            text = q.strip()
            query = query.where((model.name.contains(text)) | (model.check_id.contains(text)))
        return [_serialize(item) for item in query.order_by(model.created_at.desc()).paginate(page, page_size)]


def _create_check(model, payload, entity):
    if not payload.check_id.strip():
        raise HTTPException(status_code=422, detail="شناسه چک نمی‌تواند خالی باشد.")
    with DBManager():
        return _serialize(model.create(
            name=_clean_name(payload.name), check_id=payload.check_id.strip(),
            price=float(payload.price), date=payload.date.strip(), payed=payload.payed,
        ))


def _update_check(model, record_id, payload):
    with DBManager():
        record = model.get_or_none(model.id == record_id)
        if record is None:
            _not_found("چک")
        values = payload.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = _clean_name(values["name"])
        if "check_id" in values and values["check_id"] is not None:
            values["check_id"] = values["check_id"].strip()
            if not values["check_id"]:
                raise HTTPException(status_code=422, detail="شناسه چک نمی‌تواند خالی باشد.")
        if "date" in values and values["date"] is not None:
            values["date"] = values["date"].strip()
        return _serialize(_save_patch(record, values))


def _delete_check(model, entity, record_id):
    with DBManager():
        record = model.get_or_none(model.id == record_id)
        if record is None:
            _not_found("چک")
        cleanup_builtin_extension_values_many(entity, [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/checks/in", response_model=List[CheckOut])
def list_check_ins(
    q: Optional[str] = None, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), _user=Depends(get_current_user),
):
    return _list_checks(CheckInModel, "check_ins", q, page, page_size)


@router.post("/checks/in", response_model=CheckOut, status_code=status.HTTP_201_CREATED)
def create_check_in(payload: CheckCreate, _admin=Depends(require_admin)):
    return _create_check(CheckInModel, payload, "check_ins")


@router.patch("/checks/in/{record_id}", response_model=CheckOut)
def update_check_in(record_id: UUID, payload: CheckUpdate, _admin=Depends(require_admin)):
    return _update_check(CheckInModel, record_id, payload)


@router.delete("/checks/in/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check_in(record_id: UUID, _admin=Depends(require_admin)):
    return _delete_check(CheckInModel, "check_ins", record_id)


@router.get("/checks/out", response_model=List[CheckOut])
def list_check_outs(
    q: Optional[str] = None, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), _user=Depends(get_current_user),
):
    return _list_checks(CheckOutModel, "check_outs", q, page, page_size)


@router.post("/checks/out", response_model=CheckOut, status_code=status.HTTP_201_CREATED)
def create_check_out(payload: CheckCreate, _admin=Depends(require_admin)):
    return _create_check(CheckOutModel, payload, "check_outs")


@router.patch("/checks/out/{record_id}", response_model=CheckOut)
def update_check_out(record_id: UUID, payload: CheckUpdate, _admin=Depends(require_admin)):
    return _update_check(CheckOutModel, record_id, payload)


@router.delete("/checks/out/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check_out(record_id: UUID, _admin=Depends(require_admin)):
    return _delete_check(CheckOutModel, "check_outs", record_id)


@router.get("/users", response_model=List[UserOut])
def list_users(_admin=Depends(require_admin)):
    with DBManager():
        return [_serialize(item, exclude=("password",)) for item in UserModel.select().order_by(UserModel.username)]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, _admin=Depends(require_admin)):
    username = _clean_name(payload.username)
    with DBManager():
        if UserModel.get_or_none(UserModel.username == username):
            raise HTTPException(status_code=409, detail="این نام کاربری قبلاً ثبت شده است.")
        record = UserModel(
            username=username,
            password="",
            is_admin=payload.is_admin,
            buttons=payload.buttons,
            is_active=payload.is_active,
            requires_session_activation=payload.requires_session_activation,
        )
        record.set_password(payload.password)
        record.save(force_insert=True)
        return _serialize(record, exclude=("password",))


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate, current_admin=Depends(require_admin)):
    with DBManager():
        record = UserModel.get_or_none(UserModel.id == user_id)
        if record is None:
            _not_found("کاربر")
        values = payload.model_dump(exclude_unset=True)
        if "username" in values and values["username"] is not None:
            values["username"] = _clean_name(values["username"])
            other = UserModel.get_or_none(
                (UserModel.username == values["username"]) & (UserModel.id != user_id)
            )
            if other is not None:
                raise HTTPException(status_code=409, detail="این نام کاربری قبلاً ثبت شده است.")
        password_changed = bool(values.get("password"))
        if password_changed:
            record.set_password(values.pop("password"))
        elif "password" in values:
            values.pop("password")
        if values.get("is_admin") is False and record.is_admin:
            active_admin_count = UserModel.select().where(
                (UserModel.is_admin == True) & (UserModel.is_active == True)
            ).count()
            if record.is_active and active_admin_count <= 1:
                raise HTTPException(status_code=409, detail="آخرین مدیر فعال را نمی‌توان از مدیریت خارج کرد.")
        if values.get("is_active") is False and record.is_active:
            if record.id == current_admin.id:
                raise HTTPException(status_code=409, detail="نمی‌توانید حساب فعلی خود را غیرفعال کنید.")
            if record.is_admin:
                active_admin_count = UserModel.select().where(
                    (UserModel.is_admin == True) & (UserModel.is_active == True)
                ).count()
                if active_admin_count <= 1:
                    raise HTTPException(status_code=409, detail="آخرین مدیر فعال را نمی‌توان غیرفعال کرد.")
        updated = _save_patch(record, values)
        from datetime import datetime
        from accounting_app.database.models import ApiSession
        if values.get("is_active") is False or password_changed:
            now = datetime.now()
            ApiSession.update(
                status="revoked", revoked_at=now,
                revocation_reason="account_disabled" if values.get("is_active") is False else "password_changed",
            ).where(
                (ApiSession.user == updated.id) & ApiSession.status.in_(("active", "pending"))
            ).execute()
        elif values.get("requires_session_activation") is False:
            ApiSession.update(
                status="active", activated_at=datetime.now(), last_seen_at=datetime.now()
            ).where(
                (ApiSession.user == updated.id) & (ApiSession.status == "pending")
            ).execute()
        elif values.get("requires_session_activation") is True:
            ApiSession.update(
                status="revoked", revoked_at=datetime.now(),
                revocation_reason="activation_policy_enabled"
            ).where(
                (ApiSession.user == updated.id) & (ApiSession.status == "active")
            ).execute()
        return _serialize(updated, exclude=("password",))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, current_admin=Depends(require_admin)):
    with DBManager():
        record = UserModel.get_or_none(UserModel.id == user_id)
        if record is None:
            _not_found("کاربر")
        if record.id == current_admin.id:
            raise HTTPException(status_code=409, detail="نمی‌توانید حساب فعلی خود را حذف کنید.")
        if record.is_admin and record.is_active and UserModel.select().where(
            (UserModel.is_admin == True) & (UserModel.is_active == True)
        ).count() <= 1:
            raise HTTPException(status_code=409, detail="آخرین مدیر فعال را نمی‌توان حذف کرد.")
        cleanup_builtin_extension_values_many("users", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
