# Database, secrets and recovery deployment runbook

This is preparation, not evidence of a cloud deployment or scheduled backup. No existing database, credential, row, volume or migration revision was changed for this workstream. Execute the operator steps only after the hosting plan is approved. Never paste connection strings, private keys, payment credentials or dumps into chat.

## Current repository behaviour

- PostgreSQL holds users, orders, wallets, payment/refund receipts, mess subscriptions/attendance and recovery history. PostgreSQL is the source of truth. Redis contains menu caches and distributed authentication/recovery rate-limit counters; it is not a replacement for PostgreSQL.
- Redis is required for production availability: `backend/rate_limit.py` returns HTTP 503 if distributed rate limiting cannot reach Redis; `/api/ready` also requires Redis. Cache helpers alone fail softly. Disabling rate limits to avoid provisioning Redis is not a deployment solution.
- Alembic is already present. The reviewed head is `0005_secure_recovery`, preceded by `0001_legacy_baseline`, `0002_production_hardening`, `0003_payment_records` and `0004_wallet_refunds`. Production startup verifies the head. No new schema migration is required merely to move hosting.
- Automatic `create_all`, demo data and startup admin creation must remain disabled. The migration account and runtime account must be different. A normal API restart must not apply unreviewed migrations.
- Existing downgrade functions refuse to discard audit/financial data. Rollback is an explicit maintenance decision using a proven compatible application version or verified backup; it is not `alembic downgrade base`.

## Staging and production boundaries

Use separate service/project identities, database names, Redis instances or rigorously isolated namespaces, admin accounts, signing keys and provider credentials. Prefer separate Redis instances because this implementation uses shared `canteen:` keys and does not provide an environment prefix. Student Android/PWA and Admin web share the backend/database **within one environment**, never across environments. An isolated restore rehearsal is not another live backend.

Run staging with `ENVIRONMENT=production` to retain production security and migration checks; environment separation comes from isolated resources/configuration. Keep `PAYMENT_PROVIDER=disabled` until the appropriate provider test/live account and server verification are explicitly approved. Existing funded local balances are historical records, not proof of verified external payments. Do not manufacture payments or credits to make deployment tests pass.

The requested $0 staging trial for 40–50 testers can use an account-owned Render Free API, Neon Free PostgreSQL and Upstash Free Redis, subject to the limits confirmed in the hosting comparison. Accept API cold starts and free-service quota interruptions for that trial; it is not the reliability profile for 500 live canteen users. Do not enable upgrades or enter billing configuration that automatically changes a free resource to paid. Do not use Upstash's accountless temporary database, which expires unless claimed. Its current Free account includes one database, 256 MB, 10 GB bandwidth and 500K monthly commands; measure the application's Lua/cache usage before release. Upstash lists `PING` as an uncharged operational command. Neon history/restore allowances must be checked in the selected plan and supplemented by an independently restorable encrypted archive; do not assume the free tier provides the paid backup/PITR promise.

Staging must not contain a casual copy of real student personal information. Restrict a restoration rehearsal to authorized operators, encrypt it and prevent public traffic; use synthetic data for general staging. If preserving current project data into the approved production destination, preserve IDs, credential hashes, monetary values, receipts, attendance and sequence state.

## Hosting and account fields

Managed PostgreSQL is preferable when nobody will maintain database patches, disk capacity, backup monitoring and recovery. Choose an always-available plan with documented backup retention and recovery, then retain an independently restorable encrypted logical backup. A PostgreSQL container on a VPS can be lower cost but has one-host failure exposure; VPS snapshots alone do not establish a database RPO or a tested restore.

For the chosen provider, the operator supplies these fields privately in its dashboard/secret store:

| Resource | Required configuration |
| --- | --- |
| PostgreSQL | Region near API/college; supported version (current local Compose uses 16); explicit staging/production database; migration-owner account; limited runtime account; hostname/port; CA certificate if supplied; enforced TLS on external connections; connection allowance; storage/autogrowth cap; backup/PITR retention; access policy/private network |
| Redis | Same region/private network where possible; always-on Redis-compatible endpoint supporting `PING`, `GET`, `SET`, `SCAN`, `DEL`, `EVAL`, `INCR`, `EXPIRE`; password/ACL; TLS (`rediss://`) for external access; memory budget; persistence policy; alerting |
| API | Privately set database/Redis URLs, fresh signing key, exact CORS/trusted hosts, runtime environment, rate limiting, no demo/schema creation; private migration secrets only on one-off jobs |
| Web and Android | Real HTTPS backend hostname; separate real Student/Admin web origins; public build values only, never database/JWT/payment secrets |
| Backups | Dedicated read-capable backup identity; off-host bucket; encryption recipient; separate decryption identity; retention/object-lock policy; alert destination; approved restore operator |

