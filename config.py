import os
from pathlib import Path



db_path = Path(os.getenv("LOCALAPPDATA")) / "accounting_app" / "app.db"

db_path.parent.mkdir(parents=True, exist_ok=True)

keys_path = Path(os.getenv("LOCALAPPDATA")) / "accounting_app" / "keys.json"

if not os.path.exists(db_path):
    open(db_path, 'w').close()
    

if not os.path.exists(keys_path):
    open(keys_path, 'w').close()

DATABASE = {
    "DEFAULT": {
        "NAME" : db_path,
        
    }
}

FIELD_LENGTH = 256
USERNAME_MIN_LENGTH = 4
PASSWORD_MIN_LENGTH = 4
