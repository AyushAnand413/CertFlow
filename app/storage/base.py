from abc import ABC, abstractmethod
from typing import BinaryIO


class BaseStorage(ABC):
    """Abstract interface defining storage operations for generated assets."""

    @abstractmethod
    def save(self, relative_path: str, content: bytes) -> str:
        """Save binary content to the relative path and return the stored identifier/path."""
        pass

    @abstractmethod
    def open(self, relative_path: str) -> BinaryIO:
        """Open a file-like stream for reading the stored asset."""
        pass

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """Check whether an asset exists at the specified relative path."""
        pass

    @abstractmethod
    def get_absolute_path(self, relative_path: str) -> str:
        """Return the physical filesystem path (for local storage) or URI."""
        pass

    @abstractmethod
    def get_size(self, relative_path: str) -> int:
        """Return size in bytes of the asset."""
        pass

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """Delete an asset if it exists."""
        pass
