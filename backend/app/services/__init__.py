"""Application services — orchestration between the API and the persistence/domain layers.

A service may use repositories, domain rules, and adapters. It never touches HTTP objects and
never commits: the request or job owns the transaction boundary.
"""

from app.services.auth_service import AuthResult, AuthService, ClientContext

__all__ = ["AuthResult", "AuthService", "ClientContext"]