Use the backend's `postgresql+asyncpg://` driver format with `?ssl=verify-full` for the remote managed endpoint **and an explicit readable CA PEM bundle** through `PGSSLROOTCERT`. The installed asyncpg does not interpret `PGSSLROOTCERT=system` as the operating-system trust store: without a valid PEM path it fails or looks for `~/.postgresql/root.crt`. The reviewed Docker image sets `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt` and verifies that file exists. Local Windows migration operators should point the process-only variable to the installed `certifi.where()` bundle, or the specific provider CA bundle. Do not weaken verification to bypass a missing certificate file.

For example, from `backend` in an authorized local PowerShell migration shell:

```powershell
$env:PGSSLROOTCERT = (& ./.venv/Scripts/python.exe -c "import certifi; print(certifi.where())").Trim()
```

Omit libpq-only `sslmode` and `channel_binding` query parameters from the SQLAlchemy URL; they belong in the separate libpq tooling configuration, not blindly copied into the framework URL. Keep credentials URL-encoded or supplied through managed secret fields. A pooler endpoint must be compatible with asyncpg and the provider's stated pooling mode; use a direct endpoint for migrations and logical dumps. Budget connections per API worker plus migrations/backup/administration; deployment work adds configurable pool sizing and a free staging example can use pool 2 + overflow 3 with one API worker rather than the original 20 + 10 per worker.

For `psql`/`pg_dump`/`pg_restore`, create a private `pg_service.conf` and password file outside the repository, owned by the operator. Named services such as `canteen_source`, `canteen_recovery_empty` and `canteen_production_empty` must specify the actual host, port, database and user explicitly. Use `sslmode=verify-full` and the provider CA path for remote libpq connections. `PGPASSFILE` contains passwords and is mode 0600 on Linux; no passwords belong in command-line arguments or the service name. The SQLAlchemy URL and libpq service configuration have different syntax.

## Preserve the existing database when relocating it

1. Record the actual source server/database, PostgreSQL/client versions, current Alembic revision, table counts, sequence values, wallet/order totals and attendance balances privately. Identify the original volume before any container change. Keep its identity and original files unchanged. Do not run two PostgreSQL servers against the same volume.
2. Check PostgreSQL/client compatibility: use a `pg_dump` client that supports the source version and a restore target supported by that archive/client. Prefer the same server major version for the first move; rehearse any major-version upgrade separately.
3. Back up while the source remains available; PostgreSQL custom-format dumps are consistent snapshots. For the final cutover, pause writes/API traffic, complete in-flight transactions, and make a final dump so later orders, attendance or wallet changes are not omitted. A live rehearsal dump is not the final cutover archive.
4. Restore only into an **explicitly provisioned empty destination**, never a populated destination. Verify emptiness and the destination identity before proceeding. Do not use `--clean`, `--create`, table drops, database resets or volume deletion.
5. Use `pg_restore --no-owner --no-privileges --exit-on-error --single-transaction` under the intended migration-owner role. This avoids copying local privileged roles into managed hosting. Review any provider-added extensions/schema policy before restore; an untrusted archive can execute SQL and must not be restored with unnecessary superuser rights.
6. Compare source/destination counts, monetary totals, token/attendance ledger checks, foreign keys, unique indexes and sequence state. Read-only `deployment/database/verification.sql` checks the current fully migrated schema; run it only after verifying that schema version. Zero mismatch counts are necessary but do not substitute for reviewing the migration head and restore logs.
7. Apply missing reviewed Alembic revisions to the isolated copy, then verify again. Do not stamp `head` to suppress drift. Resume traffic only after readiness, roles, restore provenance and staging workflows pass. Keep the stopped original source and final encrypted archive for the agreed rollback period. Never allow both old and new APIs to accept writes during cutover.

