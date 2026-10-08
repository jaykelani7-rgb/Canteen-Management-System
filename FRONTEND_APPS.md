# Separate Smart Canteen frontends

The student PWA and admin web now have separate entrypoints, sessions, bundles and servers. Both use the existing FastAPI service, PostgreSQL database and Redis instance. The existing student and admin visual styles are retained.

## Start locally

Use three PowerShell terminals. Keep the existing database and Redis running; do not reset their volumes or run a new database.

Backend:

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System\backend'
.\.venv\Scripts\python.exe -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Student development server:

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System'
pnpm run student
```

Admin development server:

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System'
pnpm run admin
```

| Application | Laptop URL | Output |
| --- | --- | --- |
| Student | http://localhost:5173 | `dist/student` |
| Admin | http://localhost:8443 | `dist/admin` |
| Shared backend | http://localhost:8000 | Existing FastAPI application |

If a server is already running on its port, use that server or stop it before restarting. `pnpm run dev` starts admin. No second API server runs through Vite.

## Production builds and PWA preview

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System'
pnpm exec tsc --noEmit
pnpm run build
```

After stopping the student development server on port 5173:

```powershell
pnpm run preview:student
```

For the admin build, stop the admin development server on port 8443 and use:

```powershell
pnpm run preview:admin
```

The service worker registers only in a production build served from a secure origin. Development uses normal Vite refresh without a service worker. Preview still proxies `/api` to the same backend. The student production preview is currently running on port 5173.

## Open from an Android phone

1. Start the backend and student server. Connect the phone and laptop to the same Wi-Fi.
2. Run `ipconfig` on the laptop. Find the IPv4 address of the connected Wi-Fi adapter.
3. Open `http://<LAPTOP_LAN_IP>:5173` in Android Chrome. Replace the placeholder with that address; do not use `localhost` on the phone.
4. If Windows prompts about the frontend server, allow it on the intended private network. The network must permit devices to communicate with each other.
5. Sign in with an existing student account or register a student. Browse Menu, add food, open Cart, proceed to Checkout, place an order, and use Track my order live / Your orders.

Both frontend servers bind to `0.0.0.0`. The default same-origin `/api` proxy runs on the laptop, so the backend can remain bound to `127.0.0.1`; no phone-specific API IP is required.

### Install to the home screen

An HTTP LAN address supports browsing, but it is not a secure PWA origin. Android service-worker installation requires HTTPS with a certificate trusted by the phone. Desktop `localhost` has a development secure-origin exception; the laptop's LAN IP does not.

For a trusted HTTPS preview:

1. Obtain a certificate and private key for the hostname or address you will open. The certificate must be valid for that hostname/address and trusted on the Android device.
2. In the student preview PowerShell terminal, set paths to those existing certificate files:

```powershell
$env:HTTPS_KEY_FILE = 'C:/certificates/canteen-key.pem'
$env:HTTPS_CERT_FILE = 'C:/certificates/canteen-cert.pem'
pnpm run build:student
pnpm run preview:student
```

3. Open `https://<CERTIFICATE_HOSTNAME_OR_LAN_IP>:5173` in Android Chrome, without a certificate warning.
4. Once loaded online, choose Chrome's **Install app** or **Add to home screen** action. Launch **Smart Canteen** from the home screen, sign in, and verify an order in the standalone app.

Alternatively, host `dist/student` at a trusted HTTPS domain and route `/api` to the existing backend. Serve `dist/admin` on a separate origin. Preview is intended for local verification, not production hosting.

Actual Android installation has not been verified on a physical phone. The manifest, icon dimensions, mobile viewport, built service worker and its local registration have been checked.

## API and environment configuration

Frontend configuration is loaded from the repository root. Preserve existing `.env` values. `configuration.example` lists optional settings; add overrides to `.env.local` or set PowerShell environment variables instead of overwriting existing configuration.

