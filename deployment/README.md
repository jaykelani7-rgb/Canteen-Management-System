# Stable HTTPS deployment preparation

This is an operator-run Docker Compose deployment for one existing FastAPI app,
one PostgreSQL database and Redis, with separate Student PWA and Admin web
origins. Nothing here provisions a server, DNS, a paid resource or a live backend.
Prepared source is not a deployment claim. See `../docs/HOSTING.md` for provider
selection/costs and `../docs/DATABASE_DEPLOYMENT.md` for data preservation,
backups, least-privilege roles and restore approval.

## Free managed staging for 40–50 testers

For the approved $0 testing tier, use a Render Free Docker web service, Neon Free
PostgreSQL and Upstash Free Redis after confirming the current limits in the
hosting guide. This is staging, not the always-on 500-student production plan.
It is the same application/database architecture, not an extra backend service.
Create no paid resource or usage upgrade without separate explicit approval.

`backend.managed-staging.example` lists the exact secret-setting names. The
existing Dockerfile now binds `PORT` (default 8000), runs one worker by default,
and never creates schemas, runs migrations or seeds. Set Render `PORT=10000`
and `WEB_CONCURRENCY=1`, with `DATABASE_POOL_SIZE=2` and
`DATABASE_MAX_OVERFLOW=3`. Choose the Dockerfile `backend/Dockerfile` with the
repository root build context. If deploying the CURRENT image without a Git
push, a registry image upload/account is required; no upload has been performed.
The available Git branch cannot be assumed to contain these uncommitted changes.

Use the provider-issued stable HTTPS service hostname, not a quick tunnel. Keep
`ENVIRONMENT=production` so strict migration/security checks apply. Configure
the managed PostgreSQL asyncpg/TLS URL and private Upstash `rediss://` endpoint
through the secret dashboard. Use `ssl=verify-full` in the asyncpg PostgreSQL
URL query, as documented in the database guide. Do not copy libpq-only
`sslmode`/`channel_binding` parameters; never disable certificate verification.
The Docker runtime sets `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt` to
the public system CA bundle. Local migration operators must set `PGSSLROOTCERT`
to a trusted readable PEM CA bundle; `ssl=verify-full` alone otherwise looks for
`~/.postgresql/root.crt` and fails when that file does not exist. Use a reviewed migration-owner URL only in a local
operator migration environment; it must not be a running-service credential.

Set Render HTTP health-check path `/api/health`. Use `/api/ready` manually before
opening a tester session and for deployment validation; polling database
readiness every few seconds would keep a scale-to-zero PostgreSQL instance awake
and consume free compute allowance. Free cold starts/quotas are expected and must
be measured with actual testers. Redis remains required for fail-closed limits.

For free provider-issued web hostnames on separate sites, build BOTH static web
apps with `VITE_AUTH_COOKIE_MODE=false` and `VITE_API_BASE_URL` set to the ACTUAL
HTTPS API origin; set backend `SESSION_COOKIE_MODE_ENABLED=false`. Publish
`dist/student` and `dist/admin` separately after type/build/separation tests. The
frontends use session-only Bearer tokens; cookie mode is reserved for the paid
same-origin proxy layout below. Set `VITE_STUDENT_APP_URL` to the actual Student
web origin. Native Android remains Bearer mode independently of web settings.

Managed staging `CORS_ORIGINS` must include the actual exact Student/Admin web
origins and `https://localhost` for Android. Keep the role lists disjoint with
their actual web origins (even while cookie mode is disabled), and set
`TRUSTED_HOSTS` to the real API service hostname plus `127.0.0.1` for container
probes. No wildcard origins, localhost backend or `.example` endpoint. Provider
credentials stay in server managed secrets; only the public API URL is built
into frontend/Android assets. Keep payments and SMTP recovery disabled; current
Render Free service limits must be checked before enabling any SMTP transport.

Free services do not provide a release-time migration shell. After a verified
backup/restore and reviewed legacy adoption, run the existing Alembic command
locally against the managed staging database over verified TLS using the
separate private owner environment, then deploy. See the database guide. Do not
auto-run migrations in every application worker or stamp an unverified schema.
Off-host PostgreSQL archives and restore rehearsals are required independently
of the provider's free recovery retention. No current data has been moved here.

## Hosting and environment isolation

- Use an always-on Linux VM, a stable public IP and an owned/college-provided DNS
  domain. A public API hostname, Student hostname and distinct Admin hostname all
  point to that VM. A managed provider URL may also be used after matching its
  routing/build settings; this Compose file specifically describes the VM option.
