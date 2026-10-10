"""Read-only VPS deployment preflight. Never prints configured values or secrets."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


def read_environment(path):
    values = {}
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid environment syntax on line {number}")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"Invalid environment field on line {number}")
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def real_hostname(value):
    host = value.lower()
    if (not host or host != host.rstrip(".") or len(host) > 253 or "." not in host
            or any(part in {"example", "invalid", "test", "localhost"} for part in host.split("."))
            or host in {"example.com", "example.org", "example.net"}
            or host == "trycloudflare.com" or host.endswith(".trycloudflare.com")
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                   for part in host.split("."))):
        raise ValueError("Deployment hostname must be a real public DNS name")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValueError("Deployment hostname must be a DNS name, not an IP address")


def required(values, key):
    value = values.get(key, "")
    if not value or "<" in value or ">" in value or "placeholder" in value.lower():
        raise ValueError(f"Missing or placeholder field: {key}")
    return value


def json_list(values, key):
    try:
        result = json.loads(required(values, key))
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON array: {key}") from None
    if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
        raise ValueError(f"Expected JSON string array: {key}")
    return set(result)


def database_target(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "postgresql+asyncpg" or parsed.hostname != "postgres"
            or not parsed.username or not parsed.password or not parsed.path.strip("/")
            or parsed.query or parsed.fragment):
        raise ValueError("VPS database URL requires asyncpg, private postgres host and encoded credentials")
    return parsed


def validate(env_file):
    source = Path(env_file).resolve()
    if not source.is_file():
        raise ValueError("Private deployment environment file not found")
    values = read_environment(source)
    tier = required(values, "DEPLOYMENT_TIER")
    if tier not in {"staging", "production"}:
        raise ValueError("DEPLOYMENT_TIER must be staging or production")
    if required(values, "COMPOSE_PROJECT_NAME") != f"canteen-{tier}":
        raise ValueError("COMPOSE_PROJECT_NAME must match the selected tier")
    release = required(values, "CANTEEN_IMAGE_TAG")
    if release in {"latest", "main", "master"} or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,100}", release):
        raise ValueError("Use a unique reviewed release/image identifier")
    hosts = {key: real_hostname(required(values, key))
             for key in ("STUDENT_HOST", "ADMIN_HOST", "API_HOST")}
    if len(set(hosts.values())) != 3:
        raise ValueError("Student, Admin and API hostnames must be distinct")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", required(values, "ACME_EMAIL")):
        raise ValueError("ACME_EMAIL must be an operator email address")
    for key in ("POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"):
        required(values, key)
    volumes = [required(values, key) for key in ("POSTGRES_VOLUME_NAME", "REDIS_VOLUME_NAME")]
    if len(set(volumes)) != 2 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", item) for item in volumes):
        raise ValueError("PostgreSQL and Redis require distinct explicit volume identities")
    # A tier-specific volume label prevents accidentally selecting another tier.
    # Existing production volumes are allowed after the operator's backup/identity review.
    if tier == "staging" and any("staging" not in item.lower() for item in volumes):
        raise ValueError("Staging volume identities must include staging")

    repo = Path(__file__).resolve().parents[1]
    private_files = []
    for key in ("BACKEND_ENV_FILE", "MIGRATION_ENV_FILE"):
        path = Path(required(values, key))
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"{key} requires an existing absolute private file")
        path = path.resolve()
        if path == repo or repo in path.parents:
            raise ValueError(f"{key} must remain outside the project repository")
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError(f"{key} must not be readable by group/other users")
        private_files.append(path)
    if private_files[0] == private_files[1]:
        raise ValueError("Runtime and migration credentials require distinct private files")

    backend, migration = [read_environment(path) for path in private_files]
    student = "https://" + hosts["STUDENT_HOST"]
    admin = "https://" + hosts["ADMIN_HOST"]
    for data in (backend, migration):
        if data.get("ENVIRONMENT") != "production":
            raise ValueError("Both tiers require strict ENVIRONMENT=production")
        for key in ("AUTO_CREATE_SCHEMA", "ENABLE_DEMO_DATA"):
            if data.get(key, "").lower() != "false":
                raise ValueError(f"Disable unsafe deployment setting: {key}")
        for key in ("SESSION_COOKIE_MODE_ENABLED", "RATE_LIMIT_ENABLED"):
            if data.get(key, "").lower() != "true":
                raise ValueError(f"VPS cookie/proxy deployment requires {key}=true")
        if data.get("PAYMENT_PROVIDER") != "disabled" or data.get("PASSCODE_RECOVERY_ENABLED", "").lower() != "false":
            raise ValueError("Initial deployment must keep payment/recovery disabled until verified")
        secret = required(data, "SECRET_KEY")
        if len(secret.encode()) < 32 or secret.startswith("canteen_super_secure_"):
            raise ValueError("Use a fresh random signing value with at least 32 bytes")
        if json_list(data, "CORS_ORIGINS") != {student, admin, "https://localhost"}:
            raise ValueError("CORS must contain exactly the configured web origins and native Android origin")
        if json_list(data, "STUDENT_CORS_ORIGINS") != {student} or json_list(data, "ADMIN_CORS_ORIGINS") != {admin}:
            raise ValueError("Assign disjoint exact web-cookie origins to each role")
        if json_list(data, "TRUSTED_HOSTS") != set(hosts.values()) | {"127.0.0.1"}:
            raise ValueError("TRUSTED_HOSTS must match deployment names and internal readiness host")
        if data.get("REDIS_URL") != "redis://redis:6379/0":
            raise ValueError("VPS template requires its private Redis service")
    runtime_db = database_target(required(backend, "DATABASE_URL"))
    migration_db = database_target(migration.get("MIGRATION_DATABASE_URL") or required(migration, "DATABASE_URL"))
    if ((runtime_db.hostname, runtime_db.port, runtime_db.path)
            != (migration_db.hostname, migration_db.port, migration_db.path)):
        raise ValueError("Migration and runtime must target the same selected database")
    if runtime_db.path.strip("/") != values["POSTGRES_DB"]:
        raise ValueError("Backend database must match POSTGRES_DB")
    if runtime_db.username in {values["POSTGRES_USER"], migration_db.username}:
        raise ValueError("Runtime requires its own least-privilege role, separate from admin/migrations")
    return tier


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    try:
        tier = validate(args.env_file)
    except (ValueError, OSError) as error:
        # Messages name fields only; never print URLs, values, paths or secrets.
        message = str(error) if isinstance(error, ValueError) else "Private configuration could not be read"
        parser.exit(1, f"Deployment preflight failed: {message}\n")
    print(f"Deployment preflight passed ({tier}); values and secrets omitted. No resources changed.")
