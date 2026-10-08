# Mess Management

## STATUS

Implemented and running in the existing dashboard with real PostgreSQL and Redis.
Admin sign-in is working at http://localhost:8443/ using the locally configured account.
PostgreSQL and Redis both report healthy. The schema and seeds
were applied successfully. No mock fallback is used by this module.

With the user's approval, browser acceptance created `Krishna Israni (Demo)`, roll
`DEMO-KRISHNA`, with placeholder contact details and a clearly labeled demo payment.
No money was processed. The separate existing Krishna member was left untouched.
The approved demo remains available with 53 tokens and its complete audit history.

Installed to resolve the local startup failure: WSL 2.7.13.0, Docker Desktop 4.94.0,
Docker Engine 29.8.2 and Docker Compose v5.5.1, using official vendor sources.
Existing Compose PostgreSQL 16 and Redis 7 services are running.

## DATABASE CHANGES

Three new tables use the existing SQLAlchemy Base and existing `canteen_db`:

- `mess_plans`: configurable amount, tokens, duration and activation state.
- `mess_subscriptions`: nullable link to `students.id`, member details, agreed plan
  values, payment record, dates and balance; indexed roll, student, status and dates.
- `mess_meal_attendance`: deduction and reversal audit, admin references and timestamps.

The existing `init_db()` / `Base.metadata.create_all()` creates these additive tables.
There is no second application database or replacement schema.

Token bounds and meal/status values have database check constraints. A partial unique
index enforces one **Taken** record per subscription, date and meal. Reversal preserves
the original record, and a later re-mark creates a separate audit record. All token
mutations lock the subscription `FOR UPDATE` and commit balance and attendance together.
Overlapping subscriptions for the same roll are rejected under a PostgreSQL advisory
transaction lock, preventing consumption via two overlapping memberships.

Expiry is computed automatically on reads; exhausted status is persisted on deduction.
Only today's meals may be marked or undone; prior/future dates are read-only. Business
dates and displayed attendance times use IST. End date is start + configured duration
(default +30 days), matching the latest request, and the end date is inclusive.

## BACKEND ROUTES ADDED

All mess routes require the existing `get_current_admin` JWT dependency.

| Method | Route |
| --- | --- |
| POST | `/api/admin/login` (alias of existing admin JWT login) |
| POST, GET | `/api/admin/mess/subscriptions` |
| GET, PUT | `/api/admin/mess/subscriptions/{id}` |
| POST | `/api/admin/mess/attendance/mark` |
| POST | `/api/admin/mess/attendance/{id}/undo` |
| GET | `/api/admin/mess/attendance` |
| GET | `/api/admin/mess/stats` |
| GET | `/api/admin/mess/plans` |
| PUT | `/api/admin/mess/plans/{id}` |

Attendance GET accepts `meal_date`, `meal_type`, `search`, `filter`, `plan_type`.
Stats cover the selected date and meal, independently of search filters. The daily
token total includes all meals for the selected date; reversals are excluded.
Plan defaults use existing Redis caching and invalidation. Balances are always read
from PostgreSQL. Redis failure degrades gracefully using existing cache helpers.

## FRONTEND COMPONENTS ADDED

`MessManagement`, `MessMembersView`, `AddMessMemberModal`, `DailyAttendanceView`,
`MessMemberDetails`, `MessPlansView`, and shared `messUi` helpers.

The module reuses the existing AdminSidebar, AdminHeader and Toast. New screens use
existing beige/orange colors, white rounded cards and scrollable tables. Staff sign
in with FastAPI admin credentials; the separate admin JWT is kept in sessionStorage.
Expired/invalid sessions return to sign-in. Existing student authentication is unchanged.

Centralized `messApi` methods extend `apiClient`. Vite forwards `/api/admin` to
`FASTAPI_URL` (default `http://127.0.0.1:8000`). There is no client balance calculation
or local persistence fallback. A busy button and request lock prevent repeat clicks;
the backend remains authoritative. Conflicts refresh attendance and show a toast.

## FILES CHANGED

Modified:

- `backend/models.py`: new database tables, checks and indexes.
- `backend/schemas.py`: validated mess inputs; reject client balance/audit fields.
- `backend/main.py`: router registration and initial plan creation.
- `backend/routes.py`: unambiguous admin login alias.
- `backend/seed_data.py`: invokes the additive mess seed after existing seeds.
- `src/components/AdminDashboard.tsx`: module content and existing header title.
- `src/components/AdminSidebar.tsx`: Mess Management item using existing styling.
- `src/lib/apiClient.ts`: exposes centralized mess methods.
- `vite.config.ts`: FastAPI admin API proxy.

Added:

