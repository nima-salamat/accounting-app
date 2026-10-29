"""Authenticated CRUD endpoints for the primary accounting records."""
from typing import List, Optional
import json
from uuid import UUID, uuid4
from pathlib import Path
import mimetypes

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from peewee import ForeignKeyField, IntegrityError

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import AppSetting
from accounting_app.database.models import (
    Category as CategoryModel,
    CheckIn as CheckInModel,
    CheckOut as CheckOutModel,
    Product as ProductModel,
    StockMovement,
    User as UserModel,
    Warehouse as WarehouseModel,
)
from accounting_app.services.schema_registry import cleanup_builtin_extension_values_many
from accounting_app.services.audit import record_audit
from accounting_app.config import get_data_dir
from accounting_app.services.kiosk_config import load_kiosk_settings, kiosk_product_ids_for_user
from server.app.dependencies import get_current_user, require_admin
from server.app.permissions import has_permission, require_permission
from server.app.schemas import (
    CategoryCreate, CategoryOut, CategoryUpdate,
    CheckCreate, CheckOut, CheckUpdate,
    ProductCreate, ProductOut, ProductUpdate,
    UserCreate, UserOut, UserUpdate,
    WarehouseCreate, WarehouseOut, WarehouseUpdate, AppearanceSettingsUpdate,
)

router = APIRouter(tags=["resources"])

DEFAULT_APPEARANCE_SETTINGS = {
    "currency_unit": "toman",
    "font_family": "Vazirmatn", "font_size": 13, "heading_scale": 1.0,
    "density": "comfortable", "corner_radius": 10, "control_height": 36,
    "control_padding": 8, "horizontal_padding": 12, "section_spacing": 12,
}


def _load_appearance_settings():
    setting = AppSetting.get_or_none(AppSetting.key == "appearance_preferences")
    try:
        stored = json.loads(setting.value or "{}") if setting else {}
    except (TypeError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    try:
        return AppearanceSettingsUpdate.model_validate(
            {**DEFAULT_APPEARANCE_SETTINGS, **stored}
        ).model_dump()
    except Exception:
        return dict(DEFAULT_APPEARANCE_SETTINGS)


@router.get("/appearance-settings")
def get_appearance_settings():
    """Return non-sensitive shared UI preferences before authentication as well as after it."""
    with DBManager():
        return _load_appearance_settings()


@router.put("/appearance-settings")
def save_appearance_settings(
    payload: AppearanceSettingsUpdate,
    _user=Depends(require_admin),
):
    value = json.dumps(payload.model_dump(), ensure_ascii=False, separators=(",", ":"))
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == "appearance_preferences")
        if setting is None:
            AppSetting.create(key="appearance_preferences", value=value)
        else:
            setting.value = value
            setting.save(only=[AppSetting.value, AppSetting.updated_at])
    return payload.model_dump()


@router.get("/company-profile")
def get_company_profile(_user=Depends(require_permission("products", "read"))):
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == "company_profile")
        try:
            profile = json.loads(setting.value) if setting and setting.value else {}
        except (TypeError, ValueError):
            profile = {}
        if not isinstance(profile, dict):
            profile = {}
        return {
            "company_name": str(profile.get("company_name") or "کسب‌وکار من")[:256],
            "business_profile": str(profile.get("business_profile") or "general")[:32],
            "business_profile_label": str(profile.get("business_profile_label") or "کسب‌وکار عمومی")[:128],
            "product_buy_price_required": bool(profile.get("product_buy_price_required", True)),
            "receipt_history_hours": load_kiosk_settings()["receipt_history_hours"],
            "cafe_seat_selection": load_kiosk_settings()["cafe_seat_selection"],
            "kiosk_active": load_kiosk_settings()["active"],
        }



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


def _product_buy_price_required():
    setting = AppSetting.get_or_none(AppSetting.key == "company_profile")
    try:
        profile = json.loads(setting.value) if setting and setting.value else {}
    except (TypeError, ValueError):
        profile = {}
    return bool(profile.get("product_buy_price_required", True)) if isinstance(profile, dict) else True


def _check_category(category_id):
    if category_id is not None and CategoryModel.get_or_none(CategoryModel.id == category_id) is None:
        raise HTTPException(status_code=422, detail="دسته‌بندی انتخاب‌شده وجود ندارد.")


