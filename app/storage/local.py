import os
import shutil
from typing import BinaryIO

from app.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    """Local filesystem storage implementation."""

    def __init__(self, base_dir: str):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve(self, relative_path: str) -> str:
        # Sanitize and prevent directory traversal
        clean_rel = os.path.normpath(relative_path).lstrip(r"\/")
        full_path = os.path.abspath(os.path.join(self.base_dir, clean_rel))
        if not full_path.startswith(self.base_dir):
            raise ValueError(f"Path traversal detected: {relative_path}")
        return full_path

    def save(self, relative_path: str, content: bytes) -> str:
        full_path = self._resolve(relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        # Write to temporary file first then replace to guarantee atomic write
        tmp_path = f"{full_path}.tmp"
        with open(tmp_path, "wb") as f:
            f.write(content)
        shutil.move(tmp_path, full_path)
        return relative_path

    def open(self, relative_path: str) -> BinaryIO:
        full_path = self._resolve(relative_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {relative_path}")
        return open(full_path, "rb")

    def exists(self, relative_path: str) -> bool:
        full_path = self._resolve(relative_path)
        return os.path.isfile(full_path)

    def get_absolute_path(self, relative_path: str) -> str:
        return self._resolve(relative_path)

    def get_size(self, relative_path: str) -> int:
        full_path = self._resolve(relative_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {relative_path}")
        return os.path.getsize(full_path)

    def delete(self, relative_path: str) -> bool:
        full_path = self._resolve(relative_path)
        if os.path.isfile(full_path):
            os.remove(full_path)
            return True
        return False
