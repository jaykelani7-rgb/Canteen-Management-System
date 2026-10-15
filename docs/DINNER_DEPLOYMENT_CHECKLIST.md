# Lunch and dinner bundle deployment

This change is prepared locally on top of `krishna` commit
`ca02c8945c0c12da5d3a121437897f540377b116`. It must be reviewed, committed and
deployed by the operator after verification. No dinner implementation commit or
cloud deployment is performed by this handoff.

## Database compatibility

No new migration is needed. Revision `0007_lunch_bundles` already stores
`sabji_options` and `ordering_enabled` on each `weekly_menu` row, uniquely keyed
by weekday and meal type. Lunch and dinner use independent existing rows.
Existing dinner rows remain disabled until an administrator configures them.
Preserve the encrypted pre-migration backup and its separate recovery identity.
Do not reset, seed, downgrade, or recreate tables.

## Deploy in this order

1. Review the complete local diff and test results. Commit the intended source,
   regression tests and this checklist to `krishna`, and push only that branch.
   Record the new commit SHA; the base SHA above does not contain dinner support.
2. In Render, open the existing Free `canteen-staging-api` service, confirm the
   repository and `krishna` branch, and manually deploy the reviewed new commit.
   Retain the current secrets, `backend/Dockerfile`, repository-root Docker
   context and inherited start command. Do not run another migration for dinner.
3. Verify the deployed SHA, `/api/health`, `/api/ready` (database and Redis true),
   `/api/menu/lunch` and `/api/menu/dinner` at
   `https://canteen-staging-api.onrender.com`. Both bundle APIs must return the
   correct `mealType`, server prices, serving window and independent contents.
4. Build both frontends from the same reviewed commit with the existing release
   command and public origins:

   ```powershell
   $env:VITE_API_BASE_URL='https://canteen-staging-api.onrender.com'
   $env:VITE_STUDENT_APP_URL='https://canteenos-student-krishna.pages.dev'
   $env:VITE_ADMIN_APP_URL='https://canteenos-admin-krishna.pages.dev'
   pnpm run build:pages
   ```

5. Direct Upload only `dist/admin` contents to the existing
   `canteenos-admin-krishna` Pages project, then only `dist/student` contents to
   `canteenos-student-krishna`. Do not interchange the folders, upload their common
   parent, or upload `dist/pages-deployment.json`. Recreate any ZIPs after the
   final build; older deployment archives are not the dinner artifacts.
6. In Admin -> Weekly Schedule, select a weekday and configure the Lunch and
   Dinner cards independently. Enter the actual complete meal contents, choose
   exactly two distinct included sabjis, enable the intended meal, and save that
   meal. Do not infer dishes from automated fixtures or enable unknown menus.
7. Verify the live Student meal selector, sabji selection, cart, wallet checkout,
   order history and Admin order updates using the synthetic test account.
   Lunch uses the existing 12:00-15:00 IST service window; dinner uses the
   existing 19:30-22:30 IST window. Outside the selected period, ordering must be
   rejected. Do not override the live clock to manufacture a passing result.
8. Check that a temporarily unavailable sabji cannot be selected or ordered,
   another valid sabji remains orderable, and zero available choices blocks only
   Chapati Bhaji while a valid remaining Thali can still be ordered. Verify OCR
   replacement of one period cannot corrupt the other period's configuration.
   Check old order snapshots remain unchanged after subsequent menu edits.

Use no external payment or new wallet credit for these checks. No APK generation
is part of this handoff. Deploy backend before the frontends because older
backends do not provide the dinner API or accept dinner configuration.
