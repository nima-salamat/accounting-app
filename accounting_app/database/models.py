"""Persistent domain models; field names preserve the existing database schema."""
import binascii
import hashlib
import hmac
import secrets
from enum import Enum

from peewee import BooleanField, CharField, DateField, DateTimeField, DecimalField, FloatField, ForeignKeyField, IntegerField, TextField

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
    is_active = BooleanField(default=True)
    requires_session_activation = BooleanField(default=False)
    max_active_sessions = IntegerField(default=1)

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
    track_stock = BooleanField(default=False)
    stock_quantity = FloatField(null=False, default=0)
    reorder_level = FloatField(null=False, default=0)

    def __str__(self):
        return self.name


class BusinessPartner(BaseModel):
    """Customer or supplier directory entry used by financial documents."""
    partner_type = CharField(max_length=16)
    name = CharField(max_length=FIELD_LENGTH)
    phone = CharField(max_length=80, null=True)
    email = CharField(max_length=FIELD_LENGTH, null=True)
    tax_id = CharField(max_length=80, null=True)
    address = TextField(null=True)
    payment_terms = CharField(max_length=128, null=True)
    credit_limit = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    is_active = BooleanField(default=True)
    notes = TextField(null=True)

    class Meta:
        table_name = "business_partners"
        indexes = (
            (("partner_type", "name"), False),
            (("tax_id",), False),
        )


class Receipt(BaseModel):
    payed = BooleanField(default=False)
    payment_method = CharField(max_length=24, default="cash")
    total_price = FloatField(null=False, default=0)
    user = ForeignKeyField(User, backref="receipts", on_delete="CASCADE")
    day_receipt_id = IntegerField(null=False)
    seat_number = CharField(max_length=32, null=True)

    def __str__(self):
        return str(self.id)


class ReceiptProduct(BaseModel):
    receipt = ForeignKeyField(Receipt, backref="items", on_delete="CASCADE")
    product = ForeignKeyField(Product, backref="receipts", null=True, on_delete="SET NULL")
    product_name = CharField(max_length=FIELD_LENGTH, default="")
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


class StockMovement(BaseModel):
    """Append-only audit record for inventory adjustments and sale consumption."""
    product = ForeignKeyField(Product, backref="stock_movements", on_delete="RESTRICT")
    user = ForeignKeyField(User, backref="stock_movements", null=True, on_delete="SET NULL")
    performed_by = CharField(max_length=FIELD_LENGTH, default="Unknown")
    quantity_change = FloatField()
    stock_before = FloatField()
    stock_after = FloatField()
    reason = CharField(max_length=32)
    reference_id = CharField(max_length=64, null=True)
    notes = TextField(null=True)

    class Meta:
        table_name = "stock_movements"
        indexes = (
            (("product", "created_at"), False),
            (("reference_id",), False),
        )


class SaleReturn(BaseModel):
    """A finalized refund tied to its original receipt and operator."""
    receipt = ForeignKeyField(Receipt, backref="returns", on_delete="RESTRICT")
    user = ForeignKeyField(User, backref="sale_returns", null=True, on_delete="SET NULL")
    operator_name = CharField(max_length=FIELD_LENGTH, default="Unknown")
    refund_method = CharField(max_length=24, default="cash")
    reason = CharField(max_length=64, default="customer_return")
    total_amount = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    notes = TextField(null=True)

    class Meta:
        table_name = "sale_returns"


class SaleReturnLine(BaseModel):
    sale_return = ForeignKeyField(SaleReturn, backref="items", on_delete="CASCADE")
    original_line = ForeignKeyField(ReceiptProduct, backref="return_lines", on_delete="RESTRICT")
    product = ForeignKeyField(Product, null=True, on_delete="SET NULL")
    product_name = CharField(max_length=FIELD_LENGTH, default="")
    quantity = IntegerField()
    unit_price = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    unit_cost = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    line_total = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)

    class Meta:
        table_name = "sale_return_lines"
        indexes = ((( "sale_return", "original_line"), False),)


