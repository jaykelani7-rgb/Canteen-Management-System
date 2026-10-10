# Production deployment and operations

This repository contains one FastAPI application, two static frontends, and the existing PostgreSQL/Redis architecture. The production Compose/Caddy files are reviewable deployment templates. They have not been deployed to a public domain, and no existing data volume has been reset.

## Before release

1. Review the production audit and resolve release blockers. Rotate any real credential that reused a historical committed default. Keep all passwords, JWT/provider secrets, and production environment files outside Git.
2. Select separate student/admin DNS hostnames, point them to the intended host, and permit ports 80/443 for Caddy certificate provisioning.
3. Capture a PostgreSQL custom-format backup and verify restoration to an isolated staging database. Retain the existing application and database versions for rollback.
4. Adopt the existing legacy schema using the reviewed baseline-adoption process documented in the migrations guide. Do not blindly stamp an unverified schema, recreate tables, or run development seed scripts against production.
5. Provision separate database roles: the application account gets only required table/sequence reads and writes; the migration operator owns reviewed schema changes. Keep elevated migration credentials out of the API environment. Apply migrations first. The production API refuses to start unless its database revision matches the repository migration head.
6. Provision an administrator explicitly with `python manage_admin.py --username <username>` after migrations. Password input is hidden. Existing users are preserved. An authorized password reset uses the explicit `--reset` option and invalidates previous JWTs.
7. Configure `ENVIRONMENT=production`, a fresh random secret of at least 32 bytes, explicit HTTPS CORS origins, separate `STUDENT_CORS_ORIGINS` and `ADMIN_CORS_ORIGINS` matching their Caddy hostnames, and deployment hostnames. Each role list must be a disjoint subset of `CORS_ORIGINS`. Disable demo data and automatic table creation. Use the existing database credentials; changing an environment value does not change credentials on an existing PostgreSQL volume.
8. Keep payment configuration disabled until provider account, signing credentials, webhook delivery and reconciliation are verified. Passcode recovery remains disabled until a real SMTP provider, verified sender and correct registered student contact emails are provisioned. The implemented workflow uses short-lived HMAC-protected codes, bounded attempts and transactional single use; no plaintext code is stored or returned.

## Deployment template

Copy `deployment/configuration.example` to a private file outside the repository. Set `BACKEND_ENV_FILE` to a private backend environment file and `MIGRATION_ENV_FILE` to a separate private migration-operator environment file, and specify the existing PostgreSQL and Redis volume names.

Before a maintenance-window replacement, stop the old PostgreSQL container cleanly. **Never run two PostgreSQL servers attached to the same data volume.** Do not run `down -v`, create a new application database, or change the selected volume name.

```sh
docker compose --env-file /secure/canteen/deployment.env -f deployment/compose.production.yml build
docker compose --env-file /secure/canteen/deployment.env -f deployment/compose.production.yml run --rm migrate
docker compose --env-file /secure/canteen/deployment.env -f deployment/compose.production.yml up -d
```

PostgreSQL and Redis have no published host ports. Caddy provides TLS and serves `dist/student` and `dist/admin` on separate origins. Both origins proxy the unchanged `/api` prefix to the same backend. Production frontend builds use HttpOnly cookie mode. Cookie requests must originate from the frontend assigned to that role: mutating requests require an allowed Origin; reads validate Origin or the browser Referer origin. Requests missing both are rejected. Student and administrator origins remain separate even when ports share a cookie host or sibling domains are same-site. Programmatic Bearer requests remain supported. Role cookies have distinct names and do not grant access to the other role.

The API trusts forwarded headers only inside the private container network. Keep it unpublished. Redis is private to that network; authorization/rate limiting does not depend on a public Redis service.

## Backups and recovery

Use a dedicated least-privilege backup operator and secrets provided through an operator-managed password file or environment. Commands below are operator instructions, not automatically executed scripts.

```sh
umask 077
pg_dump --format=custom --file=/secure/backups/canteen-YYYYMMDD.dump --dbname=canteen_db
pg_restore --list /secure/backups/canteen-YYYYMMDD.dump
```

Encrypt backups at rest, copy them off-host, record checksums, and set a retention schedule appropriate to the project. Schedule a daily job only after a test restore succeeds. Credentials and dumps must not be committed.

Restore into an isolated **new staging recovery database**, never over the live application database:

```sh
createdb canteen_restore_check
pg_restore --exit-on-error --no-owner --dbname=canteen_restore_check /secure/backups/canteen-YYYYMMDD.dump
```

Verify migration revision, user/member/order counts, money ledgers and attendance balances in the restored copy. A recovery rehearsal does not create a second application backend/database and must remain isolated from live traffic. Production restoration requires an explicit maintenance decision, a fresh pre-restore backup, and a reviewed rollback plan; the repository does not automatically overwrite populated tables.

## Monitoring and response

