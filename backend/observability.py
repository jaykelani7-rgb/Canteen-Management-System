"""Request metadata logging without request bodies, tokens, query strings or secrets."""
import json
import logging
import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("canteen")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def log_event(event: str, **fields) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault("Cache-Control", "no-store")
        log_event("request", request_id=request_id, method=request.method, path=request.url.path,
                  status=response.status_code, duration_ms=round((time.monotonic() - started) * 1000, 2))
        return response
