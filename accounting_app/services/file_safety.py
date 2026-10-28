"""Filesystem path guards for resources owned by the application."""
from pathlib import Path
import re


def is_managed_image_path(path):
    """Only allow cleanup of images stored under the application's images directory."""
    if not path:
        return False
    try:
        candidate = Path(path).expanduser().resolve()
        image_root = Path("images").resolve()
        managed_name = re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:\\.[A-Za-z0-9]{1,8})?",
            candidate.name,
        )
        return managed_name is not None and candidate != image_root and image_root in candidate.parents
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