- Use `configuration.staging.example` and `configuration.example` as separate
  private files, e.g. `/secure/canteen/staging/deployment.env` and
  `/secure/canteen/production/deployment.env`. Each tier requires its own project,
  database/Redis volumes, secrets, credentials and hostnames. Staging runs with
  `ENVIRONMENT=production` too: no demo fallbacks, debug docs, schema auto-creation
  or weakened cookies. `DEPLOYMENT_TIER` distinguishes infrastructure and images.
- This template binds 80/443 and assumes one tier per VM/public IP. Two stacks
  cannot both bind those ports on one IP. Use a separate staging host, or an
  isolated local rehearsal followed by a scheduled sequential deployment.
  Do not share production data with a concurrently running staging API.
- Baseline images are version-tagged (`postgres:16-alpine`, `redis:7-alpine`,
  `python:3.14-slim`, `node:22-slim`, `caddy:2.10-alpine`). Record tested immutable
  base-image digests before real release; never change PostgreSQL major version
  by editing an image tag against the existing data directory.

## Required private configuration

Copy examples outside Git and set file permissions to 600 (directory 700).
Never print `docker compose config` without `--quiet`; expanded configuration
contains environment secrets. Never upload `.env`, credentials or dump files.

Deployment fields:

| Field | Required value |
| --- | --- |
| `DEPLOYMENT_TIER` | `staging` or `production` |
| `COMPOSE_PROJECT_NAME` | exactly `canteen-staging` or `canteen-production` |
| `CANTEEN_IMAGE_TAG` | unique reviewed build/release identifier |
| `STUDENT_HOST`, `ADMIN_HOST`, `API_HOST` | three distinct real public DNS names, without scheme/path |
| `ACME_EMAIL` | operator address for certificate notifications |
| `BACKEND_ENV_FILE`, `MIGRATION_ENV_FILE` | absolute paths to distinct private files outside Git |
| `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` | existing PostgreSQL bootstrap/admin settings; never change a populated volume's password by editing env |
| `POSTGRES_VOLUME_NAME`, `REDIS_VOLUME_NAME` | explicit tier-specific volumes; reuse the approved data identity |

Start with `backend.production.example` for both backend files. Fill:

- Runtime `DATABASE_URL`: `postgresql+asyncpg` URL using the least-privilege app
  role, hostname `postgres` and the existing database. URL-encode password special
  characters privately; do not paste a provider's incompatible `sslmode` query.
- Migration `DATABASE_URL` / optional `MIGRATION_DATABASE_URL`: same database,
  but the reviewed schema-owner role. Keep this credential out of the API file.
  Imports require `SECRET_KEY`/origin settings too; use a separate fresh migration
  job signing value, not a reused weak placeholder.
- `SECRET_KEY`: fresh random signing secret of at least 32 bytes, different per
  tier. Generate privately on the server and never send it through chat.
- `CORS_ORIGINS`: JSON array of `https://` Student origin, Admin origin and
  `https://localhost` (the Capacitor Android document origin). This localhost
  origin is *not* a backend URL and must not be used as the API endpoint.
- `STUDENT_CORS_ORIGINS`: JSON array containing only that tier's Student web
  origin. `ADMIN_CORS_ORIGINS`: JSON array containing only its distinct Admin web
  origin. Cookie-role origins must be disjoint subsets of global CORS. Android
  uses Bearer requests with credentials omitted, not a localhost cookie role.
- `TRUSTED_HOSTS`: JSON array of those three public hostnames plus `127.0.0.1`
  for internal readiness checks. No wildcard or URL scheme.
- `REDIS_URL=redis://redis:6379/0` for the private Compose service. Redis is
  required: authentication rate limits and passcode recovery fail closed when
  Redis is down. It is never published to the host/public internet.
- Keep `AUTO_CREATE_SCHEMA=false`, `ENABLE_DEMO_DATA=false`,
  `SESSION_COOKIE_MODE_ENABLED=true`, `RATE_LIMIT_ENABLED=true`,
  `PAYMENT_PROVIDER=disabled`, `PASSCODE_RECOVERY_ENABLED=false`. Live payments,
  webhook reconciliation and SMTP recovery need real account credentials and
  independent staging verification; there is no fake success transport.

## DNS, HTTPS and firewall

In the domain/college DNS dashboard create three A records for the selected
Student/Admin/API names, all set to the VM public IPv4. Add AAAA only when IPv6
is configured and reachable. Keep the domain under an account the college can
retain; temporary quick tunnels and documentation domains are rejected.

