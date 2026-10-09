# Non-destructive PostgreSQL migrations

Back up and verify restoration of the existing database before applying migrations. These scripts never reset tables, delete users, or delete ledger/audit records. They refuse legacy conflicts rather than silently repairing data.

From `backend`, first run `python adopt_legacy_schema.py` for read-only legacy structure and monetary/FK/ledger validation. For a verified existing legacy schema, run `python adopt_legacy_schema.py --stamp-baseline`, then `python -m alembic -c alembic.ini upgrade head`. For a genuinely empty database, run only the Alembic upgrade. Do not stamp an empty or drifted database.

The first revision is a frozen legacy schema independent of runtime models. Later revisions add columns, receipts, constraints and convert finite, nonnegative, cent-valued money to Numeric(12,2). PostgreSQL performs these changes transactionally; schedule a maintenance window because ALTER TABLE requires locks. No downgrade drops data: recovery uses a verified backup and an explicit plan.

`MIGRATION_DATABASE_URL` overrides the existing configured database for verification; `MIGRATION_SCHEMA` targets an explicitly provisioned disposable schema in that same database. Neither option creates a new database. Production startup verifies the head revision and does not run migrations or demo seeds automatically.
