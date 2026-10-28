"""Compatibility facade for database operations used by the existing UI."""
from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.models import User
from accounting_app.database.schema import create_tables


def initialize_database(path=None):
    """Initialize the database, optionally choosing an explicit SQLite path."""
    return initialize_db(path)


def create_db():
    initialize_database()
    with DBManager() as database:
        create_tables(database)


def create_admin():
    """Create the documented first-run admin only if it does not exist."""
    with DBManager():
        user = User.get_or_none(User.username == "admin")
        if user is None:
            user = User(username="admin", password="")
            user.set_password("admin")
            user.is_admin = True
            user.save(force_insert=True)
        elif not user.is_admin:
            user.is_admin = True
            user.save(only=[User.is_admin, User.updated_at])
        return user


__all__ = [
    "DBManager", "db", "initialize_db", "initialize_database", "create_db", "create_admin",
]
