# PRODUCTION AUDIT

Audit completed before implementation on 8 October 2026. This report separates the audited baseline from the changes subsequently made. The application has been restarted locally; production release is still conditional on the remaining items below. No commit or push was made for this hardening work.

## A. Current architecture

Two independently built React frontends (`dist/student`, `dist/admin`) share one FastAPI application, one existing PostgreSQL database and Redis. PostgreSQL owns users, catalogue, orders, wallet ledgers, mess subscriptions and attendance history. Redis provides optional menu caching and production login rate limiting. The student build contains the existing PWA assets; the admin build remains a web application. Existing beige, white and orange styling is preserved.

## B. Production gaps found before changes

| Area | Audited baseline | Changes and current boundary |
| --- | --- | --- |
| Student frontend/PWA | Partly integrated; simulated external payments and invented calories | Durable checkout retries, verified payment confirmation, pending order recovery, session guards; existing PWA preserved. Physical-device/HTTPS installation unverified. |
| Admin frontend | Authentication and mess worked; core screens used local mock state | Database-backed catalogue, Live Orders, weekly menu, analytics and OCR review/save. Existing design retained. |
| FastAPI | Functionally useful; unsafe startup seeds and error handling | Separate role auth routes, generic errors, request IDs, strict production startup and readiness. |
| PostgreSQL | Row locks in mess; money stored as floats; no migrations | Decimal cents, financial constraints/FKs, idempotency, PostgreSQL order sequence and Alembic revisions. |
| Redis | Useful cache; exposed ports; unbounded demo fallback patterns | Private production network, bounded login limiter; availability shown by readiness. Redis remains nonauthoritative. |
| Authentication/authorization | Universal student passcodes and reset bypass; public student directory | Actual hashed verification, removed bypasses/directory, credential-bound JWTs, role guards, rate limits, optional HttpOnly cookies and CSRF origin checks. |
| Orders/lifecycle | Client prices trusted; count-based numbers; arbitrary transitions | Authoritative catalogue/customization pricing, bounded inputs, serialized lifecycle, sequence-based numbers and legal transitions. |
| Wallet/payments | Fake recharge/UPI success; race-prone debit and repeated refunds | Row-locked debit/refund and ledger constraints. Unverified recharge disabled. Gateway capture is verified; refund automation remains incomplete. |
| OCR | Public/unbounded uploads; simulated frontend extraction/save | Admin-only image validation, byte/pixel bounds, async timeout, validated structured result, explicit review and persistent save. Real provider call needs configuration. |
| Notifications | Broadcast read changed another student's state | Per-student read receipts with legacy targeted-read compatibility and ownership checks. Delivery remains in-app. |
| Mess | Row locking, Taken uniqueness and history-preserving undo already good | Existing behavior retained and regression/concurrency tests exercised. |
| Environment/configuration | Weak defaults in old history; no strict production separation | Development/test/production validation, no secret fallbacks, no automatic production seed/schema creation. Local private environment values retained. |
| Security | Public OCR, mutation bypasses, simulated money | API role/ownership enforcement, protected status routes, strict CORS/hosts, fail-closed payment/recovery. Further operational credential review required. |
| Logging/errors | Password bootstrap logging and raw exception responses | Structured request logs without bodies/tokens/query strings; generic production error responses. |
| Tests | Existing tests accepted demo financial behavior | Updated regression assertions plus gateway signature/capture, wallet concurrency, OCR and migration tests in disposable schemas. |
| Builds | Separate builds existed; verification harness needed updates | TypeScript, both production builds and 22 separation/PWA/session/idempotency checks pass. |
| Containers | Local PostgreSQL/Redis only | API/frontend Dockerfiles and reviewed production Compose template. Full production image build/deployment not exercised. |
| Deployment | Root dist assumption, no HTTPS proxy/CI | Separate origins via Caddy TLS, shared /api proxy, CI checks, migration service and private storage/network configuration. DNS/TLS not provisioned. |
| Migrations | Startup create_all only | Frozen baseline, strict read-only adoption/preflight, additive hardening/payment revisions and production head check. |
| External APIs | Gemini configuration possible; payments simulated | Razorpay adapter implemented against official docs; payment account and notification-delivery decisions outstanding. |

## C. Security risks and fixes

