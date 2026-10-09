# ₹0 staging: setup and deployment checklist

Updated 10 October 2026. **The Free staging backend is deployed and verified:**
https://canteen-staging-api.onrender.com. `/api/health` returns HTTP 200 with
`{"status":"alive"}`; `/api/ready` returns HTTP 200 with PostgreSQL and Redis ready.

The Student debug APK has now been rebuilt with that actual HTTPS API origin.
Its bundled assets, application ID, matching update signature and all 13 Android
checks passed. Output: `android/app/build/outputs/apk/debug/app-debug.apk`.
The owner must install this new APK; physical-phone verification remains pending.

Both existing Cloudflare **Direct Upload** projects are deployed and verified:

- Student: https://canteenos-student-krishna.pages.dev
- Admin: https://canteenos-admin-krishna.pages.dev
- Shared API: https://canteen-staging-api.onrender.com

GitHub App authorization is not required for Pages. No Pages projects were deleted
or recreated. Both separately built ZIPs were uploaded to their matching existing
projects. Public assets match the reviewed build outputs; exact web/native CORS
passed after a fresh Render deploy. Save-only environment changes require a new
deploy; restarting the previous deployment does not activate those saved values.

Live browser acceptance passed: Student and Admin login, shared menu, Student
cart/wallet order creation, Admin Live Orders and Preparing → Ready → Completed
updates reflected in Student tracking. Only synthetic staging credit was used;
external gateway payments remain disabled. Read-only database verification confirmed
each order has one debit and the wallet matches the transaction ledger.

Account/resource order: **Neon → Upstash → Render → Cloudflare Pages**.
Use Free plans for the 40–50-person pilot. Free sleep/quotas are testing limitations;
this is not an always-on production promise for the later 500-student rollout.
Do not upgrade, enable automatic paid overages, buy a domain or add paid resources
without explicit approval. Use the providers' included HTTPS domains.

## What Codex has completed locally

- Reviewed `backend/Dockerfile`: repository-root build context; image command
  `python start_server.py`; listens on `0.0.0.0` using `PORT`.