## Existing legacy schema versus migrated or empty destination

From `backend`, with private `DATABASE_URL`/`MIGRATION_DATABASE_URL` and the other required production settings supplied by the operator:

```sh
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini heads
```

- A restored database already containing a valid `alembic_version` uses normal reviewed `upgrade head` only if its revision is behind. At head, no migration is needed.
- A verified existing legacy database **without** revision metadata must first pass the read-only `python adopt_legacy_schema.py`. Only after its backup and structure/financial preflight pass may the operator explicitly use `python adopt_legacy_schema.py --stamp-baseline`, then `python -m alembic -c alembic.ini upgrade head`.
- A genuinely empty database can use Alembic upgrades to create the approved schema. This does not preserve existing data: if the objective is relocating current records, restore the full archive instead. Do not run upgrades creating duplicate tables before restoring an archive.
- Drift, fractional-cent money, duplicate success ledgers or orphan references must be reviewed and reconciled without deleting history. The preflight intentionally refuses these cases.

Schedule migrations during a maintenance window; PostgreSQL ALTER operations require locks. Run one migration job only. The migration identity owns schema objects; the API identity has only needed `SELECT`, `INSERT`, `UPDATE`, `DELETE` and sequence usage, plus read access to `alembic_version`, with no schema ownership/DDL privilege. Configure owner default privileges for future migrations, and review broad grants against actual endpoint needs. Use `manage_admin.py --username ACTUAL_USERNAME` for explicit provisioning only if a new authorized administrator is needed; it prompts privately and does not replace existing users unless `--reset` is deliberately selected.

## Encrypted backups and restore verification

`deployment/database/backup.sh` is an operator-invoked Linux helper. It requires the PostgreSQL client, `age`, `sha256sum`, an existing private output directory, a named private libpq source service and a **public** age recipient. It streams the dump directly into encryption; no plaintext dump or password is written by this script. A failed command may leave a partial archive; it must not be treated as a successful backup. The script never overwrites an existing archive and does not provision, schedule, delete or restore anything.

```sh
bash deployment/database/backup.sh canteen_source /secure/backups "$BACKUP_AGE_RECIPIENT"
```

Copy the archive and checksum file off the database host after success. Protect the bucket against accidental deletion; limit the upload identity to the backup prefix and keep the decryption identity separate from the API host. Backups contain student personal data and credential hashes even when no JWT keys are present.

On the authorized recovery workstation, set the following **nonsecret** environment variables to actual paths/names. `RESTORE_SERVICE` must be a reviewed private service pointing to the specifically selected empty recovery destination; `EXPECTED_RECOVERY_DB` must exactly match that destination. `AGE_IDENTITY_FILE` names a private existing file, not the identity contents. The operator must not substitute the live production service:

```sh
set -euo pipefail
umask 077
: "${ARCHIVE:?Set the verified absolute encrypted archive path}"
: "${AGE_IDENTITY_FILE:?Set the private age identity file path}"
: "${RESTORE_SERVICE:?Select an isolated empty recovery service explicitly}"
: "${EXPECTED_RECOVERY_DB:?Name the expected recovery database explicitly}"
(cd -- "$(dirname -- "$ARCHIVE")" && sha256sum --check "$(basename -- "$ARCHIVE").sha256")
actual_db=$(psql --no-password -XAt --dbname="service=$RESTORE_SERVICE" -c 'SELECT current_database()')
[ "$actual_db" = "$EXPECTED_RECOVERY_DB" ]
table_count=$(psql --no-password -XAt --dbname="service=$RESTORE_SERVICE" -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
[ "$table_count" = 0 ]
age --decrypt --identity "$AGE_IDENTITY_FILE" "$ARCHIVE" | pg_restore --list > /secure/recovery/archive-list.txt
age --decrypt --identity "$AGE_IDENTITY_FILE" "$ARCHIVE" | pg_restore --no-password --no-owner --no-privileges --exit-on-error --single-transaction --dbname="service=$RESTORE_SERVICE"
psql --no-password -X --dbname="service=$RESTORE_SERVICE" -f deployment/database/verification.sql > /secure/recovery/restored-verification.txt
```

