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
    ApiSession, Category, CheckIn, CheckOut, IdempotencyRecord, Product, Receipt,
    ReceiptProduct, User, Warehouse,
)

TABLES = (
    User, Category, Product, Receipt, ReceiptProduct, Warehouse, CheckIn, CheckOut,
    AppSetting, CustomModelDefinition, CustomFieldDefinition, CustomFieldValue,
    CustomRecord, IdempotencyRecord, ApiSession,
)


def create_tables(database=None):
    """Create missing tables without dropping records from an existing database."""
    target = database or db
    target.create_tables(TABLES, safe=True)
    _migrate_existing_user_table(target)


def _migrate_existing_user_table(database):
    """Add account activation fields to existing databases without data loss."""
    table = User._meta.table_name
    columns = {column.name for column in database.get_columns(table)}
    for name, definition in (
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("requires_session_activation", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in columns:
            database.execute_sql(
                'ALTER TABLE "{}" ADD COLUMN "{}" {}'.format(table, name, definition)
            )
