"""ORM models.

Importing this package registers every table on `Base.metadata`. `migrations/env.py` imports
it so Alembic autogenerate sees the full schema; forgetting a model here would silently
produce a migration that drops its table.
"""

from app.models.refresh_session import RefreshSession
from app.models.user import User

__all__ = ["RefreshSession", "User"]
