"""Distributed limits use separate IP and account budgets, without raw identifiers."""
import hashlib
import hmac
import time
from collections import OrderedDict
from fastapi import HTTPException, Request
from config import settings
from database import get_redis_client

_LOCAL_WINDOWS: OrderedDict[str, tuple[int, float]] = OrderedDict()
_SCRIPT = """
local value = redis.call('INCR', KEYS[1])
if value == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return value
"""


async def enforce_rate_limit(request: Request, scope: str, identity: str = "", limit: int | None = None, window: int | None = None) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    maximum = limit or settings.AUTH_RATE_LIMIT
    seconds = window or settings.AUTH_RATE_WINDOW_SECONDS
    client = request.client.host if request.client else "unknown"
    def digest(value):
        return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
    budgets = [("canteen:rate:" + scope + ":ip:" + digest(client), maximum * 5 if identity else maximum)]
    if identity:
        budgets.append(("canteen:rate:" + scope + ":account:" + digest(identity.lower()), maximum))
    for key, budget in budgets:
        try:
            count = int(await get_redis_client().eval(_SCRIPT, 1, key, seconds))
        except Exception:
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=503, detail="Service temporarily unavailable")
            now = time.monotonic()
            count, expires = _LOCAL_WINDOWS.get(key, (0, now + seconds))
            if expires <= now:
                count, expires = 0, now + seconds
            count += 1
            _LOCAL_WINDOWS[key] = (count, expires)
            _LOCAL_WINDOWS.move_to_end(key)
            while len(_LOCAL_WINDOWS) > 10000:
                _LOCAL_WINDOWS.popitem(last=False)
        if count > budget:
            raise HTTPException(status_code=429, detail="Too many attempts. Please try again later", headers={"Retry-After": str(seconds)})