def _save_patch(record, values):
    for key, value in values.items():
        if key in ("buy_price", "sell_price", "price", "amount", "reorder_level") and value is not None:
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
    response: Response,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    user=Depends(require_permission("categories", "read")),
):
    with DBManager():
        query = CategoryModel.select()
        if q and q.strip():
            query = query.where(CategoryModel.name.contains(q.strip()))
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_serialize(item) for item in query.order_by(CategoryModel.name).paginate(page, page_size)]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, user=Depends(require_permission("categories", "create"))):
    with DBManager():
        record = CategoryModel.create(name=_clean_name(payload.name))
        record_audit(user, "category.created", "categories", record.id, {"name": record.name})
        return _serialize(record)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: UUID, payload: CategoryUpdate, user=Depends(require_permission("categories", "update"))):
    with DBManager():
        record = CategoryModel.get_or_none(CategoryModel.id == category_id)
        if record is None:
            _not_found("دسته‌بندی")
        values = payload.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = _clean_name(values["name"])
        updated = _save_patch(record, values)
        record_audit(user, "category.updated", "categories", updated.id, {"fields": sorted(values)})
        return _serialize(updated)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: UUID, user=Depends(require_permission("categories", "delete"))):
    with DBManager():
        record = CategoryModel.get_or_none(CategoryModel.id == category_id)
        if record is None:
            _not_found("دسته‌بندی")
        record_audit(user, "category.deleted", "categories", record.id, {"name": record.name})
        cleanup_builtin_extension_values_many("categories", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/products", response_model=List[ProductOut])
def list_products(
    response: Response,
    q: Optional[str] = None,
    category_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    user=Depends(require_permission("products", "read")),
):
    with DBManager():
        query = ProductModel.select()
        if q and q.strip():
            query = query.where(ProductModel.name.contains(q.strip()))
        if category_id is not None:
            query = query.where(ProductModel.category == category_id)
        allowed_product_ids = kiosk_product_ids_for_user(user)
        if allowed_product_ids is not None:
            query = query.where(ProductModel.id.in_(list(allowed_product_ids)))
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_serialize(item) for item in query.order_by(ProductModel.name).paginate(page, page_size)]


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, user=Depends(require_permission("products", "read"))):
    with DBManager():
        product = ProductModel.get_or_none(ProductModel.id == product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
        allowed_product_ids = kiosk_product_ids_for_user(user)
        if allowed_product_ids is not None and product.id not in allowed_product_ids:
            raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
        return _serialize(product)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, user=Depends(require_permission("products", "create"))):
    with DBManager():
        if payload.buy_price is None and _product_buy_price_required():
            raise HTTPException(status_code=422, detail="قیمت خرید طبق تنظیمات کسب‌وکار الزامی است.")
        _check_category(payload.category_id)
        record = ProductModel.create(
            name=_clean_name(payload.name),
            buy_price=float(payload.buy_price or 0),
            sell_price=float(payload.sell_price),
            image_path=payload.image_path,
            custom_product=payload.custom_product,
            category=payload.category_id,
            track_stock=payload.track_stock,
            reorder_level=float(payload.reorder_level),
        )
        record_audit(
            user, "product.created", "products", record.id,
            {"name": record.name, "sell_price": record.sell_price, "track_stock": record.track_stock},
        )
        return _serialize(record)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: UUID, payload: ProductUpdate, user=Depends(require_permission("products", "update"))):
    with DBManager():
        record = ProductModel.get_or_none(ProductModel.id == product_id)
        if record is None:
            _not_found("محصول")
        values = payload.model_dump(exclude_unset=True)
        if "buy_price" in values and values["buy_price"] is None:
            if _product_buy_price_required():
                raise HTTPException(status_code=422, detail="قیمت خرید طبق تنظیمات کسب‌وکار الزامی است.")
            values["buy_price"] = 0
        if "category_id" in values:
            _check_category(values["category_id"])
        updated = _save_patch(record, values)
        record_audit(user, "product.updated", "products", updated.id, {"name": updated.name, "fields": sorted(values)})
        return _serialize(updated)