- `backend/mess_routes.py`: authorized queries, transactions and audit operations.
- `backend/mess_seed.py`: five demo members and matching meal ledger; reruns preserve balances.
- `backend/requirements-dev.txt`: backend testing dependencies.
- `backend/tests/test_mess.py`: API and PostgreSQL concurrency tests.
- `src/lib/messApi.ts`: typed API client and admin session.
- `src/components/MessManagement.tsx`
- `src/components/MessMembersView.tsx`
- `src/components/AddMessMemberModal.tsx`
- `src/components/DailyAttendanceView.tsx`
- `src/components/MessMemberDetails.tsx`
- `src/components/MessPlansView.tsx`
- `src/components/messUi.tsx`
- `MESS_MANAGEMENT.md`: setup, validation and limitations.

The prior startup task's `.gitignore` edit and ignored `backend/.env` remain in place.
No commits or pushes were made. No wallet or normal ordering behavior was changed.

## TESTS PASSED

- PostgreSQL backend: **17 passed in 85.66 seconds**, including competing meal requests
  against real PostgreSQL row locks and the partial unique index.
- The API tests cover both defaults, initialization, 55→54 lunch, duplicate rejection,
  54→53 dinner, retained history, undo/re-mark auditing, expiry, exhaustion,
  future/past dates, nullable student linking, overlap rejection, search/filters/stats,
  admin authorization, untrusted balance rejection, configurable/inactive plans,
  membership editing, database uniqueness and idempotent seeds.
- Earlier SQLite validation: 16 passed; the PostgreSQL-only test was skipped there.
- `pnpm exec tsc --noEmit`: passed.
- `pnpm run build`: passed.
- `python -m pip check`: passed.
- Browser acceptance using the approved demo: create with 55 tokens; Lunch 55→54;
  repeat Lunch rejected with HTTP 409 and balance 54; Dinner 54→53; Undo Dinner
  53→54 with reason; re-mark Dinner 54→53; full browser reload preserved the balance.
- Member details after reload show Tokens Used = 2, Tokens Remaining = 53 and
  Meals Taken = 2. The ledger retains Lunch Taken, original Dinner Reversed and
  replacement Dinner Taken. The reversal records reason, timestamp, admin and 53→54.
- The live health endpoint reports database healthy and Redis healthy; admin login
  through the Vite proxy succeeds. Existing student auth, weekly menu and API docs
  smoke checks also passed.

Evidence saved alongside this report: `mess-demo-balance.png` and
`mess-demo-history.png`.

## KNOWN LIMITATIONS

- There is no frontend unit-test runner configured. Type-check, production build
  and actual browser acceptance were used without adding another test framework.
- Production hosting must forward `/api/admin` to FastAPI, because Vite's development
  proxy applies only to local development.
- The approved demo membership is deliberately retained and labeled in its name
  and notes. Its recorded payment is demo data; no payment transaction took place.

## HOW TO RUN / VERIFY

Docker Desktop, PostgreSQL, Redis and both app servers are already running.
For future restarts, start Docker Desktop and use PowerShell:

```powershell
cd C:\Users\isran\Desktop\Canteen-Management-System\backend
docker compose up -d --wait postgres redis
docker compose exec postgres pg_isready -U postgres -d canteen_db
docker compose exec redis redis-cli ping
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe seed_data.py
# Restart the existing backend after infrastructure becomes available.
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```powershell
cd C:\Users\isran\Desktop\Canteen-Management-System
pnpm run dev
```

If port 8000/8443 is already occupied by this project's running server, stop that
server before starting another instance. If `docker` is not yet in a terminal's PATH,
open a new terminal or add `C:\Users\isran\AppData\Local\Programs\DockerDesktop\resources\bin`. Frontend URL: `http://localhost:8443`.
Admin credentials are configured locally in the ignored backend environment.
API docs: `http://127.0.0.1:8000/docs`. Health: `/api/health` must report both services
healthy before treating the live workflow as verified.

Open Mess Management and sign in with the configured admin credentials. For an additional test, use clearly labeled demo details, select Double Meal and
today's start date. The approved `DEMO-KRISHNA` record is already available.
Check 55 tokens. In Daily Attendance, search Krishna, mark Lunch, verify 54;
duplicate Lunch must remain 54. Mark Dinner, verify 53. View history for both rows
and Tokens Used = 2. Undo with a reason and verify one token restored and a retained
Reversed record. Refresh the browser to verify persistence.

Run backend tests:

```powershell
cd C:\Users\isran\Desktop\Canteen-Management-System\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests\test_mess.py -q
# Run against the existing PostgreSQL database using disposable test schemas:
$env:MESS_TEST_DATABASE_URL = (& .\.venv\Scripts\python.exe -c "from config import settings; print(settings.DATABASE_URL)")
.\.venv\Scripts\python.exe -m pytest tests\test_mess.py -q
Remove-Item Env:MESS_TEST_DATABASE_URL
```

PostgreSQL tests create and remove uniquely named test schemas; the application
schema is untouched. The database user needs CREATE SCHEMA permission. The PostgreSQL
concurrency test checks two competing Lunch requests plus Dinner: two successes,
one conflict, balance 53 and an uninterrupted 55→54→53 audit trail.
