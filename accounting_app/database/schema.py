"""Schema bootstrap kept separate from model declarations."""
from accounting_app.database.connection import db
from accounting_app.config import FIELD_LENGTH
from accounting_app.database.extension_models import (
    AppSetting,
    CustomFieldDefinition,
    CustomFieldValue,
    CustomModelDefinition,
    CustomRecord,
)
from accounting_app.database.models import (
    ApiSession, Category, CheckIn, CheckOut, IdempotencyRecord, Product, Receipt,
    ReceiptProduct, StockMovement, User, Warehouse, SaleReturn, SaleReturnLine,
    FiscalYear, LedgerAccount, JournalEntry, JournalLine, AuditEvent, Stocktake, StocktakeLine,
    BusinessPartner, PurchaseInvoice, PurchaseInvoiceLine, PurchasePayment, ExpenseRecord,
)

TABLES = (
    User, Category, Product, Receipt, ReceiptProduct, Warehouse, CheckIn, CheckOut,
    AppSetting, CustomModelDefinition, CustomFieldDefinition, CustomFieldValue,
    CustomRecord, IdempotencyRecord, ApiSession, StockMovement, SaleReturn, SaleReturnLine,
    FiscalYear, LedgerAccount, JournalEntry, JournalLine, AuditEvent, Stocktake, StocktakeLine,
    BusinessPartner, PurchaseInvoice, PurchaseInvoiceLine, PurchasePayment, ExpenseRecord,
)


def create_tables(database=None):
    """Create missing tables without dropping records from an existing database."""
    target = database or db
    target.create_tables(TABLES, safe=True)
    _migrate_existing_user_table(target)
    _migrate_existing_receipt_table(target)
    _migrate_existing_product_table(target)
    _migrate_existing_receipt_product_table(target)
    _migrate_existing_sale_return_line_table(target)


def _migrate_existing_user_table(database):
    """Add account activation fields to existing databases without data loss."""
    table = User._meta.table_name
    columns = {column.name for column in database.get_columns(table)}
    for name, definition in (
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("requires_session_activation", "INTEGER NOT NULL DEFAULT 0"),
        ("max_active_sessions", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if name not in columns:
            database.execute_sql(
                'ALTER TABLE "{}" ADD COLUMN "{}" {}'.format(table, name, definition)
            )


def _migrate_existing_product_table(database):
    """Add stock tracking columns to an existing product table without data loss."""
    table = Product._meta.table_name
    columns = {column.name for column in database.get_columns(table)}
    for name, definition in (
        ("track_stock", "INTEGER NOT NULL DEFAULT 0"),
        ("stock_quantity", "REAL NOT NULL DEFAULT 0"),
        ("reorder_level", "REAL NOT NULL DEFAULT 0"),
    ):
        if name not in columns:
            database.execute_sql(
                'ALTER TABLE "{}" ADD COLUMN "{}" {}'.format(table, name, definition)
            )


def _migrate_existing_receipt_product_table(database):
    """Snapshot item names onto receipt lines so historical invoices survive product edits/deletes."""
    table = ReceiptProduct._meta.table_name
    columns = {column.name for column in database.get_columns(table)}
    if "product_name" not in columns:
        database.execute_sql(
            'ALTER TABLE "{}" ADD COLUMN "product_name" VARCHAR({}) NOT NULL DEFAULT \'\''.format(
                table, FIELD_LENGTH
            )
        )
    # Backfill existing rows once, before later product deletions can null their FK.
    database.execute_sql(
        'UPDATE "{}" SET "product_name" = ('
        'SELECT "name" FROM "{}" WHERE "{}"."id" = "{}"."product_id"'
        ') WHERE ("product_name" = "" OR "product_name" IS NULL) AND "product_id" IS NOT NULL'.format(
            table, Product._meta.table_name, Product._meta.table_name, table
        )
    )


def _migrate_existing_sale_return_line_table(database):
    """Add unit-cost snapshot for returns without losing existing return records."""
    table = SaleReturnLine._meta.table_name
    columns = {column.name for column in database.get_columns(table)}
    if "unit_cost" not in columns:
        database.execute_sql(
            'ALTER TABLE "{}" ADD COLUMN "unit_cost" DECIMAL(16, 2) NOT NULL DEFAULT 0'.format(table)
        )


def _migrate_existing_receipt_table(database):
    """Add receipt numbering columns without changing any already-issued invoice number."""
    table = Receipt._meta.table_name
    columns = {column.name for column in database.get_columns(table)}
    if "payment_method" not in columns:
        database.execute_sql(
            'ALTER TABLE "{}" ADD COLUMN "payment_method" VARCHAR(24) NOT NULL DEFAULT \'cash\''.format(table)
        )
    if "seat_number" not in columns:
        database.execute_sql(
            'ALTER TABLE "{}" ADD COLUMN "seat_number" VARCHAR(32)'.format(table)
        )
    if "invoice_sequence" not in columns:
        database.execute_sql(
            'ALTER TABLE "{}" ADD COLUMN "invoice_sequence" INTEGER'.format(table)
        )
    if "invoice_number" not in columns:
        database.execute_sql(
            'ALTER TABLE "{}" ADD COLUMN "invoice_number" VARCHAR(120)'.format(table)
        )
    # Backfill global counters but keep old printed numbers unchanged.
    highest = database.execute_sql(
        'SELECT COALESCE(MAX("invoice_sequence"), 0) FROM "{}"'.format(table)
    ).fetchone()[0] or 0
    missing = database.execute_sql(
        'SELECT "id" FROM "{}" WHERE "invoice_sequence" IS NULL ORDER BY "created_at", "id"'.format(table)
    ).fetchall()
    for (receipt_id,) in missing:
        highest += 1
        database.execute_sql(
            'UPDATE "{}" SET "invoice_sequence" = ? WHERE "id" = ?'.format(table),
            (highest, receipt_id),
        )
    database.execute_sql(
        'CREATE UNIQUE INDEX IF NOT EXISTS "idx_receipts_invoice_sequence_unique" '
        'ON "{}" ("invoice_sequence") WHERE "invoice_sequence" IS NOT NULL'.format(table)
    )
    database.execute_sql(
        'CREATE UNIQUE INDEX IF NOT EXISTS "idx_receipts_invoice_number_unique" '
        'ON "{}" ("invoice_number") WHERE "invoice_number" IS NOT NULL'.format(table)
    )
