"""Persistent domain models; field names preserve the existing database schema."""
import binascii
import hashlib
import hmac
import secrets
from enum import Enum

from peewee import BooleanField, CharField, FloatField, ForeignKeyField, IntegerField

from accounting_app.config import FIELD_LENGTH
from accounting_app.database.connection import BaseModel

_HASH_NAME = "pbkdf2_sha256"
_HASH_ITERATIONS = 600_000
_LEGACY_ITERATIONS = 100_000
_SALT_BYTES = 16


class User(BaseModel):
    username = CharField(max_length=FIELD_LENGTH, unique=True)
    password = CharField(max_length=FIELD_LENGTH)
    is_admin = BooleanField(default=False)
    buttons = CharField(max_length=FIELD_LENGTH, default="")

    def set_password(self, password):
        """Store a versioned PBKDF2 hash instead of the raw password."""
        if not isinstance(password, str):
            raise TypeError("Password must be text.")
        salt = secrets.token_bytes(_SALT_BYTES)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
        self.password = "$".join((_HASH_NAME, str(_HASH_ITERATIONS), salt.hex(), digest.hex()))

    def check_password(self, password):
        """Verify current and historical credential formats."""
        if not isinstance(password, str) or not isinstance(self.password, str):
            return False
        stored = self.password
        try:
            if stored.startswith(_HASH_NAME + "$"):
                algorithm, rounds_text, salt_text, digest_text = stored.split("$", 3)
                if algorithm != _HASH_NAME:
                    return False
                rounds = int(rounds_text)
                if rounds < 1 or rounds > 2_000_000:
                    return False
                salt = bytes.fromhex(salt_text)
                expected = bytes.fromhex(digest_text)
                if len(salt) < 8 or len(expected) != 32:
                    return False
                actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
                return hmac.compare_digest(actual, expected)

            decoded = binascii.unhexlify(stored.encode("ascii"))
            if len(decoded) == 48:
                salt, expected = decoded[:16], decoded[16:]
                actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _LEGACY_ITERATIONS)
                return hmac.compare_digest(actual, expected)
            if len(decoded) == 32:
                actual = hashlib.sha256(password.encode("utf-8")).digest()
                return hmac.compare_digest(actual, decoded)
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            return False
        return False

    def password_needs_upgrade(self):
        return not self.password.startswith(_HASH_NAME + "$")

    def __str__(self):
        return self.username


class Category(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)

    def __str__(self):
        return self.name


class Product(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    buy_price = FloatField(null=False, default=0)
    sell_price = FloatField(null=False, default=0)
    image_path = CharField(max_length=FIELD_LENGTH, null=True)
    custom_product = BooleanField(default=False)
    category = ForeignKeyField(Category, backref="products", null=True, on_delete="SET NULL")

    def __str__(self):
        return self.name


class Receipt(BaseModel):
    payed = BooleanField(default=False)
    total_price = FloatField(null=False, default=0)
    user = ForeignKeyField(User, backref="receipts", on_delete="CASCADE")
    day_receipt_id = IntegerField(null=False)

    def __str__(self):
        return str(self.id)


class ReceiptProduct(BaseModel):
    receipt = ForeignKeyField(Receipt, backref="items", on_delete="CASCADE")
    product = ForeignKeyField(Product, backref="receipts", null=True, on_delete="SET NULL")
    buy_price = FloatField(null=False, default=0)
    sell_price = FloatField(null=False, default=0)
    quantity = IntegerField()

    def __str__(self):
        product_name = self.product.name if self.product_id else "محصول حذف‌شده"
        return "{}-{}".format(product_name, self.quantity)


class UnitEnum(str, Enum):
    KILOGRAM = "kg"
    METER = "m"
    LITRE = "l"
    PIECE = "pcs"


class Warehouse(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    price = FloatField(null=False, default=0)
    amount = FloatField(null=False, default=0)
    unit = CharField(choices=[(unit.value, unit.name) for unit in UnitEnum], max_length=10)


class CheckIn(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    check_id = CharField(max_length=FIELD_LENGTH)
    price = FloatField(null=False, default=0)
    date = CharField(max_length=FIELD_LENGTH)
    payed = BooleanField(default=False)


class CheckOut(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    check_id = CharField(max_length=FIELD_LENGTH)
    price = FloatField(null=False, default=0)
    date = CharField(max_length=FIELD_LENGTH)
    payed = BooleanField(default=False)


class IdempotencyRecord(BaseModel):
    """Persist sale request keys so a retried HTTP request cannot create a duplicate receipt."""
    key = CharField(max_length=128)
    user = ForeignKeyField(User, backref="idempotency_records", on_delete="CASCADE")
    request_hash = CharField(max_length=64)
    receipt = ForeignKeyField(Receipt, backref="idempotency_records", on_delete="CASCADE")

    class Meta:
        table_name = "api_idempotency_records"
        indexes = ((("user", "key"), True),)