class FiscalYear(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    start_date = DateField()
    end_date = DateField()
    status = CharField(max_length=16, default="open")
    opened_by_name = CharField(max_length=FIELD_LENGTH, default="Unknown")
    closed_by_name = CharField(max_length=FIELD_LENGTH, null=True)
    closed_at = DateTimeField(null=True)
    reopen_reason = TextField(null=True)

    class Meta:
        table_name = "fiscal_years"
        indexes = ((( "start_date", "end_date"), True),)


class LedgerAccount(BaseModel):
    code = CharField(max_length=32, unique=True)
    name = CharField(max_length=FIELD_LENGTH)
    account_type = CharField(max_length=24, default="asset")
    is_active = BooleanField(default=True)
    description = TextField(null=True)

    class Meta:
        table_name = "ledger_accounts"


class PurchaseInvoice(BaseModel):
    """Supplier invoice; posted invoices have a balanced journal and stock movements."""
    supplier = ForeignKeyField(BusinessPartner, backref="purchase_invoices", on_delete="RESTRICT")
    invoice_number = CharField(max_length=64)
    invoice_date = DateField()
    due_date = DateField(null=True)
    status = CharField(max_length=16, default="posted")
    total_amount = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    paid_amount = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    notes = TextField(null=True)
    created_by = ForeignKeyField(User, backref="purchase_invoices", null=True, on_delete="SET NULL")
    created_by_name = CharField(max_length=FIELD_LENGTH, default="Unknown")

    class Meta:
        table_name = "purchase_invoices"
        indexes = (
            (("supplier", "invoice_number"), True),
            (("invoice_date", "status"), False),
        )


class PurchaseInvoiceLine(BaseModel):
    invoice = ForeignKeyField(PurchaseInvoice, backref="items", on_delete="CASCADE")
    product = ForeignKeyField(Product, backref="purchase_lines", null=True, on_delete="SET NULL")
    product_name = CharField(max_length=FIELD_LENGTH)
    description = CharField(max_length=FIELD_LENGTH, default="")
    quantity = FloatField()
    unit_cost = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    line_total = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    stock_tracked = BooleanField(default=False)

    class Meta:
        table_name = "purchase_invoice_lines"


class PurchasePayment(BaseModel):
    invoice = ForeignKeyField(PurchaseInvoice, backref="payments", on_delete="RESTRICT")
    amount = DecimalField(max_digits=16, decimal_places=2, auto_round=True)
    paid_on = DateField()
    payment_method = CharField(max_length=24, default="cash")
    reference = CharField(max_length=FIELD_LENGTH, null=True)
    notes = TextField(null=True)
    user = ForeignKeyField(User, backref="purchase_payments", null=True, on_delete="SET NULL")
    operator_name = CharField(max_length=FIELD_LENGTH, default="Unknown")

    class Meta:
        table_name = "purchase_payments"


class JournalEntry(BaseModel):
    entry_number = CharField(max_length=48, unique=True)
    entry_date = DateField()
    description = TextField()
    reference = CharField(max_length=FIELD_LENGTH, null=True)
    status = CharField(max_length=16, default="posted")
    created_by = ForeignKeyField(User, backref="journal_entries", null=True, on_delete="SET NULL")
    created_by_name = CharField(max_length=FIELD_LENGTH, default="Unknown")
    debit_total = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    credit_total = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    is_year_closing = BooleanField(default=False)

    class Meta:
        table_name = "journal_entries"
        indexes = ((( "entry_date", "status"), False),)


class JournalLine(BaseModel):
    entry = ForeignKeyField(JournalEntry, backref="lines", on_delete="CASCADE")
    account = ForeignKeyField(LedgerAccount, backref="journal_lines", on_delete="RESTRICT")
    description = CharField(max_length=FIELD_LENGTH, default="")
    debit = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)
    credit = DecimalField(max_digits=16, decimal_places=2, auto_round=True, default=0)

    class Meta:
        table_name = "journal_lines"


class ExpenseRecord(BaseModel):
    """Posted operating expense with a matching journal entry."""
    description = TextField()
    category = CharField(max_length=FIELD_LENGTH, default="general")
    expense_date = DateField()
    amount = DecimalField(max_digits=16, decimal_places=2, auto_round=True)
    payment_method = CharField(max_length=24, default="cash")
    reference = CharField(max_length=FIELD_LENGTH, null=True)
    notes = TextField(null=True)
    expense_account = ForeignKeyField(LedgerAccount, backref="expenses", on_delete="RESTRICT")
    journal_entry = ForeignKeyField(JournalEntry, backref="expense_records", null=True, on_delete="SET NULL")
    created_by = ForeignKeyField(User, backref="expenses", null=True, on_delete="SET NULL")
    created_by_name = CharField(max_length=FIELD_LENGTH, default="Unknown")

    class Meta:
        table_name = "expense_records"
        indexes = (
            (("expense_date",), False),
            (("category", "expense_date"), False),
        )


class AuditEvent(BaseModel):
    """Append-only business audit entry with a non-null actor-name snapshot."""
    user = ForeignKeyField(User, backref="audit_events", null=True, on_delete="SET NULL")
    actor_name = CharField(max_length=FIELD_LENGTH, default="Unknown")
    action = CharField(max_length=48)
    resource = CharField(max_length=64)
    target_id = CharField(max_length=64, null=True)
    details = TextField(default="{}")
    remote_addr = CharField(max_length=128, null=True)

    class Meta:
        table_name = "audit_events"
        indexes = (
            (("created_at",), False),
            (("resource", "action"), False),
            (("actor_name", "created_at"), False),
        )


class Stocktake(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    status = CharField(max_length=16, default="draft")
    notes = TextField(null=True)
    created_by = ForeignKeyField(User, backref="stocktakes", null=True, on_delete="SET NULL")
    created_by_name = CharField(max_length=FIELD_LENGTH, default="Unknown")
    applied_at = DateTimeField(null=True)

    class Meta:
        table_name = "stocktakes"


class StocktakeLine(BaseModel):
    stocktake = ForeignKeyField(Stocktake, backref="lines", on_delete="CASCADE")
    product = ForeignKeyField(Product, backref="stocktake_lines", on_delete="RESTRICT")
    expected_quantity = FloatField()
    counted_quantity = FloatField()
    difference = FloatField()

    class Meta:
        table_name = "stocktake_lines"
        indexes = ((( "stocktake", "product"), True),)


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



class ApiSession(BaseModel):
    """Server-controlled login session with explicit approval and revocation state."""
    user = ForeignKeyField(User, backref="api_sessions", on_delete="CASCADE")
    status = CharField(max_length=24, default="active")
    client_name = CharField(max_length=FIELD_LENGTH, default="Desktop client")
    remote_addr = CharField(max_length=128, null=True)
    user_agent = CharField(max_length=FIELD_LENGTH, null=True)
    last_seen_at = DateTimeField(null=True)
    expires_at = DateTimeField()
    activated_at = DateTimeField(null=True)
    revoked_at = DateTimeField(null=True)
    revocation_reason = CharField(max_length=FIELD_LENGTH, null=True)

    class Meta:
        table_name = "api_sessions"
