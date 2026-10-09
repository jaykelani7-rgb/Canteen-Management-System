"""Offline preflight for free managed staging; never connects, migrates or prints secrets.

Populate the operator's private process environment, then run this script.
Use --local-ca when also checking the operator's local PEM trust bundle.
This helper does not load .env files or import the backend's settings module.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import ssl
from typing import Mapping
from urllib.parse import parse_qs, urlsplit


def public_hostname(host: str | None) -> bool:
    if not host or host != host.strip() or host.endswith("."):
        return False
    lowered = host.lower()
    try:
        ipaddress.ip_address(lowered)
        return False
    except ValueError:
        pass
    labels = lowered.split(".")
    forbidden = {"localhost", "example", "invalid", "test", "local", "internal", "lan", "corp", "private", "intranet", "onion"}
    rejected_domains = {
        "example.com", "example.org", "example.net", "home.arpa", "trycloudflare.com",
        "ngrok.io", "ngrok.app", "ngrok-free.app", "ngrok-free.dev", "loca.lt",
        "localtunnel.me", "localhost.run", "lhr.life", "serveo.net", "tunnelmole.net",
        "pinggy.link", "pinggy.io", "zrok.io",
    }
    return (len(labels) >= 2 and len(lowered) <= 253
            and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
            and labels[-1] not in forbidden
            and not any(lowered == domain or lowered.endswith("." + domain) for domain in rejected_domains))


def explicit_origin(value: object, *, native: bool = False) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    if native and value == "https://localhost":
        return True
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and public_hostname(parsed.hostname)
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and not parsed.path and not parsed.query and not parsed.fragment
                and "*" not in value and "\\" not in value)
    except ValueError:
        return False


def check_environment(env: Mapping[str, str], *, local_ca: bool = False) -> list[str]:
    """Return fixed diagnostic strings only. Never include supplied input values."""
    errors: list[str] = []
    expected = {
        "ENVIRONMENT": "production", "PORT": "10000", "WEB_CONCURRENCY": "1",
        "SESSION_COOKIE_MODE_ENABLED": "false", "RATE_LIMIT_ENABLED": "true",
        "AUTO_CREATE_SCHEMA": "false", "ENABLE_DEMO_DATA": "false",
        "PAYMENT_PROVIDER": "disabled", "PASSCODE_RECOVERY_ENABLED": "false",
    }
    for name, value in expected.items():
        if env.get(name, "").strip().lower() != value:
            errors.append(f"{name}: required free-staging setting is missing or unsafe")

    for name, minimum, maximum in (("DATABASE_POOL_SIZE", 1, 2), ("DATABASE_MAX_OVERFLOW", 0, 3)):
        try:
            valid = minimum <= int(env.get(name, "")) <= maximum
        except ValueError:
            valid = False
        if not valid:
            errors.append(f"{name}: set a value within the small staging pool limit")

    secret = env.get("SECRET_KEY", "")
    if (len(secret.encode()) < 32 or len(set(secret)) < 10
            or secret.startswith("canteen_super_secure_") or any(c in secret for c in "\r\n")):
        errors.append("SECRET_KEY: provide a fresh random signing secret of at least 32 bytes privately")

    try:
        raw_db = env.get("DATABASE_URL", "")
        db = urlsplit(raw_db)
        query = parse_qs(db.query, keep_blank_values=True)
        valid_db = (not any(character.isspace() for character in raw_db)
                    and db.scheme == "postgresql+asyncpg" and public_hostname(db.hostname)
                    and bool(db.username) and bool(db.password) and db.port in (None, 5432)
                    and len(db.path) > 1 and not db.fragment
                    and query == {"ssl": ["verify-full"]})
    except ValueError:
        valid_db = False
    if not valid_db:
        errors.append("DATABASE_URL: require authenticated public PostgreSQL asyncpg URL with ssl=verify-full only")

    ca_path = env.get("PGSSLROOTCERT", "")
    if local_ca:
        try:
            ssl.create_default_context(cafile=ca_path)
        except (OSError, ssl.SSLError, ValueError):
            errors.append("PGSSLROOTCERT: local operator requires a readable valid PEM CA bundle")
    elif ca_path != "/etc/ssl/certs/ca-certificates.crt":
        errors.append("PGSSLROOTCERT: use the Docker runtime's public system CA bundle")

    try:
        raw_redis = env.get("REDIS_URL", "")
        redis = urlsplit(raw_redis)
        query = parse_qs(redis.query, keep_blank_values=True)
        allowed = {"ssl_cert_reqs": ["required"], "ssl_check_hostname": ["true"]}
        valid_redis = (not any(character.isspace() for character in raw_redis)
                       and redis.scheme == "rediss" and public_hostname(redis.hostname)
                       and bool(redis.password) and redis.port in (None, 6379)
                       and redis.path in ("", "/0") and not redis.fragment
                       and all(key in allowed and value == allowed[key] for key, value in query.items()))
    except ValueError:
        valid_redis = False
    if not valid_redis:
        errors.append("REDIS_URL: require authenticated public Redis TCP/TLS with certificate and hostname verification")

    arrays: dict[str, list[str]] = {}
    for name in ("CORS_ORIGINS", "STUDENT_CORS_ORIGINS", "ADMIN_CORS_ORIGINS", "TRUSTED_HOSTS"):
        try:
            raw = json.loads(env.get(name, ""))
            valid_array = isinstance(raw, list) and all(isinstance(item, str) for item in raw)
        except (ValueError, TypeError):
            valid_array = False
        if not valid_array:
            errors.append(f"{name}: require an explicit JSON string array")
            arrays[name] = []
        else:
            arrays[name] = raw

    cors = arrays["CORS_ORIGINS"]
    if not cors or any(not explicit_origin(value, native=True) for value in cors):
        errors.append("CORS_ORIGINS: require exact HTTPS web origins or the exact native https://localhost origin")
    for name in ("STUDENT_CORS_ORIGINS", "ADMIN_CORS_ORIGINS"):
        values = arrays[name]
        if any(not explicit_origin(value) for value in values) or not set(values).issubset(cors):
            errors.append(f"{name}: require public HTTPS web origins also listed in CORS_ORIGINS")
    if set(arrays["STUDENT_CORS_ORIGINS"]) & set(arrays["ADMIN_CORS_ORIGINS"]):
        errors.append("ROLE_ORIGINS: Student and Admin web origins must be separate")
    hosts = arrays["TRUSTED_HOSTS"]
    if (not any(public_hostname(value) for value in hosts)
            or any(value != "127.0.0.1" and not public_hostname(value) for value in hosts)):
        errors.append("TRUSTED_HOSTS: require actual public API hostname; permit only 127.0.0.1 for local probes")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-ca", action="store_true", help="Verify the local migration/operator CA PEM file")
    args = parser.parse_args()
    errors = check_environment(os.environ, local_ca=args.local_ca)
    if errors:
        print("Managed staging configuration FAILED (values omitted):")
        for message in errors:
            print(f"- {message}")
        return 1
    print("Managed staging configuration PASSED; no connections or resources created.")
    print("Deployment still requires published reviewed source, safely migrated staging data, and public HTTPS health/readiness verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
