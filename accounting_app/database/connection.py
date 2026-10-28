"""SQLite connection lifecycle and transaction management."""
from datetime import datetime
from pathlib import Path
from threading import RLock, local
import uuid

from peewee import DatabaseProxy, DateTimeField, Model, SqliteDatabase, UUIDField

from accounting_app.config import get_database_path

db = DatabaseProxy()
_real_database = None
_database_path = None
_initialization_lock = RLock()
_transaction_state = local()


class DB:
    """Backward-compatible access to the configured database path."""

    @staticmethod
    def get_default_data_base():
        return current_database_path() if _real_database is not None else get_database_path()

    @staticmethod
    def get_data_base(name="NAME"):
        if name not in ("NAME", "DEFAULT"):
            raise KeyError("Only the default database is configured.")
        return DB.get_default_data_base()


def initialize_db(path=None):
    """Initialize the shared Peewee proxy, keeping explicit test DBs isolated."""
    global _real_database, _database_path
    if path is None and _real_database is not None:
        return db
    resolved_path = Path(path or get_database_path()).expanduser()
    with _initialization_lock:
        if _real_database is not None and _database_path == resolved_path:
            return db
        if _real_database is not None and not _real_database.is_closed():
            raise RuntimeError("Close the current database connection before switching databases.")
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        _real_database = SqliteDatabase(
            str(resolved_path), timeout=30,
            pragmas={"foreign_keys": 1, "journal_mode": "wal", "synchronous": "normal"},
        )
        _database_path = resolved_path
        db.initialize(_real_database)
        return db


def current_database_path():
    """Return the active database path, initializing the proxy if needed."""
    if _real_database is None:
        initialize_db()
    return _database_path


class BaseModel(Model):
    """Base record with UUID identity and automatic timestamps."""
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        database = db

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)


class DBManager:
    """Provide atomic scopes with thread-local nesting and predictable cleanup.

    Nested contexts create savepoints, while the outermost managed scope closes
    the thread's SQLite connection even if a preceding ORM query auto-opened it.
    """

    def __init__(self):
        self._depth = 0
        self._outermost = False
        self._transaction = None

    def __enter__(self):
        initialize_db()
        self._depth = getattr(_transaction_state, "depth", 0)
        self._outermost = self._depth == 0
        if db.is_closed():
            db.connect(reuse_if_open=True)
        _transaction_state.depth = self._depth + 1
        self._transaction = db.atomic()
        try:
            self._transaction.__enter__()
        except Exception:
            _transaction_state.depth = self._depth
            if self._outermost and not db.is_closed():
                db.close()
            raise
        return db

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._transaction is not None:
                return self._transaction.__exit__(exc_type, exc_value, traceback)
            return False
        finally:
            _transaction_state.depth = self._depth
            if self._outermost and not db.is_closed():
                db.close()
