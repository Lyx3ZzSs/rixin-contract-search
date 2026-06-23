from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.errors import ApiError


@dataclass(frozen=True)
class AuthContext:
    owner_id: str


class ApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
            return await call_next(request)
        request.state.auth = AuthContext(owner_id=settings.INTERNAL_OWNER_ID)
        return await call_next(request)


def get_auth(request: Request) -> AuthContext:
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise ApiError("auth_unavailable", "Authentication context unavailable", 500)
    return auth