| Setting | Purpose |
| --- | --- |
| `FASTAPI_URL` | Server-side Vite proxy target. Defaults to `http://127.0.0.1:8000`. |
| `VITE_API_BASE_URL` | Optional public API origin, for example `https://api.example.edu`, without `/api`. Leave unset for the same-origin proxy. Both clients append existing `/api/...` paths. |
| `VITE_STUDENT_APP_URL` | Student URL for the admin header's external Open Student App link. Development defaults to the current hostname on port 5173. Set the deployed student URL for production. |
| `HTTPS_KEY_FILE` / `HTTPS_CERT_FILE` | Optional trusted HTTPS certificate paths for dev/preview. |

`VITE_*` values are public build-time settings. They must not contain JWT secrets, database credentials or private keys. Rebuild after changing them.

For direct cross-origin API requests, configure `CORS_ORIGINS` in the existing backend environment as a JSON array of explicit frontend origins. Defaults allow localhost and 127.0.0.1 on ports 5173 and 8443. `backend/configuration.example` documents the format. Add the actual HTTPS frontend origins when deploying; restart FastAPI after changes. Same-origin `/api` proxy requests need no additional browser CORS origin.

For a fresh checkout, copy `backend/configuration.example` to the ignored `backend/.env` and replace every placeholder. `DATABASE_URL`, `SECRET_KEY` and `DEFAULT_ADMIN_PASSWORD` are required; Compose also requires `POSTGRES_PASSWORD`. Existing local values were retained in `.env` when removing hard-coded defaults for the checkpoint. Do not change the database password on an existing populated volume just by changing Compose; provision credentials to match the existing database.

## Source ownership

```text
src/App.tsx                 Admin-only entrypoint and global auth gate
src/components/             Existing admin dashboard and mess screens
src/lib/adminApi.ts         Admin session/API client
src/lib/messApi.ts          Existing mess API client
src/lib/apiClient.ts        Student session/API client
src/lib/studentTypes.ts     Student response types
src/lib/apiConfig.ts        Small shared API-origin helper
src/index.css               Existing shared typography/design tokens
student/index.html          Student document and PWA metadata
student/src/                Student app, mobile CSS and PWA registration
student/public/             Manifest, icons, static service worker and offline page
vite.config.ts              Admin configuration
vite.student.config.ts      Student configuration
backend/                    One existing backend
```

The single root package and lockfile are retained to avoid duplicating dependencies. Student features do not import admin features; admin does not mount the student app. Open Student App opens the independent URL in a new tab.

## Data, sessions and offline behavior

- Student authentication uses the existing student JWT and a separate session-storage key. Admin authentication retains its own JWT and global AdminAuthGate. Backend role checks reject the opposite role.
- Menu, order history, tracking, wallet balance and wallet history come from FastAPI. Logout clears student state; late responses cannot restore a logged-out session.
- The service worker caches only public shell/assets from an explicit allowlist. API, authorized, cross-origin and non-GET requests are excluded. Offline navigation displays a generic connection page. It never queues orders or caches profiles, orders or balances.
- Existing mess schema, attendance transactions and admin order-status security are unchanged by this separation. No schema migration or database reset was required.

## Verification and current limits

- Both frontend builds and TypeScript checks pass.
- All 61 backend tests pass, including seven new CORS/role-isolation cases. Tests use disposable PostgreSQL schemas.
- Seventeen separation/session/PWA safety checks pass.
- After building, run `pnpm run test:separation` to reproduce the separation/PWA checks.
- Browser verification completed student login, live menu, cart, checkout, order confirmation, tracking and history. A labeled demo student and wallet order persist in the shared PostgreSQL database.
- Admin global sign-in, sidebar and all existing section screens were checked. Mess plans continue loading their existing backend values.
- Existing OCR, Live Orders, Analytics and other legacy admin demo/local-state behavior is preserved; separation does not make those screens newly integrated with live backend data.
- Existing UPI/card payment handling is simulated. The student checkout labels those choices as demo payments; no payment gateway was added. Wallet ordering uses the existing database ledger.
- Physical Android installation, actual Wi-Fi/firewall reachability and HTTPS certificate provisioning remain device/environment checks.
