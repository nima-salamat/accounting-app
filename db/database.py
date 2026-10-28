"""Compatibility imports for the modular database package."""
from accounting_app.database.connection import BaseModel, DB, db, initialize_db

__all__ = ["BaseModel", "DB", "db", "initialize_db"]
