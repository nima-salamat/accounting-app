"""Cross-platform application paths and configuration defaults."""
import os
from pathlib import Path

APP_DIRECTORY = "accounting_app"
FIELD_LENGTH = 256
USERNAME_MIN_LENGTH = 4
PASSWORD_MIN_LENGTH = 4


def get_data_dir(environ=None, *, is_windows=None, home=None):
    """Return the per-user data directory without creating it."""
    env = os.environ if environ is None else environ
    override = env.get("ACCOUNTING_APP_DATA_DIR")
    if override:
        return Path(override).expanduser()
    home_path = Path(home).expanduser() if home is not None else Path.home()
    if is_windows is None:
        is_windows = os.name == "nt"
    if is_windows:
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        if base:
            return Path(base).expanduser() / APP_DIRECTORY
        return home_path / "AppData" / "Local" / APP_DIRECTORY
    xdg_data_home = env.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / APP_DIRECTORY
    return home_path / ".local" / "share" / APP_DIRECTORY


def get_database_path(environ=None, *, is_windows=None, home=None):
    """Return the SQLite path, honoring an explicit database override."""
    env = os.environ if environ is None else environ
    override = env.get("ACCOUNTING_APP_DB_PATH")
    if override:
        return Path(override).expanduser()
    return get_data_dir(env, is_windows=is_windows, home=home) / "app.db"


def get_keys_path(environ=None, *, is_windows=None, home=None):
    """Return the local preferences path."""
    return get_data_dir(environ, is_windows=is_windows, home=home) / "keys.json"


def ensure_data_dir(environ=None, *, is_windows=None, home=None):
    """Create and return the per-user application data directory."""
    directory = get_data_dir(environ, is_windows=is_windows, home=home)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# Compatibility constants used by the existing UI modules.
DATA_DIR = get_data_dir()
DB_PATH = get_database_path()
KEYS_PATH = get_keys_path()
db_path = DB_PATH
keys_path = KEYS_PATH
DATABASE = {"DEFAULT": {"NAME": DB_PATH}}
