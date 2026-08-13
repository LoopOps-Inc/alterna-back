import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.security import decode_jwt_token
from app.adapters.driven.cache.redis_service import RedisSessionCache

logger = logging.getLogger("altm_backend")

class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Exclude endpoints like open auth and health check
        path = request.url.path
        if path.endswith("/login") or path.endswith("/refresh") or path.endswith("/health") or "docs" in path or "openapi" in path:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authorization header missing or invalid"}
            )

        token = auth_header.split(" ")[1]
        payload = decode_jwt_token(token)
        if not payload:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token is invalid or expired"}
            )

        user_id = payload.get("sub")
        family_id = payload.get("family_id")

        # Verify active session on Redis session cache
        # Get redis_client from request state or construct a singleton instance of our memory redis
        # Let's use the default RedisSessionCache fallback if not configured
        session_cache = RedisSessionCache()
        token_family = await session_cache.get_token_family_by_token(token)
        if token_family and token_family.is_revoked:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Session has been revoked"}
            )

        # Attach claims to request state
        request.state.user_id = user_id
        request.state.family_id = family_id

        return await call_next(request)