Provision the recovery destination and `/secure/recovery` privately beforehand; the instructions do not create a database or remove any data. The table-count check conservatively refuses managed databases with existing provider tables; review that case rather than weakening it against an unknown destination. Inspect archive provenance/list and SQL before executing a restore. Missing keys, checksum mismatch, identity mismatch, a nonempty database or restore error must stop recovery. Compare the private verification output with the frozen source and check sequence last values against inserted IDs before directing any writes to the restored database. Never restore Redis caches with old sensitive values as a substitute for PostgreSQL restore.

Proposed minimum operating objectives, requiring college approval: encrypted daily logical backup, off-host copy, 7 daily / 4 weekly / 3 monthly retention, and a monthly isolated restore rehearsal. Daily-only dumps imply up to 24 hours of data loss (RPO), unsuitable if losing a lunch service's financial/attendance records is unacceptable. Prefer managed continuous backup/PITR with an explicitly documented retention/RPO; otherwise engineer and verify WAL archiving before live financial operation. Target an initial recovery within four hours (RTO), but do not claim this target until a timed full restore, DNS/API recovery and client smoke test pass. Alert on backup age/failure, storage limits, readiness failures and restore rehearsal failures. A local backup, a successful dump exit code or an untested provider snapshot does not establish recovery readiness.

Redis stays private and authenticated/ACL-restricted; use TLS for remote hosted Redis. Existing AOF settings improve restart recovery but PostgreSQL remains authoritative. A lost Redis cache/rate window does not lose orders; it can temporarily disrupt availability/rate controls. Restore/restart it separately with the same environment separation, memory limits and alerting. Do not run Redis flush commands on the shared service as a deployment shortcut.

## CORS, native origin, sessions and secrets

- `CORS_ORIGINS` must list actual Student/Admin web HTTPS origins and **`https://localhost`** for the packaged Android WebView. That Android origin is locally bundled content, not the backend address. `TRUSTED_HOSTS` describes incoming API hosts, not client origins: list the real API/front-door hostnames and any strictly required internal health host.
- Native Android uses Bearer JWT requests with omitted browser cookies. Do not add `https://localhost` to Student/Admin **cookie-role** origins, enable native cookie mode or broaden CORS to `*` to bypass failures. Web cookie role origin sets remain disjoint subsets of global CORS.
- Same-origin `/api` proxying per web frontend avoids cross-site cookie restrictions. For separate static hosting, check actual domain/site relationships: current cookies use `SameSite=Lax`, so unrelated web/backend provider domains can break credentialed cookie requests even when CORS is correct. Use approved same-site custom domains/proxies or explicit Bearer web configuration, not arbitrary weakening of cookie protections.
- Expose HTTPS only. Keep database/Redis/API ports private behind the approved proxy. Trust forwarded IP headers only from that proxy; broad `*` forwarding trust is acceptable only with enforced private/unpublished backend access and an audited network boundary. Rate-limit client-IP accuracy must be tested through the actual deployed proxy.
- Generate different high-entropy signing secrets for staging/production inside the provider secret store. Rotating a signing secret invalidates existing sessions; it does not change preserved password hashes. Never put JWT/database/SMTP/provider secrets in `VITE_*`, APK resources, images, source maps, Git or logs. Public API URL and Razorpay checkout key are different from provider signing secrets.
- Keep payments and recovery disabled until real provider/sender ownership and server-side verification have been tested. Never re-enable a writable student order-status simulation endpoint for deployment debugging.

## Release evidence required

Before claiming production: external HTTPS `/api/health` and `/api/ready` succeed; deployed revision/configuration is identified; database/Redis ports are inaccessible publicly; migration head and runtime grants are verified; backup restoration and alerting work; actual web and native origins pass CORS/preflight; student/admin role separation and expired JWT rejection pass; student login/menu/order/tracking use the same backend; no fake success/live provider switch occurs. A phone rendering the bundled UI proves installation, not backend connectivity.

Official references: [PostgreSQL 16 pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html), [libpq TLS verification](https://www.postgresql.org/docs/16/libpq-ssl.html), [Redis persistence](https://redis.io/docs/latest/management/persistence/).

Free Redis limits and operational-command accounting: [official Upstash pricing](https://upstash.com/pricing/redis). Confirm quotas and the actual plan in the provider dashboard before enabling tester access.