The old student login accepted `000000` or `123456` regardless of the stored hash; reset also accepted a universal code and returned plaintext OTPs. Those active paths were removed. Known existing demo accounts can still sign in with their own actual hashed passcodes. New registrations begin with zero wallet balance. Recovery now uses hashed, short-lived, single-use challenges and a verified TLS/SSL SMTP adapter. It remains unavailable until real SMTP delivery and trusted registered contacts are configured. No OTP or password is exposed by a response or startup log.

Both roles are checked server-side, including active-account checks and credential fingerprints so password changes invalidate issued sessions. Production builds use role-specific HttpOnly, Secure, SameSite cookies; cookie reads require the matching frontend role Origin (or a matching read Referer), and mutations require the matching role Origin. Bearer authentication remains supported for programmatic clients. No refresh-token system is claimed; sessions expire and users sign in again. Login rate limiting uses Redis in production and fails closed on dependency failure.

No `.env` or private credentials are tracked. Historical development JWT/database/admin defaults were found in the old commit `13cf35d`; history was preserved and values are deliberately not reproduced here. If any deployed credential reused those defaults, rotate it before release. Legacy prototype server files remain outside the active frontend/backend runtime and must not be separately exposed as an alternative authentication server.

## D. Database risks and fixes

Money is represented as `Numeric(12,2)` and business arithmetic uses Decimal rounding. The server locks the student row for wallet creation/refund and locks the order for lifecycle changes. Successful order-linked ledger records are unique by student/order/type. The server requires a durable Idempotency-Key, checks its canonical request fingerprint and returns the existing order on retry. A PostgreSQL sequence initialized above legacy order numbers avoids both concurrent and seeded-number collisions. Client balance, price, name and payment-success claims do not determine payable amounts.

Mess attendance continues locking subscriptions, enforcing one active Taken record per subscription/date/meal, preventing negative tokens and retaining reversal history. Plan changes preserve purchased snapshots. IST is authoritative for business dates; the UI timezone does not validate attendance.

The populated local database was backed up and read-only preflight passed. Reviewed additive migrations through `0005_secure_recovery` are applied; all 17 table counts present immediately before the latest upgrade remain unchanged. `alembic check` reports no schema drift. A complete archive restore into an isolated schema of the existing database verified counts and row fingerprints for all 17 archived tables; application data was unchanged and the rehearsal schema was removed. Production off-host retention and a deployment-specific restore drill still require operator setup.

## E. Payment risks and fixes

The adapter creates an INR gateway order from a durable, server-priced intent in integer paise. Frontend checkout receives only the public key and provider order details. A successful browser callback is insufficient: the server verifies the HMAC against its stored provider order, fetches the provider payment, and checks identifier, exact amount, currency and captured state. Authorized payments remain unpaid. Capture and notification/stat updates are idempotent under row locks; unique provider identifiers prevent reuse.

Webhooks verify HMAC over the exact raw request body, bound body size and store unique provider event receipts and body hashes. Duplicate callbacks/webhooks cannot charge the wallet or confirm the order twice; failed/reordered events do not downgrade a captured payment. Pending checkout can resume after refresh. Ambiguous provider order creation is retained as reconciliation_required rather than blindly issuing a second payment order. Admin-only reconciliation verifies provider order receipt and amount before binding an existing gateway order. Abandoned payments remain pending or can be cancelled without entering the kitchen.

Gateway credentials are disabled by default and server-only. Verified wallet top-ups now persist a purpose-specific payment intent and immutable successful ledger credit; captured provider details determine the credited amount. Student-scoped idempotency keys and row locks prevent duplicate credits and lost balances during concurrent spending. Pending top-ups can resume and ambiguous initialization is reconciled without a second provider-order POST.

Eligible gateway order cancellations persist a full-refund request before contacting Razorpay. Timeout retries reuse the same durable provider idempotency key and exact request body. Pending/failed refunds retain the paid status; only a server-fetched processed refund changes it to Refunded. Signed refund webhooks and admin reconciliation preserve monotonic completion. Late captures for cancelled/expired food checkouts are refunded without entering the kitchen; checkout expiration is server-configured. Admin order polling includes persisted refund status.

