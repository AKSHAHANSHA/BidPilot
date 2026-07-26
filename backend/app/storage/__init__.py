"""File storage adapters. Local filesystem now; an S3-compatible adapter only when deployment
requires it (docs/08 D14)."""

from app.storage.base import StorageBackend
from app.storage.local import LocalStorage

__all__ = ["LocalStorage", "StorageBackend"]
