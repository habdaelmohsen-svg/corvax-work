from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.observability import HTTP_LATENCY, HTTP_REQUESTS, SECURITY_EVENTS

logger = logging.getLogger("corvax.http")


@dataclass(frozen=True)
class RatePolicy:
    name: str
    limit: int
    window_seconds: int = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Endpoint-aware sliding-window limiter.

    The limiter is deliberately dependency-light and effective immediately. For
    horizontally scaled deployments, the same policy can be moved to the edge/API
    gateway; the application-level protection remains a mandatory second layer.
    """

    _events: dict[str, deque[float]] = defaultdict(deque)
    _lock = asyncio.Lock()

    @staticmethod
    def _policy(request: Request) -> RatePolicy:
        path = request.url.path
        if path in {"/api/v1/auth/login", "/api/v1/auth/recover-admin"}:
            return RatePolicy("login", settings.rate_limit_login_per_minute)
        if path == "/api/v1/auth/refresh":
            return RatePolicy("refresh", settings.rate_limit_refresh_per_minute)
        if request.method == "POST" and path.rstrip("/") == "/api/v1/manufacturing/advanced/mrp-runs":
            return RatePolicy("mrp", settings.rate_limit_mrp_per_minute)
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return RatePolicy("read", settings.rate_limit_read_per_minute)
        return RatePolicy("write", settings.rate_limit_write_per_minute)

    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            not settings.rate_limit_enabled
            or not request.url.path.startswith("/api/")
            or (settings.environment.lower() == "testing" and not settings.enable_rate_limit_testing)
            or ((request.client.host if request.client else "") == "testclient" and not settings.enable_rate_limit_testing)
        ):
            return await call_next(request)
        policy = self._policy(request)
        client = request.client.host if request.client else "unknown"
        key = f"{client}|{policy.name}"
        now = time.monotonic()
        async with self._lock:
            queue = self._events[key]
            threshold = now - policy.window_seconds
            while queue and queue[0] <= threshold:
                queue.popleft()
            if len(queue) >= policy.limit:
                retry_after = max(1, int(policy.window_seconds - (now - queue[0])))
                SECURITY_EVENTS.labels(event="rate_limited").inc()
                return JSONResponse(
                    {"detail": "Rate limit exceeded", "policy": policy.name, "retry_after_seconds": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(policy.limit)},
                )
            queue.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(policy.limit)
        response.headers["X-RateLimit-Policy"] = policy.name
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Traceability, metrics, structured logs and conservative browser headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "Unhandled request exception",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status": 500, "elapsed_ms": round(elapsed_ms, 2)},
            )
            HTTP_REQUESTS.labels(method=request.method, route=request.url.path, status="500").inc()
            HTTP_LATENCY.labels(method=request.method, route=request.url.path).observe(elapsed_ms / 1000)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(method=request.method, route=route_path, status=str(status)).inc()
        HTTP_LATENCY.labels(method=request.method, route=route_path).observe(elapsed_ms / 1000)
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": route_path,
                "status": status,
                "elapsed_ms": round(elapsed_ms, 2),
                "client_ip": request.client.host if request.client else None,
            },
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