Allow inbound TCP 80 and 443 (optional UDP 443 for HTTP/3), plus SSH only from
operator IPs. Do not expose 5432, 6379 or 8000. Caddy obtains/renews certificates
for the configured DNS names and redirects HTTP to HTTPS. Its `/data` volume
persists certificate state. The API hostname serves `/api/*`, not a remote web
loader. Both web origins proxy `/api/*` to exactly the same backend/database.

## Preserve data, then deploy

Commands below are operator instructions. Run them on the approved target host
after a verified off-host backup/restore rehearsal and explicit resource approval.
No command here seeds users, resets tables or deletes a volume.

1. Upload the reviewed current project source using a secure transfer that omits
   `.env`, `.git`, `node_modules`, `dist`, Android build files, credentials and
   backups. No Git commit/push is necessary. Keep the previous release directory
   and image tags for rollback.
2. Confirm the intended volume exists (`docker volume inspect NAME`), the
   PostgreSQL major version matches 16, and only one server will attach to it.
   For a new approved host, provision an empty target volume explicitly, restore
   the verified current archive there and check counts before migrations. Do not
   run baseline creation over populated restored tables. See database guide.
3. Validate the private configuration without printing secret contents:

```sh
python3 deployment/check_configuration.py --env-file /secure/canteen/staging/deployment.env
docker compose --env-file /secure/canteen/staging/deployment.env -f deployment/compose.production.yml config --quiet
docker compose --env-file /secure/canteen/staging/deployment.env -f deployment/compose.production.yml build
```

4. Stop writes during the scheduled migration/cutover and preserve a fresh
   backup. Start only the selected private data services; do not attach the
   legacy and replacement PostgreSQL containers to one volume simultaneously:

```sh
docker compose --env-file /secure/canteen/staging/deployment.env -f deployment/compose.production.yml up -d postgres redis
docker compose --env-file /secure/canteen/staging/deployment.env -f deployment/compose.production.yml run --rm migrate python adopt_legacy_schema.py
```

For a verified unversioned legacy schema, explicitly approve baseline adoption
and run `migrate python adopt_legacy_schema.py --stamp-baseline` before the upgrade.
For an existing versioned or genuinely empty target, follow its documented
migration path. Never stamp `head` or overwrite drifted schemas.

```sh
docker compose --env-file /secure/canteen/staging/deployment.env -f deployment/compose.production.yml run --rm migrate
docker compose --env-file /secure/canteen/staging/deployment.env -f deployment/compose.production.yml up -d api web
```

Migration runs are explicit one-off jobs under the `operations` profile. Ordinary
`up` cannot automatically migrate or seed. The API checks the Alembic head at
startup and refuses a stale database. Do not deploy a changed app against an
unreviewed schema. New administrator provisioning uses existing `manage_admin.py`
with hidden password entry; existing users and authentication hashes are retained.

5. Check `ps` and only non-secret status logs. Verify from outside the VM:

```sh
curl --fail --silent --show-error https://REAL_API_HOST/api/health
curl --fail --silent --show-error https://REAL_API_HOST/api/ready
curl --fail --silent --show-error -X OPTIONS https://REAL_API_HOST/api/auth/login \
  -H 'Origin: https://localhost' -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,authorization' -D - -o /dev/null
```

Substitute the actual configured `API_HOST` privately; `REAL_API_HOST` is an
instruction marker, never a build value. Expect 200 health/ready, a valid public
TLS chain, exact allowed-origin CORS (no `*`), and rejected unconfigured origins.
Test student login/menu/ordering/tracking, admin role rejection, session expiry
and both web origin cookie flows in staging with approved accounts/data. No live
payment transaction is authorized by these deployment preparations.

## Android handoff and rollback

Only after the actual HTTPS API passes readiness and CORS checks, rebuild the
Student APK with `CAPACITOR_API_BASE_URL` set to the actual HTTPS API origin.
Run `pnpm run build:student:android production`, then `pnpm exec cap sync android`,
then `node scripts/build-android-debug.mjs` with the configured JDK/SDK. Never
run the default staging rebuild after that production asset sync. The URL
has no `/api` suffix. Existing installed placeholder APKs cannot be reconfigured
remotely; reinstall the rebuilt package. See `../docs/ANDROID.md` for exact
commands and installation. Verify its embedded endpoint and test on a phone.

Persist old app images and a pre-migration backup. Rolling back an image is safe
only when its schema compatibility is reviewed; no automatic destructive
downgrade is offered. Database restore requires a maintenance decision and the
database guide. Never use `down -v`, volume prune or a force reset for deployment.
