from functools import lru_cache

from app.config import get_settings
from app.storage.base import BaseStorage
from app.storage.local import LocalStorage


@lru_cache()
def get_storage() -> BaseStorage:
    """Return default storage provider configured for the application."""
    settings = get_settings()
    return LocalStorage(settings.STORAGE_DIR)


__all__ = ["BaseStorage", "LocalStorage", "get_storage"]
