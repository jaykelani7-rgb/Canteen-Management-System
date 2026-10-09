"""PORT-aware entry point for Docker/managed hosting. Never runs migrations/seeds."""
import os
import uvicorn


def bounded_integer(name: str, default: str, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError:
        raise RuntimeError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} is outside the supported range")
    return value


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=bounded_integer("PORT", "8000", 1, 65535),
        workers=bounded_integer("WEB_CONCURRENCY", "1", 1, 8),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "*"),
        timeout_graceful_shutdown=25,
    )