def _product_image_directory():
    directory = (get_data_dir() / "product_images").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _identify_image(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None, None


@router.post("/products/{product_id}/image")
async def upload_product_image(
    product_id: UUID,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Store a bounded raster product photo under a generated server-side name."""
    if not (has_permission(user, "products", "create") or has_permission(user, "products", "update")):
        raise HTTPException(status_code=403, detail="برای افزودن یا ویرایش تصویر محصول مجوز ندارید.")
    with DBManager():
        product = ProductModel.get_or_none(ProductModel.id == product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
        if file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise HTTPException(status_code=415, detail="فقط تصویر JPEG، PNG، WebP یا GIF مجاز است.")
        data = await file.read(8 * 1024 * 1024 + 1)
        if not data or len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم عکس باید حداکثر ۸ مگابایت باشد.")
        extension, media_type = _identify_image(data)
        if not extension or media_type != file.content_type:
            raise HTTPException(status_code=415, detail="محتوای فایل با نوع تصویر معتبر مطابقت ندارد.")
        directory = _product_image_directory()
        generated_name = "{}{}".format(uuid4().hex, extension)
        destination = (directory / generated_name).resolve()
        if destination.parent != directory:
            raise HTTPException(status_code=400, detail="نام فایل نامعتبر است.")
        destination.write_bytes(data)
        old_name = product.image_path
        product.image_path = generated_name
        product.save(only=[ProductModel.image_path, ProductModel.updated_at])
        if old_name and old_name != generated_name:
            old_path = (directory / Path(old_name).name).resolve()
            if old_path.parent == directory and old_path.is_file():
                try:
                    old_path.unlink()
                except OSError:
                    pass
        record_audit(
            user, "product.image_updated", "products", product.id,
            {"image": generated_name, "content_type": media_type, "bytes": len(data)},
        )
        return _serialize(product)


@router.get("/products/{product_id}/image")
def get_product_image(
    product_id: UUID,
    user=Depends(require_permission("products", "read")),
):
    with DBManager():
        product = ProductModel.get_or_none(ProductModel.id == product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
        if not product.image_path:
            raise HTTPException(status_code=404, detail="برای این محصول عکسی ثبت نشده است.")
        directory = _product_image_directory()
        path = (directory / Path(product.image_path).name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(status_code=404, detail="فایل تصویر پیدا نشد.")
        _extension, media_type = _identify_image(path.read_bytes()[:16])
        if not media_type:
            raise HTTPException(status_code=415, detail="فایل تصویر ذخیره‌شده معتبر نیست.")
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
        )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: UUID, user=Depends(require_permission("products", "delete"))):
    with DBManager():
        record = ProductModel.get_or_none(ProductModel.id == product_id)
        if record is None:
            _not_found("محصول")
        if StockMovement.select().where(StockMovement.product == record.id).exists():
            raise HTTPException(
                status_code=409,
                detail="این کالا سابقهٔ گردش موجودی دارد؛ برای حفظ سابقهٔ حسابرسی نمی‌توان آن را حذف کرد.",
            )
        record_audit(user, "product.deleted", "products", record.id, {"name": record.name})
        cleanup_builtin_extension_values_many("products", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/warehouses", response_model=List[WarehouseOut])
def list_warehouses(
    response: Response,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    user=Depends(require_permission("warehouse", "read")),
):
    with DBManager():
        query = WarehouseModel.select()
        if q and q.strip():
            query = query.where(WarehouseModel.name.contains(q.strip()))
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_serialize(item) for item in query.order_by(WarehouseModel.name).paginate(page, page_size)]


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(payload: WarehouseCreate, user=Depends(require_permission("warehouse", "create"))):
    if payload.unit not in ("kg", "m", "l", "pcs"):
        raise HTTPException(status_code=422, detail="واحد انبار معتبر نیست.")
    with DBManager():
        record = WarehouseModel.create(
            name=_clean_name(payload.name), price=float(payload.price),
            amount=float(payload.amount), unit=payload.unit,
        )
        record_audit(user, "warehouse.created", "warehouse", record.id, {"name": record.name, "amount": record.amount})
        return _serialize(record)


@router.patch("/warehouses/{record_id}", response_model=WarehouseOut)
def update_warehouse(record_id: UUID, payload: WarehouseUpdate, user=Depends(require_permission("warehouse", "update"))):
    with DBManager():
        record = WarehouseModel.get_or_none(WarehouseModel.id == record_id)
        if record is None:
            _not_found("رکورد انبار")
        values = payload.model_dump(exclude_unset=True)
        if "unit" in values and values["unit"] not in ("kg", "m", "l", "pcs"):
            raise HTTPException(status_code=422, detail="واحد انبار معتبر نیست.")
        updated = _save_patch(record, values)
        record_audit(user, "warehouse.updated", "warehouse", updated.id, {"name": updated.name, "fields": sorted(values)})
        return _serialize(updated)


@router.delete("/warehouses/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(record_id: UUID, user=Depends(require_permission("warehouse", "delete"))):
    with DBManager():
        record = WarehouseModel.get_or_none(WarehouseModel.id == record_id)
        if record is None:
            _not_found("رکورد انبار")
        record_audit(user, "warehouse.deleted", "warehouse", record.id, {"name": record.name})
        cleanup_builtin_extension_values_many("warehouses", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _list_checks(model, entity, q, page, page_size, response):
    with DBManager():
        query = model.select()
        if q and q.strip():
            text = q.strip()
            query = query.where((model.name.contains(text)) | (model.check_id.contains(text)))
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_serialize(item) for item in query.order_by(model.created_at.desc()).paginate(page, page_size)]


def _create_check(model, payload, entity, user):
    if not payload.check_id.strip():
        raise HTTPException(status_code=422, detail="شناسه چک نمی‌تواند خالی باشد.")
    with DBManager():
        record = model.create(
            name=_clean_name(payload.name), check_id=payload.check_id.strip(),
            price=float(payload.price), date=payload.date.strip(), payed=payload.payed,
        )
        record_audit(user, "check.created", entity, record.id, {"name": record.name, "check_id": record.check_id, "price": record.price})
        return _serialize(record)


def _update_check(model, record_id, payload, entity, user):
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
        updated = _save_patch(record, values)
        record_audit(user, "check.updated", entity, updated.id, {"check_id": updated.check_id, "fields": sorted(values)})
        return _serialize(updated)


def _delete_check(model, entity, record_id, user):
    with DBManager():
        record = model.get_or_none(model.id == record_id)
        if record is None:
            _not_found("چک")
        record_audit(user, "check.deleted", entity, record.id, {"name": record.name, "check_id": record.check_id})
        cleanup_builtin_extension_values_many(entity, [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/checks/in", response_model=List[CheckOut])
def list_check_ins(
    response: Response, q: Optional[str] = None, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), user=Depends(require_permission("checks_in", "read")),
):
    return _list_checks(CheckInModel, "check_ins", q, page, page_size, response)


@router.post("/checks/in", response_model=CheckOut, status_code=status.HTTP_201_CREATED)
def create_check_in(payload: CheckCreate, user=Depends(require_permission("checks_in", "create"))):
    return _create_check(CheckInModel, payload, "check_ins", user)


@router.patch("/checks/in/{record_id}", response_model=CheckOut)
def update_check_in(record_id: UUID, payload: CheckUpdate, user=Depends(require_permission("checks_in", "update"))):
    return _update_check(CheckInModel, record_id, payload, "check_ins", user)


@router.delete("/checks/in/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check_in(record_id: UUID, user=Depends(require_permission("checks_in", "delete"))):
    return _delete_check(CheckInModel, "check_ins", record_id, user)


@router.get("/checks/out", response_model=List[CheckOut])
def list_check_outs(
    response: Response, q: Optional[str] = None, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), user=Depends(require_permission("checks_out", "read")),
):
    return _list_checks(CheckOutModel, "check_outs", q, page, page_size, response)


@router.post("/checks/out", response_model=CheckOut, status_code=status.HTTP_201_CREATED)
def create_check_out(payload: CheckCreate, user=Depends(require_permission("checks_out", "create"))):
    return _create_check(CheckOutModel, payload, "check_outs", user)


@router.patch("/checks/out/{record_id}", response_model=CheckOut)
def update_check_out(record_id: UUID, payload: CheckUpdate, user=Depends(require_permission("checks_out", "update"))):
    return _update_check(CheckOutModel, record_id, payload, "check_outs", user)


@router.delete("/checks/out/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check_out(record_id: UUID, user=Depends(require_permission("checks_out", "delete"))):
    return _delete_check(CheckOutModel, "check_outs", record_id, user)


@router.get("/users", response_model=List[UserOut])
def list_users(
    response: Response,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _admin=Depends(require_admin),
):
    with DBManager():
        query = UserModel.select()
        if q and q.strip():
            query = query.where(UserModel.username.contains(q.strip()))
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_serialize(item, exclude=("password",)) for item in query.order_by(UserModel.username).paginate(page, page_size)]


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
            max_active_sessions=payload.max_active_sessions,
        )
        record.set_password(payload.password)
        record.save(force_insert=True)
        record_audit(
            _admin, "user.created", "users", record.id,
            {"username": record.username, "is_admin": record.is_admin, "is_active": record.is_active},
        )
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
        if "max_active_sessions" in values and values.get("is_active") is not False and not password_changed:
            from server.app.api.auth import enforce_user_session_limit
            enforce_user_session_limit(
                updated.id, updated.max_active_sessions, reason="session_limit_changed"
            )
        record_audit(
            current_admin, "user.updated", "users", updated.id,
            {
                "username": updated.username,
                "changed_fields": sorted(values.keys()) + (["password"] if password_changed else []),
                "is_admin": updated.is_admin,
                "is_active": updated.is_active,
                "max_active_sessions": updated.max_active_sessions,
            },
        )
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
        record_audit(current_admin, "user.deleted", "users", record.id, {"username": record.username})
        cleanup_builtin_extension_values_many("users", [record.id])
        record.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
