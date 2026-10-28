"""Compatibility facade for database operations used by the existing UI."""
from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.models import User
from accounting_app.database.schema import create_tables
from accounting_app.services.validation import validate_password, validate_username


def initialize_database(path=None):
    """Initialize the database, optionally choosing an explicit SQLite path."""
    return initialize_db(path)


def create_db():
    """Create any missing tables without altering existing records."""
    initialize_database()
    with DBManager() as database:
        create_tables(database)


def create_admin(username=None, password=None):
    """Create an administrator only with explicit credentials; never ship a default password."""
    if not username or not password:
        raise ValueError("برای ساخت مدیر باید نام کاربری و رمز عبور صریحاً تعیین شوند.")
    normalized_username = validate_username(username)
    validated_password = validate_password(password)
    with DBManager():
        existing = User.get_or_none(User.username == normalized_username)
        if existing is not None:
            raise ValueError("این نام کاربری از قبل ثبت شده است.")
        user = User(username=normalized_username, password="", is_admin=True)
        user.set_password(validated_password)
        user.save(force_insert=True)
        return user


__all__ = [
    "DBManager", "db", "initialize_db", "initialize_database", "create_db", "create_admin",
]
