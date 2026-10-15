"""Exercise the additive migration locally; no deployed database is contacted."""
import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def migration():
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0007_lunch_bundles.py'
    spec = importlib.util.spec_from_file_location('lunch_migration_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lunch_additive_migration_preserves_existing_rows_and_defaults_disabled():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as db:
        db.execute(sa.text('CREATE TABLE weekly_menu (id INTEGER PRIMARY KEY, day TEXT, meal_type TEXT, items JSON)'))
        db.execute(sa.text('CREATE TABLE old_order_snapshot (id INTEGER PRIMARY KEY, total INTEGER, contents TEXT)'))
        db.execute(sa.text("INSERT INTO weekly_menu VALUES (1,'Thursday','lunch','[\"Old meal\"]')"))
        db.execute(sa.text("INSERT INTO old_order_snapshot VALUES (1,80,'Original thali')"))
        with Operations.context(MigrationContext.configure(db)):
            migration().upgrade()
        assert db.execute(sa.text('SELECT day,meal_type,items,sabji_options,ordering_enabled FROM weekly_menu')).one() == ('Thursday','lunch','["Old meal"]','[]',0)
        assert db.execute(sa.text('SELECT * FROM old_order_snapshot')).one() == (1,80,'Original thali')
    engine.dispose()


def test_postgres_lunch_migration_generates_only_two_additive_columns():
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
    with Operations.context(context):
        migration().upgrade()
    sql = output.getvalue()
    assert sql.count('ALTER TABLE weekly_menu ADD COLUMN') == 2
    assert 'sabji_options JSON DEFAULT' in sql and 'ordering_enabled BOOLEAN DEFAULT false NOT NULL' in sql
    assert not any(word in sql.upper() for word in ('DROP ', 'DELETE ', 'TRUNCATE ', 'INSERT ', 'UPDATE '))
