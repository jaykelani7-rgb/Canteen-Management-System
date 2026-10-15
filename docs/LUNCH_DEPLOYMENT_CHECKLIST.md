# Lunch feature deployment handoff

Prepared locally on 15 October 2026. No commit, push, cloud deployment, live database migration, or APK build was performed.

## What changed

The Student app previously ordered only `FoodItem` catalogue entries. `WeeklyMenu` was display-only: it had no bundle prices, two-sabji configuration, or order selection contract. Admin Weekly Schedule was read-only.

- Admin → Weekly Schedule now edits each weekday's complete lunch, two sabji choices drawn from that meal, and an ordering toggle.
- `GET /api/menu/lunch` exposes today's IST lunch and fixed server prices: Chapati Bhaji ₹45; Thali ₹80. Both cards remain visible when closed or unconfigured.
- Chapati Bhaji requires exactly one configured sabji and contains three chapatis plus salad. Thali uses every configured current lunch item.
- Backend validates availability, existing 12:00–15:00 IST serving window, choice, price and menu revision. It snapshots meal date, contents and choice in existing order JSON.
- Student cart separates sabji variants; checkout refreshes lunch and rejects stale carts. History and Admin Live Orders use saved snapshots. Existing wallet/payment/idempotency and à la carte paths are retained.

## Verified locally

- Full backend suite: **290 passed, 15 skipped**. PostgreSQL-only migration/row-lock cases were skipped; no deployed PostgreSQL database was modified.
- Focused lunch, additive migration and weekly bulk-save tests: **27 passed**. Migration tests exercised existing-row preservation in SQLite and generated PostgreSQL additive DDL.
- Student lunch: **24 checks passed**; Admin lunch: **7**; original Student menu: **10**.
- TypeScript passed. Student and Admin production builds passed. PWA/separation: **22 checks passed**; Pages configuration: **10**.
- Both built JavaScript bundles contain `https://canteen-staging-api.onrender.com` and exclude localhost/LAN/placeholder/tunnel API targets.
- Existing backend health/readiness returned success during the build (database and Redis ready). This verifies the existing deployment only, not the new lunch feature live.

## Deployment order — operator actions

1. Review the local changes, including new/untracked files. Current branch is `krishna`, based on `5ff7df8ea8a94e9f7c6b7c857da844617a765b8b`. There is **no new commit SHA yet**. Commit and push the intended reviewed code to `origin/krishna` yourself; preserve unrelated local edits. Include migration `0007_lunch_bundles.py`, new lunch services/components/helpers and tests. Never push to `main`.
2. Back up the existing Neon database using the existing database runbook. Privately configure the existing migration-owner connection via `MIGRATION_DATABASE_URL` with TLS; keep runtime `DATABASE_URL` unchanged. Do not paste credentials into chat or Git. From the repository's `backend` directory run:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic -c alembic.ini current
   .\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
   .\.venv\Scripts\python.exe -m alembic -c alembic.ini current
   .\.venv\Scripts\python.exe -m alembic -c alembic.ini check
   ```

   Expected head: **`0007_lunch_bundles`**. This adds only `weekly_menu.sabji_options` and `ordering_enabled`; old rows default to empty options and ordering disabled. No tables/data are dropped or seeded. Do not stamp head, reset data or run downgrade. Startup does not migrate automatically and rejects an outdated database revision.
3. Render → existing **canteen-staging-api** → confirm branch **krishna** → **Manual Deploy → Deploy latest commit**. Confirm it deploys your new reviewed commit. Keep Free plan, existing environment, `backend/Dockerfile`, repository-root Docker context, and inherited `python start_server.py` command. Verify `/api/health` and `/api/ready` at `https://canteen-staging-api.onrender.com`; readiness must report database and Redis `true`.
4. Cloudflare Pages → existing **canteenos-admin-krishna** → new Direct Upload deployment → upload **`dist/admin`** contents. Its root must contain `index.html` and `assets/`. Preserve the existing project. Open the Admin site, sign in, and configure each required weekday under Weekly Schedule: actual complete meal, exactly two distinct included sabjis, then enable lunch ordering and save.
5. Cloudflare Pages → existing **canteenos-student-krishna** → new Direct Upload deployment → upload **`dist/student`** contents, including `index.html`, `assets/`, service worker, manifest and icons. Do not interchange folders or upload their common `dist` parent. Do not upload `dist/pages-deployment.json`.
6. Existing public origins remain unchanged. Verify backend CORS still includes exact `https://canteenos-student-krishna.pages.dev` and `https://canteenos-admin-krishna.pages.dev` (retain existing native origin if configured); no wildcard or new secrets are needed. Both apps use the same backend/database with Bearer authentication.
7. During today's configured **12:00–15:00 IST** lunch window, verify both cards. Chapati Bhaji cannot be added without one sabji; two different choices remain separate cart lines. Verify ₹45 and ₹80 totals and real wallet deductions using your authorized test account. Check history and Admin visibility/status updates, then edit the menu and confirm the old order contents remain unchanged. Verify à la carte and mixed orders. Outside the window, lunch must show closed and reject ordering. Confirm these live results before requesting the Android phase.

## Exact artifacts and configuration

- Student: `C:\Users\isran\Desktop\Canteen-Management-System\dist\student`
- Admin: `C:\Users\isran\Desktop\Canteen-Management-System\dist\admin`
- Student URL: `https://canteenos-student-krishna.pages.dev`
- Admin URL: `https://canteenos-admin-krishna.pages.dev`
- Shared API origin: `https://canteen-staging-api.onrender.com` — this is the existing staging backend, not a newly created production service.

Rebuild after any further source changes using the existing release script with these public process variables: `VITE_API_BASE_URL`, `VITE_STUDENT_APP_URL`, `VITE_ADMIN_APP_URL`, then `pnpm run build:pages`.

Android/Capacitor files were not changed. No APK was generated for this feature.