- `/api/health`: process liveness, HTTP 200.
- `/api/ready`: PostgreSQL/Redis readiness; HTTP 503 on failure, generic dependency status, no credentials or exception text.
- Structured backend logs include request ID, method, path, response status and duration. Bodies, query strings, tokens and account identifiers are excluded.
- Alert on readiness failures, elevated 5xx/429 responses, payment webhook/reconciliation failures, database/storage exhaustion and backup failures. Connect these log/health signals to the selected monitoring service before production release.
- Set deployment CPU/memory/storage budgets and database connection limits for the intended capacity. Existing engine pools are per worker; load testing is required before claiming lunch-break capacity.
- Validate logout, expired/reset credentials, role separation, CSRF, payment readiness, transaction retries and both frontend builds in staging.
- Refresh stored secrets through the deployment platform and restart the API. Changing the JWT signing secret invalidates all sessions.
- Pin deployment image digests after validating the chosen architecture and images. The checked-in image tags are explicit starting templates, not immutable production attestations.

## Current boundaries

No public-domain deployment, physical Android installation, real payment-provider settlement, scheduled backup job, off-host retention or production load test is claimed. CI and deployment files are provided for review and operation after environment-specific credentials, DNS, certificates and service account permissions are provisioned.

## Passcode recovery delivery

Apply migration `0005_secure_recovery` only after the reviewed `0004_wallet_refunds` migration. It adds recovery audit history; it does not delete users, legacy OTP records or existing data. The old plaintext OTP table is unused.

Set `PASSCODE_RECOVERY_ENABLED=true` only after provisioning `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, a verified `SMTP_FROM_EMAIL` and, when required, paired private `SMTP_USERNAME`/`SMTP_PASSWORD` credentials. `starttls` and `ssl` both use system-trusted certificate and hostname verification. Plaintext SMTP and debug/dummy delivery are unsupported. Do not commit SMTP credentials.

Verify the existing registered email for each account before enabling recovery: this repository does not claim that historical or generated campus addresses were already email-verified. Recovery never accepts a destination email in its request. Updating the stored contact or passcode invalidates outstanding challenges. Codes expire after five minutes by default, lock after five incorrect attempts, and become unusable once consumed or superseded. Account and aggregate source-IP limits apply independently.

Request responses are identical for eligible, missing and inactive accounts and delivery failures. Email is sent after the HTTP response, avoiding provider-latency account enumeration; failed delivery leaves an unusable audited challenge. Background delivery is deliberately bounded and in-process: a worker restart can lose an unsent code, and a user must request another after the cooldown. There is no plaintext retry queue or fake success transport. Monitor generic `recovery_delivery_failed`/`recovery_delivery_unavailable` events, and verify actual provider delivery in staging before declaring recovery available.

Successful reset requires signing in again and invalidates every existing credential-bound session. It does not issue an automatic login token. The test suite mocks delivery and verifies expiry, replay rejection, lockout, supersession, contact/credential changes, failures and PostgreSQL concurrency; running those tests sends no real email.

A local rehearsal on 2026-10-09 restored a verified archive into a temporary schema of the existing database: all 17 archived table counts matched, and original public-schema counts remained unchanged. The disposable rehearsal schema was then removed. This demonstrates that archive restoration was checked locally; it does not claim scheduled or off-site backups, a public deployment, or production recovery readiness.


## Verified wallet funding and full refunds

Apply the reviewed additive `0004_wallet_refunds` then `0005_secure_recovery` migrations before restarting the API. Existing order, wallet and mess rows are preserved. Configure Razorpay only through private server settings; the frontend receives the public checkout key, never the signing secrets. Enable provider webhook events for payment capture/authorization/failure and refund creation/processing/failure. Test actual raw-body signatures, delayed callbacks and retries against staging before enabling a live account.

Wallet funding credits exactly once after server verification of a captured payment. Food payment intents expire after `PAYMENT_ORDER_EXPIRY_MINUTES` (15 by default); late captures are refunded and cannot enter the kitchen. Top-ups do not expire while funds may still settle. Refund retries retain the persisted `X-Refund-Idempotency` key and identical full-refund body, including after an uncertain network response. Pending or failed refunds do not appear completed.

Use Live Orders → Payment Review to check unresolved intents and persisted refund status. Locate uncertain provider-order creation by its stored receipt and bind the existing order; never create another provider order manually for that intent. Full provider-dashboard refunds are reconciled; partial/multiple refunds require reviewed accounting. A spent refunded wallet balance records the unrecovered amount and freezes the account until an operator completes a reviewed adjustment. There is no automatic partial allocation, debt clearing or student account reactivation workflow. Document those policies with the college before release.

All current gateway verification used mocks; no real payment or refund was executed. SMTP recovery also remains disabled locally. Real merchant activation, sender/contact verification, Gemini verification, public TLS, monitoring and capacity testing remain deployment requirements.
