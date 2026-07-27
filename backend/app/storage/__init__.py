"""File storage adapters. Local filesystem for development; an S3-compatible adapter for
deployment (Supabase Storage, MinIO, AWS S3), selected by STORAGE_BACKEND (docs/08 D14)."""

from app.storage.base import StorageBackend
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage

__all__ = ["LocalStorage", "S3Storage", "StorageBackend"]
