"""Private operator helper for one new staging runtime role; default is read-only.

Run with the backend Python environment. A named libpq service/password file stays
outside the repository. This helper never runs migrations, restores data, resets
passwords, modifies application rows, or provisions a cloud account.
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
import warnings
from dataclasses import dataclass

import psycopg2
from psycopg2 import extensions, sql


HEAD = "0005_secure_recovery"
APP_TABLES = frozenset({
    "weekly_menu", "ala_carte", "food_items", "admin_users", "students", "orders",
    "wallet_transactions", "notifications", "feedback_reviews", "password_reset_otps",
    "mess_plans", "mess_subscriptions", "mess_meal_attendance", "notification_reads",
    "recovery_challenges", "payment_intents", "payment_refunds", "payment_events",
})
NAME = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
SERVICE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


class UnsafeTarget(ValueError):
    """An intentionally public, credential-free refusal message."""


@dataclass(frozen=True)
class Target:
    database: str
    user: str
    database_owner: str
    schema_owner: str
    revisions: tuple[str, ...]
    relations: tuple[tuple[str, str], ...]
    role_exists: bool
    public_create: bool
    public_revision_write: bool


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, help="Named private libpq service, never a URL")
    parser.add_argument("--expected-database", required=True, help="Exact staging database ending in _staging")
    parser.add_argument("--expected-host", required=True, help="Exact managed PostgreSQL hostname")
    parser.add_argument("--migration-owner", required=True, help="Existing database/schema owner role")
    parser.add_argument("--runtime-role", default="canteen_runtime")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--provider", choices=("postgres", "neon"), default="postgres",
                        help="Neon requires a bound plain-text password over verified TLS; ordinary PostgreSQL uses client SCRAM")
    parser.add_argument("--apply", action="store_true", help="Prompt privately and create a new role after checks")
    args = parser.parse_args(argv)
    if not SERVICE.fullmatch(args.service):
        parser.error("Use a named libpq service, not a URL or connection string.")
    for value in (args.expected_database, args.migration_owner, args.runtime_role, args.schema):
        if not NAME.fullmatch(value):
            parser.error("Database, schema and role names must be lowercase SQL identifiers.")
    if not args.expected_database.endswith("_staging"):
        parser.error("This helper accepts explicitly named _staging databases only.")
    if (args.runtime_role == args.migration_owner or args.runtime_role in {"postgres", "public"}
            or args.runtime_role.startswith(("pg_", "neon_"))):
        parser.error("Choose a distinct application role, not a provider/system owner role.")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", args.expected_host):
        parser.error("Expected host must be a hostname, never a URL or credentials.")
    if args.provider == "neon" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*\.neon\.tech", args.expected_host):
        parser.error("Neon password mode accepts only an explicit *.neon.tech hostname.")
    return args


def validate_target(target: Target, args, connection_parameters, tls_in_use):
    if (connection_parameters.get("host", "").lower() != args.expected_host.lower()
            or connection_parameters.get("sslmode") != "verify-full" or not tls_in_use):
        raise UnsafeTarget("Private service must target the expected host with verified TLS (sslmode=verify-full).")
    if (target.database != args.expected_database or target.user != args.migration_owner
            or target.database_owner != args.migration_owner):
        raise UnsafeTarget("Database, authenticated owner or database ownership does not match the selected staging target.")
    if target.schema_owner not in {args.migration_owner, "pg_database_owner"}:
        raise UnsafeTarget("Selected schema is not owned by the stated migration/database owner.")
    if target.revisions != (HEAD,):
        raise UnsafeTarget("Staging schema must already be at the reviewed migration head; this helper never migrates or stamps.")
    tables = {name for name, _ in target.relations}
    if tables != APP_TABLES | {"alembic_version"} or any(owner != args.migration_owner for _, owner in target.relations):
        raise UnsafeTarget("Application tables or ownership differ from the reviewed schema; review the target before granting access.")
    if target.role_exists:
        raise UnsafeTarget("Runtime role already exists. No existing password, permissions or role will be changed.")
    if target.public_create or target.public_revision_write:
        raise UnsafeTarget("PUBLIC has unsafe schema/database CREATE or migration-ledger write privileges; review grants separately.")


def inspect_target(cursor, args):
    cursor.execute("SELECT current_database(), current_user, pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")
    database, user, database_owner = cursor.fetchone()
    cursor.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s", (args.schema,))
    schema = cursor.fetchone()
    if schema is None:
        raise UnsafeTarget("Selected schema does not exist; no role was created.")
    cursor.execute(sql.SQL("SELECT version_num FROM {}.alembic_version ORDER BY version_num").format(sql.Identifier(args.schema)))
    revisions = tuple(row[0] for row in cursor.fetchall())
    cursor.execute("SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('r','p','v','m','f') ORDER BY c.relname", (args.schema,))
    relations = tuple(cursor.fetchall())
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", (args.runtime_role,))
    role_exists = cursor.fetchone()[0]
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a WHERE n.nspname=%s AND a.grantee=0 AND a.privilege_type='CREATE') OR EXISTS(SELECT 1 FROM pg_database d CROSS JOIN LATERAL aclexplode(COALESCE(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='CREATE')", (args.schema,))
    public_create = cursor.fetchone()[0]
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a WHERE n.nspname=%s AND c.relname='alembic_version' AND a.grantee=0 AND a.privilege_type<>'SELECT')", (args.schema,))
    public_revision_write = cursor.fetchone()[0]
    return Target(database, user, database_owner, schema[0], revisions, relations, role_exists, public_create, public_revision_write)


def password_prompt():
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("New runtime role password (hidden, at least 24 bytes): ")
        confirmation = getpass.getpass("Confirm runtime role password (hidden): ")
    if password != confirmation or not 24 <= len(password.encode("utf-8")) <= 1024:
        raise UnsafeTarget("Passwords must match and contain 24–1024 UTF-8 bytes. No role was created.")
    return password


def apply_role(cursor, connection, args, password):
    # Neon explicitly rejects pre-hashed passwords. Its opt-in mode is restricted
    # to an exact Neon hostname and verified TLS by the preceding target guard.
    # Keep the password in the bound parameter only; never print SQL/parameters.
    # Other PostgreSQL providers retain client-side SCRAM encoding.
    verifier = (password if args.provider == "neon" else
                extensions.encrypt_password(password, args.runtime_role, connection, algorithm="scram-sha-256"))
    role = sql.Identifier(args.runtime_role)
    schema = sql.Identifier(args.schema)
    owner = sql.Identifier(args.migration_owner)
    cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %s").format(role), (verifier,))
    cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(args.expected_database), role))
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, role))
    for table in sorted(APP_TABLES):
        cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {}.{} TO {}").format(schema, sql.Identifier(table), role))
    cursor.execute(sql.SQL("GRANT SELECT ON TABLE {}.alembic_version TO {}").format(schema, role))
    cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, role))
    cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(owner, schema, role))
    cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE, SELECT ON SEQUENCES TO {}").format(owner, schema, role))
    cursor.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit FROM pg_roles WHERE rolname=%s", (args.runtime_role,))
    attributes = cursor.fetchone()
    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s) OR has_database_privilege(%s,%s,'CREATE') OR has_schema_privilege(%s,%s,'CREATE') OR has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')", (args.runtime_role, args.runtime_role, args.expected_database, args.runtime_role, args.schema, args.runtime_role, args.schema + ".alembic_version"))
    if attributes is None or any(attributes) or cursor.fetchone()[0]:
        raise UnsafeTarget("Runtime role verification failed; the entire provisioning transaction is rolled back.")


def quiet_cleanup(connection, operation):
    """A lost connection must not expose driver diagnostics during cleanup."""
    if connection is not None:
        try:
            getattr(connection, operation)()
        except Exception:
            pass


def run(args, connector=None, prompt=None):
    connector = connector or psycopg2.connect
    prompt = prompt or password_prompt
    connection = None
    try:
        connection = connector(service=args.service, connect_timeout=10,
                               options="-c search_path=pg_catalog -c statement_timeout=15000 -c lock_timeout=5000")
        with connection.cursor() as cursor:
            if not args.apply:
                cursor.execute("SET TRANSACTION READ ONLY")
            target = inspect_target(cursor, args)
            validate_target(target, args, connection.get_dsn_parameters(), connection.info.ssl_in_use)
            if not args.apply:
                connection.rollback()
                print("Read-only staging preflight passed. Plan: one new runtime role; app DML/sequence access; migration ledger read only. No changes made.")
                return 0
            password = prompt()
            apply_role(cursor, connection, args, password)
        connection.commit()
        print("New staging runtime role created and verified. Store its connection privately in Render DATABASE_URL; never paste credentials in chat.")
        return 0
    except UnsafeTarget as error:
        quiet_cleanup(connection, "rollback")
        print(str(error), file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        quiet_cleanup(connection, "rollback")
        print("Provisioning stopped; inspect target role state privately before retrying. A lost connection during commit can leave the outcome uncertain. Driver errors and credentials are suppressed.", file=sys.stderr)
        return 1
    finally:
        quiet_cleanup(connection, "close")


if __name__ == "__main__":
    raise SystemExit(run(arguments()))
