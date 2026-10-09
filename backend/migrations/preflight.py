"""Read-only checks before legacy adoption and financial schema conversion."""
import re
from sqlalchemy import inspect, text, UniqueConstraint, Numeric, Float
from migrations.legacy_schema import Base as LegacyBase

MONEY = {
    "ala_carte": ("price",), "food_items": ("price",),
    "students": ("wallet_balance", "total_spent"),
    "orders": ("item_total", "packaging_fee", "gst_amount", "total_amount"),
    "wallet_transactions": ("amount",),
}

def canonical_check(expression):
    value=re.sub(r"::(?:character varying|double precision|numeric|integer|text)(?:\[\])?", "", str(expression).lower())
    value=re.sub(r"[\s()\[\]\"]", "", value)
    return value.replace("=anyarray", "in")

def validate_legacy_schema(connection):
    """Refuse to stamp an empty, incomplete, or structurally drifted schema."""
    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(LegacyBase.metadata.tables)
    if "alembic_version" in actual_tables:
        raise RuntimeError("Schema already has an Alembic revision; use normal upgrades")
    missing = expected_tables - actual_tables
    if missing:
        raise RuntimeError("Legacy adoption refused: missing tables: " + ", ".join(sorted(missing)))
    for table in LegacyBase.metadata.sorted_tables:
        actual_columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        if set(actual_columns) != set(table.columns.keys()):
            raise RuntimeError("Legacy adoption refused: column drift in " + table.name)
        for col in table.columns:
            actual = actual_columns[col.name]
            if actual["type"]._type_affinity != col.type._type_affinity or actual["nullable"] != col.nullable:
                raise RuntimeError("Legacy adoption refused: type/nullability drift in " + table.name + "." + col.name)
            if hasattr(col.type,"timezone") and getattr(actual["type"],"timezone",None) != col.type.timezone:
                raise RuntimeError("Legacy adoption refused: timestamp timezone drift in " + table.name + "." + col.name)
            if isinstance(col.type, Numeric) and not isinstance(col.type, Float) and (getattr(actual["type"],"scale",None),getattr(actual["type"],"precision",None)) != (col.type.scale,col.type.precision):
                raise RuntimeError("Legacy adoption refused: numeric precision drift in " + table.name + "." + col.name)
            expected_length = getattr(col.type, "length", None)
            if expected_length and getattr(actual["type"], "length", None) != expected_length:
                raise RuntimeError("Legacy adoption refused: column length drift in " + table.name + "." + col.name)
        if tuple(inspector.get_pk_constraint(table.name)["constrained_columns"]) != tuple(c.name for c in table.primary_key.columns):
            raise RuntimeError("Legacy adoption refused: primary-key drift in " + table.name)
        actual_fks = {(tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"])) for f in inspector.get_foreign_keys(table.name)}
        for fk in table.foreign_key_constraints:
            wanted = (tuple(c.name for c in fk.columns), fk.elements[0].column.table.name, tuple(e.column.name for e in fk.elements))
            if wanted not in actual_fks:
                raise RuntimeError("Legacy adoption refused: foreign-key drift in " + table.name)
        actual_indices = {i["name"]: i for i in inspector.get_indexes(table.name)}
        for idx in table.indexes:
            actual = actual_indices.get(idx.name)
            if not actual or tuple(actual["column_names"]) != tuple(c.name for c in idx.columns) or bool(actual["unique"]) != bool(idx.unique):
                raise RuntimeError("Legacy adoption refused: index drift in " + table.name)
            expected_where = idx.dialect_options["postgresql"].get("where")
            if expected_where is not None:
                actual_where = actual.get("dialect_options", {}).get("postgresql_where", "")
                if canonical_check(actual_where) != canonical_check(expected_where):
                    raise RuntimeError("Legacy adoption refused: partial-index predicate drift in " + table.name)
        actual_unique = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table.name)}
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint) and tuple(c.name for c in constraint.columns) not in actual_unique:
                raise RuntimeError("Legacy adoption refused: unique-constraint drift in " + table.name)
        actual_checks = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints(table.name)}
        for constraint in table.constraints:
            if constraint.__class__.__name__ == "CheckConstraint":
                if constraint.name not in actual_checks or canonical_check(actual_checks[constraint.name]) != canonical_check(constraint.sqltext):
                    raise RuntimeError("Legacy adoption refused: check-constraint drift in " + table.name)
    validate_financial_data(connection)
    return sorted(expected_tables)

def validate_financial_data(connection):
    for table, columns in MONEY.items():
        for col in columns:
            bad = connection.execute(text(f"SELECT count(*) FROM {table} WHERE {col} IS NULL OR {col}::text IN ('NaN','Infinity','-Infinity') OR {col} < 0 OR {col} >= 10000000000 OR abs({col}::numeric - round({col}::numeric,2)) > 0.00000001")).scalar_one()
            if bad:
                raise RuntimeError(f"Migration refused: {bad} invalid or fractional-cent monetary values in {table}.{col}; review data without deleting it")
    for table in ("wallet_transactions", "notifications"):
        orphan = connection.execute(text(f"SELECT count(*) FROM {table} t LEFT JOIN orders o ON o.id=t.order_id WHERE t.order_id IS NOT NULL AND o.id IS NULL")).scalar_one()
        if orphan:
            raise RuntimeError(f"Migration refused: {orphan} orphan order references in {table}; preserve and reconcile records first")
    duplicates = connection.execute(text("SELECT count(*) FROM (SELECT student_id,order_id,transaction_type FROM wallet_transactions WHERE order_id IS NOT NULL AND status='success' GROUP BY student_id,order_id,transaction_type HAVING count(*)>1) d")).scalar_one()
    if duplicates:
        raise RuntimeError(f"Migration refused: {duplicates} duplicate successful order-ledger groups; reconcile without deleting history")
