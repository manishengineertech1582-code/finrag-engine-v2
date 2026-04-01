"""
Supabase JWT Authentication Middleware
========================================
Extracts user_id from Supabase Bearer tokens and injects it into
the request state so route handlers can use it without manual user_id passing.

When SUPABASE_JWT_SECRET is not configured, middleware is a no-op pass-through
(safe for local dev without Supabase).
"""

import logging
from typing import Callable

import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Routes that don't require authentication
_PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/"}


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    """
    Extract user_id from Supabase JWT Bearer token.

    - If SUPABASE_JWT_SECRET is not set: passes through silently (dev mode).
    - If token is present and valid: injects request.state.user_id.
    - If token is present and invalid: returns 401.
    - If token is absent on protected routes: request.state.user_id = None.
    """

    def __init__(self, app, jwt_secret: str):
        super().__init__(app)
        self._jwt_secret = jwt_secret

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request.state.user_id = None

        # No secret configured → dev mode, skip validation
        if not self._jwt_secret:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    self._jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                request.state.user_id = payload.get("sub")
            except jwt.ExpiredSignatureError:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token expired. Please sign in again."},
                )
            except jwt.InvalidTokenError as exc:
                logger.warning("Invalid JWT token: %s", exc)
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication token."},
                )

        return await call_next(request)
