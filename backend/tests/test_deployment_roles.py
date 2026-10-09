"""Isolated tests only: no provider or database connection is used."""
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest


path = Path(__file__).resolve().parents[2] / "deployment" / "database" / "provision_runtime_role.py"
spec = importlib.util.spec_from_file_location("deployment_runtime_role_helper", path)
roles = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = roles
spec.loader.exec_module(roles)


def arguments(apply=False):
    values = ["--service", "canteen_staging_owner", "--expected-database", "canteen_staging",
              "--expected-host", "database.neon.tech", "--migration-owner", "migration_owner"]
    return roles.arguments(values + (["--apply"] if apply else []))


def target(**overrides):
    state = roles.Target("canteen_staging", "migration_owner", "migration_owner", "pg_database_owner",
                         (roles.HEAD,), tuple((name, "migration_owner") for name in sorted(roles.APP_TABLES | {"alembic_version"})),
                         False, False, False)
    return replace(state, **overrides)


def test_postgresql16_database_owner_schema_is_allowed():
    roles.validate_target(target(), arguments(), {"host": "database.neon.tech", "sslmode": "verify-full"}, True)


@pytest.mark.parametrize("changes", [
    {"database": "canteen_production"}, {"user": "another_owner"}, {"database_owner": "another_owner"},
    {"schema_owner": "another_owner"}, {"revisions": ("0004_wallet_refunds",)}, {"revisions": ()},
    {"role_exists": True}, {"public_create": True}, {"public_revision_write": True},
    {"relations": (("alembic_version", "migration_owner"),)},
])
def test_unsafe_targets_are_refused(changes):
    with pytest.raises(roles.UnsafeTarget):
        roles.validate_target(target(**changes), arguments(), {"host": "database.neon.tech", "sslmode": "verify-full"}, True)


@pytest.mark.parametrize("parameters,tls", [
    ({"host": "another.neon.tech", "sslmode": "verify-full"}, True),
    ({"host": "database.neon.tech", "sslmode": "require"}, True),
    ({"host": "database.neon.tech", "sslmode": "verify-full"}, False),
])
def test_wrong_host_or_unverified_tls_is_refused(parameters, tls):
    with pytest.raises(roles.UnsafeTarget):
        roles.validate_target(target(), arguments(), parameters, tls)


@pytest.mark.parametrize("flag,value", [
    ("--service", "postgresql://private:private@database/canteen"),
    ("--expected-database", "canteen_production"), ("--runtime-role", "neon_superuser"),
    ("--runtime-role", "migration_owner"), ("--schema", "public; DROP TABLE students"),
    ("--expected-host", "https://database.neon.tech"),
])
def test_unsafe_operator_arguments_are_rejected(flag, value):
    values = ["--service", "staging_owner", "--expected-database", "canteen_staging",
              "--expected-host", "database.neon.tech", "--migration-owner", "migration_owner"]
    values.extend([flag, value])
    with pytest.raises(SystemExit):
        roles.arguments(values)


class Cursor:
    def __init__(self):
        self.executions = []
        self.results = [(False,) * 6, (False,)]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, statement, params=None):
        self.executions.append((str(statement), params))
    def fetchone(self):
        return self.results.pop(0)


class Connection:
    def __init__(self):
        self.recorder = Cursor()
        self.commits = self.rollbacks = self.closes = 0
        self.info = SimpleNamespace(ssl_in_use=True)
    def cursor(self):
        return self.recorder
    def get_dsn_parameters(self):
        return {"host": "database.neon.tech", "sslmode": "verify-full"}
    def commit(self):
        self.commits += 1
    def rollback(self):
        self.rollbacks += 1
    def close(self):
        self.closes += 1


def test_read_only_preflight_does_not_prompt_or_write(monkeypatch, capsys):
    connection = Connection()
    monkeypatch.setattr(roles, "inspect_target", lambda *args: target())
    def forbidden_prompt():
        raise AssertionError("Read-only execution must not ask for a password")
    assert roles.run(arguments(), lambda **kwargs: connection, forbidden_prompt) == 0
    assert connection.recorder.executions == [("SET TRANSACTION READ ONLY", None)]
    assert connection.commits == 0 and connection.rollbacks == 1 and connection.closes == 1
    assert "No changes made" in capsys.readouterr().out


def test_new_role_uses_scram_and_only_reads_migration_ledger(monkeypatch, capsys):
    connection = Connection()
    monkeypatch.setattr(roles, "inspect_target", lambda *args: target())
    calls = []
    def encrypt(password, role, conn, algorithm):
        calls.append((password, role, conn, algorithm))
        return "SCRAM-SHA-256$synthetic-verifier"
    monkeypatch.setattr(roles.extensions, "encrypt_password", encrypt)
    password = "synthetic-private-password-for-tests"
    assert roles.run(arguments(True), lambda **kwargs: connection, lambda: password) == 0
    assert calls == [(password, "canteen_runtime", connection, "scram-sha-256")]
    sql_text = "\n".join(statement for statement, _ in connection.recorder.executions)
    assert "NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS" in sql_text
    ledger_grants = [statement for statement, _ in connection.recorder.executions if "GRANT" in statement and "alembic_version" in statement]
    assert len(ledger_grants) == 1 and "GRANT SELECT ON TABLE" in ledger_grants[0]
    assert "ALTER DEFAULT PRIVILEGES" in sql_text
    assert password not in repr(connection.recorder.executions)
    assert connection.commits == 1 and connection.rollbacks == 0 and connection.closes == 1
    assert password not in capsys.readouterr().out


def test_existing_role_stops_before_any_password_prompt(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(roles, "inspect_target", lambda *args: target(role_exists=True))
    assert roles.run(arguments(True), lambda **kwargs: connection, lambda: pytest.fail("Must not prompt")) == 1
    assert not connection.recorder.executions and connection.commits == 0 and connection.rollbacks == 1


def test_failed_role_verification_rolls_back(monkeypatch):
    connection = Connection()
    connection.recorder.results = [(False,) * 6, (True,)]
    monkeypatch.setattr(roles, "inspect_target", lambda *args: target())
    monkeypatch.setattr(roles.extensions, "encrypt_password", lambda *args, **kwargs: "SCRAM-SHA-256$synthetic")
    assert roles.run(arguments(True), lambda **kwargs: connection, lambda: "synthetic-password") == 1
    assert connection.commits == 0 and connection.rollbacks == 1 and connection.closes == 1


def test_driver_errors_are_suppressed(monkeypatch, capsys):
    def failed_connector(**kwargs):
        raise RuntimeError("private fixture driver password should never be displayed")
    assert roles.run(arguments(True), failed_connector) == 1
    assert "private fixture" not in capsys.readouterr().err


def test_connection_cleanup_errors_do_not_leak_driver_details(monkeypatch, capsys):
    connection = Connection()
    monkeypatch.setattr(roles, "inspect_target", lambda *args: target(role_exists=True))
    def unsafe_cleanup():
        raise RuntimeError("private driver connection data")
    connection.rollback = connection.close = unsafe_cleanup
    assert roles.run(arguments(True), lambda **kwargs: connection) == 1
    assert "private driver" not in capsys.readouterr().err
