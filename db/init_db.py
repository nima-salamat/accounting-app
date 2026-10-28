"""Compatibility wrapper for schema creation."""
from accounting_app.database.connection import db
from accounting_app.database.schema import create_tables


def create(database=None):
    return create_tables(database or db)
