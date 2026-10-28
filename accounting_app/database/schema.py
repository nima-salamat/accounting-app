"""Schema bootstrap kept separate from model declarations."""
from accounting_app.database.connection import db
from accounting_app.database.extension_models import (
    AppSetting,
    CustomFieldDefinition,
    CustomFieldValue,
    CustomModelDefinition,
    CustomRecord,
)
from accounting_app.database.models import (
    Category, CheckIn, CheckOut, IdempotencyRecord, Product, Receipt,
    ReceiptProduct, User, Warehouse,
)

TABLES = (
    User, Category, Product, Receipt, ReceiptProduct, Warehouse, CheckIn, CheckOut,
    AppSetting, CustomModelDefinition, CustomFieldDefinition, CustomFieldValue,
    CustomRecord, IdempotencyRecord,
)


def create_tables(database=None):
    """Create missing tables without dropping records from an existing database."""
    target = database or db
    target.create_tables(TABLES, safe=True)
