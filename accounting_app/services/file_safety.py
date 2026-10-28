"""Filesystem path guards for resources owned by the application."""
from pathlib import Path


def is_managed_image_path(path):
    """Only allow cleanup of images stored under the application's images directory."""
    if not path:
        return False
    try:
        candidate = Path(path).expanduser().resolve()
        image_root = Path("images").resolve()
        return candidate != image_root and image_root in candidate.parents
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
