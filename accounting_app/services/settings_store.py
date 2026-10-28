"""Safe JSON persistence for local desktop preferences."""
import json
import os
import tempfile
from pathlib import Path


def load_settings(path):
    """Load a settings dictionary; recover cleanly from missing or invalid files."""
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            settings = json.load(stream)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return settings if isinstance(settings, dict) else {}


def save_settings(path, settings):
    """Atomically replace the JSON file so interruption cannot leave it truncated."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=str(destination.parent),
            prefix=destination.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(settings, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp_path), str(destination))
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