- Prepared [render.yaml](../render.yaml) for one Free Docker web service from
  GitHub branch `krishna`, with automatic deploys/previews disabled. **A separate
  container registry is not required:** Render builds the Dockerfile directly.
  See [Render Docker deployment](https://render.com/docs/docker).
- Prepared [managed environment template](../deployment/backend.managed-staging.example),
  [offline configuration preflight](../deployment/check_managed_configuration.py),
  [database/backup runbook](DATABASE_DEPLOYMENT.md) and a guarded runtime-role helper.
- Prepared the guarded Pages builder: it requires the real API/Student/Admin
  HTTPS origins, verifies API health/readiness, builds both existing web apps and
  emits public CORS metadata outside their upload directories.

Current verified execution results:

- Neon staging was originally empty and safely migrated to `0005_secure_recovery`.
  The owner authorized using this isolated target instead of transferring local
  test data. The original local database remains unchanged.
- A new restricted runtime role was created with verified TLS, no DDL/elevated
  membership and read-only migration metadata. Upstash verified TLS PING passed.
- Render is Free, using reviewed `krishna` source and managed environment secrets.
  Its startup, public health and PostgreSQL/Redis readiness checks passed.
- Actual public API acceptance passed: admin/student login, shared menu, wallet
  order creation/idempotency, admin order visibility/status transitions, tracking
  and the persisted single-debit ledger. Only unique synthetic staging fixtures
  and an explicitly labelled synthetic test credit were created; no external money
  was processed. Gateway payments and automatic demo seeding remain disabled.
- Exact Student, Admin and native-origin CORS checks passed; unrelated origins
  are rejected. Both deployed websites passed browser acceptance, and independent
  QA verified all 16 published files against the reviewed ZIP contents.

No credentials, local configuration, database dumps or generated APKs were
published. All commits were pushed only to `krishna`; `main` remains unchanged.

Neon Free `canteen-staging` (PostgreSQL 16/Singapore, database
`canteen_staging`) and Upstash Free `canteen-staging` (Singapore/TLS) were
created with explicit owner approval. Their actual connections and backend
health/readiness have now passed; existing local data was not transferred.

The existing `canteenos-student-krishna` and `canteenos-admin-krishna` projects
remain **Direct Upload**, with no Git connection. Reuse them for subsequent
reviewed deployments; do not create replacement Git projects for this staging run.

The owner has explicitly approved publication of reviewed deployment changes
only to `krishna`, and private staging credentials only in local migration tools
and Render managed secrets. Never publish credentials or modify `main`.
Render must use the reviewed current source, not an older checkout missing the
Dockerfile, migrations or transitive application modules. Verify the actual
published revision during deployment.

## 1. Neon — owner dashboard actions

Open [Neon Console](https://console.neon.tech), remain on **Free**, enable MFA and
create/select an isolated staging project after approving its free creation.

| Field | Select |
| --- | --- |
| Project | `canteen-staging` or an available staging name |
| PostgreSQL | **16**, matching the existing local database |
| Region | Singapore if available on Free; otherwise review latency before choosing |
| Application database | `canteen_staging` |
| Environment | Staging only; separate from future production resources |

The existing auto-created project `falling-dream-56289503` is Free, PostgreSQL 18,
Virginia, with a provider-named `production` branch. **Do not delete, reset, alter
or silently repurpose it.** A provider branch label is not evidence that the
Canteen application has been deployed there. If the Free quota prevents a separate
PostgreSQL 16 target, stop and review instead of upgrading or replacing data.

Keep credentials in a password manager/private provider settings, never chat.
Retain the **direct** endpoint for migrations and backups. Use a distinct limited
runtime role for Render; do not give the running API the database-owner credential.
Supply the direct owner connection as `MIGRATION_DATABASE_URL` only in the private
operator process environment; it overrides the migration connection without
putting that credential in the running service's `DATABASE_URL`.
The runtime SQLAlchemy URL uses `postgresql+asyncpg` and `?ssl=verify-full`;
remove Neon/libpq-only `sslmode` and `channel_binding` parameters when preparing
that private value. A compatible pooled endpoint may be used for API traffic.

**Preserve data before migration:** follow [DATABASE_DEPLOYMENT.md](DATABASE_DEPLOYMENT.md).
The original local database was audited read-only: PostgreSQL **16.15**, database
`canteen_db`, already at **`0005_secure_recovery`**, with existing application data.
Its original container and `backend_postgres_data` volume remain preserved.
An approved full copy at this head needs restoration/verification, not a legacy
stamp or unnecessary upgrade. These observations do not prove a cloud copy exists.
Record the source identity, take an encrypted backup and rehearse restoration only
into an explicitly verified **empty** staging destination. For general testers,
use authorized sanitized data. Preserve the original records, IDs, password hashes,
wallet/order totals, attendance and sequence state. Do not seed/reset the source,
restore over populated tables, use `--clean`, drop tables or stamp `head` to hide drift.

From `backend`, using the operator's private migration environment/direct TLS
connection and a readable CA bundle:

```powershell
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini heads
```

The reviewed head is **`0005_secure_recovery`**. When an upgrade is appropriate,
the exact command from `backend` is `python -m alembic -c alembic.ini upgrade head`.
Restore the full approved archive
before running upgrades when relocating existing records. A restored database at
head needs no upgrade; a behind revision uses reviewed `upgrade head`. A legacy
database without revision metadata first needs `adopt_legacy_schema.py` read-only
preflight and explicit baseline adoption, as documented in the runbook. A genuinely
empty fresh schema may use migrations directly only when preserving imported
records is not the objective. Run one migration job, never a startup hook.

After the selected staging target is safely at head, use
[provision_runtime_role.py](../deployment/database/provision_runtime_role.py) with
a private named libpq service (`sslmode=verify-full`, CA/password files outside the
repository). Supply its actual `--service`, `--expected-database`, `--expected-host`,
`--migration-owner` and distinct `--runtime-role`; defaults are read-only.
For Neon, also supply `--provider neon`: Neon requires a bound password over
verified TLS and rejects pre-hashed PostgreSQL role passwords. This mode accepts
only an explicit Neon hostname and never prints SQL parameters or credentials.
Only an approved invocation with `--apply` creates a **new** role after hidden
password prompts and ownership/schema checks. It refuses existing roles, changes
no application rows and grants only application DML/sequences plus read access to
`alembic_version`. Never pass a connection string/password as a CLI argument.

## 2. Upstash — owner dashboard actions

Open [Upstash Console](https://console.upstash.com) → Redis → create/select an
account-owned **Free** database after approving its free creation.

- Name: `canteen-staging`; choose the nearest available Free region to the API.
- Keep Free billing and TLS enabled; review the displayed free quota before saving.
- Obtain the **Redis TCP/TLS** endpoint privately. The backend uses a `rediss://`
  connection with verified certificates/hostnames, **not** the REST URL/token.
- Do not flush/delete existing Redis databases, use an expiring accountless
  instance or reuse production caches/rate-limit counters for staging.

Redis is required for distributed authentication rate limits and `/api/ready`;
do not disable rate limiting to avoid this resource. See
[Upstash Free pricing/quotas](https://upstash.com/pricing/redis).

## 3. Render — owner dashboard actions

Reuse the existing Free `canteen-staging-api` service. It already builds the public
repository and branch `krishna` without needing another GitHub App installation.
The settings below describe that existing service; do not create a duplicate.

| Field | Exact setting |
| --- | --- |
| Repository | `jaykelani7-rgb/Canteen-Management-System` |
| Branch | **`krishna`**, containing the complete reviewed current source |
| Name | `canteen-staging-api` or an available unique staging name |
| Region | Singapore, coordinated with the database |
| Runtime | Docker |
| Instance/plan | **Free** |
| Root directory | Leave blank: repository root |
| Dockerfile path | `backend/Dockerfile` |
| Docker build context | `.`: repository root, not `backend` |
| Docker command | Leave blank to inherit `python start_server.py` |
| Health-check path | **`/api/health`** |
| Automatic deploys / previews | Off |

Do not select Existing Image, add a registry, create Render PostgreSQL/Key Value,
enable a persistent disk or add a paid pre-deploy job for this architecture.
Render Free has no interactive shell/pre-deploy command support; run the reviewed
migrations from the authorized operator machine. Startup checks the migration head
and **never** migrates, creates tables or seeds users.

Enter private values directly in Render Environment/managed secrets:
**`DATABASE_URL`** (limited runtime account), **`REDIS_URL`**, and a fresh random
**`SECRET_KEY`** of at least 32 bytes. Do not print them, send them in chat or place
them in `VITE_*`, Android assets, Git, deployment logs or Cloudflare Pages.

Enter every nonsecret setting from the template:

| Environment variable | Value |
| --- | --- |
| `ENVIRONMENT` | `production` — security mode, despite isolated staging resources |
| `PORT` | `10000` |
| `WEB_CONCURRENCY` | `1` |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `2` / `3` |
| `PGSSLROOTCERT` | `/etc/ssl/certs/ca-certificates.crt` |
| `SESSION_COOKIE_MODE_ENABLED` | `false` — cross-provider/native Bearer authentication |
| `RATE_LIMIT_ENABLED` | `true` |
| `AUTO_CREATE_SCHEMA` / `ENABLE_DEMO_DATA` | `false` / `false` |
| `PAYMENT_PROVIDER` | `disabled` |
| `PASSCODE_RECOVERY_ENABLED` | `false` — current SMTP transport is blocked on Render Free |
| `TRUSTED_HOSTS` | JSON array of the **assigned actual API hostname** and `127.0.0.1` |
| `CORS_ORIGINS` | `["https://canteenos-student-krishna.pages.dev","https://canteenos-admin-krishna.pages.dev","https://localhost"]` |
| `STUDENT_CORS_ORIGINS` / `ADMIN_CORS_ORIGINS` | `["https://canteenos-student-krishna.pages.dev"]` / `["https://canteenos-admin-krishna.pages.dev"]` |

`https://localhost` above is Capacitor's bundled app **origin**, never the backend
URL. Do not enable Admin cookie authentication for it. No wildcard origins/hosts.
Optional OCR/provider integration secrets belong only in backend-managed settings;
do not invent credentials or enable live payments to make a test succeed.

Use the real assigned `onrender.com` address shown by Render, including any suffix;
do not guess it from the proposed name. Service creation can trigger an initial
attempt before configuration/migrations are complete. Keep that attempt unaccepted,
finish private operator settings/migrations/runtime role, enter the assigned host,
then manually deploy again. No deployment success is claimed until both public
checks pass. The offline `deployment/check_managed_configuration.py` can validate
the operator's private process environment without connecting or printing values;
`--local-ca` checks the migration workstation's PEM trust bundle.

### Public acceptance gate — before any Android rebuild

From outside the provider network, request the actual HTTPS base origin plus:

- **`/api/health`**: HTTP 200 JSON **`{"status":"alive"}`**.
- **`/api/ready`**: HTTP 200 JSON with **`status="ready"`, `database=true`, `redis=true`**.

An HTML wake-up page, redirect, 200 response with wrong JSON or readiness 503 is
not acceptance. Use a trusted HTTPS certificate and the intended deployed revision.
Allow legitimate cold wake-up, then deliberately retry; do not continuously poll
database readiness or use a keep-awake workaround. Render Free sleeps after idle
traffic and can take about a minute to wake; this is a stated pilot limitation.
See [Render Free limitations](https://render.com/docs/free).

## 4. Cloudflare Pages — existing Direct Upload projects

Remain on Free. Use the existing projects in
[Workers & Pages](https://dash.cloudflare.com/e49f8c1863efc23f6e8088769f10bc3b/workers-and-pages).
Do not connect GitHub, create duplicate projects or upload the repository itself.

| Existing project | Exact local upload folder | Verified public origin |
| --- | --- | --- |
| `canteenos-student-krishna` | `dist/student` | https://canteenos-student-krishna.pages.dev |
| `canteenos-admin-krishna` | `dist/admin` | https://canteenos-admin-krishna.pages.dev |

From the repository root, build with these public process variables:

```powershell
$env:VITE_API_BASE_URL = 'https://canteen-staging-api.onrender.com'
$env:VITE_STUDENT_APP_URL = 'https://canteenos-student-krishna.pages.dev'
$env:VITE_ADMIN_APP_URL = 'https://canteenos-admin-krishna.pages.dev'
pnpm run build:pages
if ($LASTEXITCODE -ne 0) { throw 'Backend acceptance or Pages build failed.' }
```

The existing helper verifies actual health/readiness, rejects unsafe origins and
builds each app separately with Bearer authentication. For any future upload,
select the matching existing project → **Create deployment** → upload only that
project's output folder (or a ZIP whose `index.html` is at its root) → **Deploy site**.
Never upload the parent `dist`, `pages-deployment.json`, local configuration,
credentials, database files, Android artifacts or the other app's folder.
Dashboard environment changes do not rewrite already-built JavaScript: rebuild
and upload when the public API or app origins change.

Use `dist/pages-deployment.json` only to align the exact managed backend CORS
settings. Preserve native `https://localhost` and cookie-disabled mode. Activate
saved Render environment changes with **Save and deploy** or a fresh manual deploy;
**Save only → Restart service** keeps the previous deployed environment snapshot.
Verify public HTTPS health/readiness, both sites, login/menu/order/tracking and
shared Admin updates after every deployment. No continuous keep-awake workaround.

## 5. Android cutover — only after verified backend health/readiness

Follow [ANDROID_DEPLOYMENT.md](ANDROID_DEPLOYMENT.md). Set only the verified public
`CAPACITOR_API_BASE_URL`, run production URL validation, build/sync the Student
assets, verify the embedded API URL, then build/install the new debug APK with the
existing signing key. The source pipeline must not substitute a staging placeholder
or temporary tunnel, and the current APK must remain untouched while the backend
is not ready. A production frontend mode still produces a debug-signed test APK.

Physical-phone login/menu/order/tracking and graceful failures still need actual
testing after cutover. Future production requires separate resources, credentials,
origins, backups and capacity checks; do not point testing at live college tables.

**Remaining owner action:** transfer and install the rebuilt debug APK over the
existing phone app, then verify login/menu/order/tracking on the physical phone.
The backend and both web deployments have passed live checks. No provider account
setup, GitHub authorization or data transfer is required for this staging run.
No private credentials are needed in chat.