Credited top-ups cannot be refunded through the generic operator route without a reviewed account adjustment. A verified full provider-dashboard refund recovers available funds once; any spent shortfall is recorded and the student account is frozen, without creating a negative balance. Partial or multiple provider refunds require explicit accounting review and suspend further spending/fulfilment rather than inventing a full refund. There is no automatic debt-clearing or partial-refund allocation workflow. Payment Review exposes the required operator attention.

Do not enable public payments until merchant activation, the college refund policy and end-to-end provider test-mode checkout/webhook/refund behavior have been verified. All financial tests used mocked provider responses; no real money was processed.

Implementation references: [Razorpay standard checkout integration](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/), [create order API](https://razorpay.com/docs/api/orders/create/), [webhook validation](https://razorpay.com/docs/webhooks/validate-test/). These prescribe server order creation, payment signature verification and raw-body webhook validation; provider activation and settlement were not tested. Refund retries follow [Razorpay idempotent refunds](https://razorpay.com/docs/api/refunds/normal-refunds-idempotent/); confirmation uses [specific refund retrieval](https://razorpay.com/docs/api/refunds/fetch-specific-refund-payment/). Migration environment follows the [Alembic async cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html).

## F. Deployment risks and requirements

Use a single cost-conscious host with separate student/admin static origins, Caddy TLS, one API, private PostgreSQL and Redis, and persistent existing volumes. The production Compose configuration validates, but has not been deployed. See `deployment/PRODUCTION.md` for commands, operator permissions, private configuration, backups and recovery. Pin tested image digests and transitive dependency hashes before release; current direct Python versions are pinned, not a complete supply-chain attestation.

Before release provide DNS/HTTPS hostnames, merchant gateway account and test/live server credentials, webhook signing secret, confirmed price/GST/packaging/refund policy, Gemini account configuration, verified SMTP recovery contacts and a notification-delivery decision, least-privilege database roles, encrypted off-host backups/retention, a production restore drill, monitoring and a staging lunch-period load test. Test the Razorpay CSP allowlist against the actual hosted checkout before enabling payments. Do not reuse local demo data/credentials as an implicit production onboarding policy.

## G. Implementation and verification record

Priority order followed: audit; authentication/authorization; non-destructive migration and monetary correctness; legal order lifecycle; verified payment adapter; real admin/student API integration; OCR/menu persistence; real analytics; deployment and observability; local restart and integration checks. Three scoped parallel agents worked on frontend, infrastructure/auth and database/OCR/operations, with root coordinating order/payment correctness and integration.

Verified locally: backend liveness/readiness return HTTP 200 with PostgreSQL/Redis healthy; admin sign-in opens the normal dashboard; sidebar order and exactly three mess children are correct; members and both plan values persist; student sign-in loads the preserved order. TypeScript and both builds pass; 22 frontend separation/PWA/session/idempotency checks pass. Current backend verification across all test modules: 119 regression/recovery/auth/OCR/mess/student cases, 14 order/migration cases and 19 financial cases passed (152 total, with database and concurrency cases exercised against PostgreSQL). TypeScript, both builds, 22 separation/PWA checks and 9 isolated financial frontend checks passed. Local database/cache container ports now bind only to 127.0.0.1.

Local fresh startup URLs: admin http://localhost:8443/, student http://localhost:5174/, API http://localhost:8000/. Port 5173 belonged to an unrelated TradeMind project and was preserved. Existing source changes, branch krishna, users, wallet balances, orders and mess history were preserved.

DONE: highest-risk active demo auth/money paths removed; safe database migrations, verified order capture and wallet top-ups, durable full refunds and reconciliation, secure configurable recovery, persisted screens, protected OCR and deployment templates implemented. Local application data is preserved. Final browser checks show admin login, persisted Live Orders, Payment Review, student login and the preserved wallet; unconfigured funding is explicitly disabled.

REMAINING / BLOCKERS: merchant activation and confirmed refund/account-adjustment policy; real SMTP configuration with verified contacts; real Gemini/payment/delivery staging verification; public HTTPS/domain deployment; off-host backups, monitoring and capacity testing. Partial/multiple provider refunds or spent refunded wallet funds require manual accounting resolution. These are release gates, not claims of completed production deployment.

NEXT STEP: provide private operator configuration and merchant/recovery decisions, then validate real test-mode providers and DNS/TLS in staging before public release. No secrets, commits or pushes were created for this hardening work.
