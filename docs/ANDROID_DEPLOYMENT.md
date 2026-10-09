# Android connection after backend deployment

The owner installed the earlier placeholder APK and confirmed its UI renders.
On 9 October 2026, after real health/readiness passed, the Student debug APK was
rebuilt with **https://canteen-staging-api.onrender.com**. On 10 October its payload, all
13 Android checks and unchanged signing certificate were independently verified.
It contains the bundled Student frontend, no temporary tunnel, placeholder or
remote `server.url`. The owner still needs to install this update; physical-phone
login/menu/order/tracking against the deployed backend has not been verified.

APK SHA-256: `5ef1d508b2f7f4918a377cb6cef125c47e29ef0e660cee8a0538d4decdddebf9`.
Web deployments use the same API and database; no further APK rebuild is needed
unless its configured API origin or Student application code changes.

## Required public configuration

Obtain the actual HTTPS **API base origin** from the deployed provider service. For the free staging route, Render displays the service's real `onrender.com` HTTPS address after deployment. The verified staging origin is `https://canteen-staging-api.onrender.com`. A later production API should use its approved stable hostname. Provide only this public URL; configure database/JWT/Redis/provider secrets privately in server-managed variables, never in chat, `VITE_*`, Android assets or Capacitor configuration.

The base must not end in `/api`: the existing API client adds `/api/...`. The production builder rejects absent URLs, documentation domains, private/local/reserved IP addresses and hostnames, credentials, query strings, fragments and known temporary tunnel addresses. A syntactically accepted hostname is not proof of public DNS, TLS or backend health; verify those independently first. Staging still permits the explicitly labeled documentation placeholder so packaging can be prepared without inventing a deployment.

Capacitor serves local bundled files from `https://localhost`; that is the packaged app origin, **not the backend address**. Allow that exact origin for Student Bearer requests alongside the real Student/Admin web origins. Do not enable cookie sessions for the native origin or permit it for Admin browser-cookie authentication. Retain the existing Authorization, Content-Type and Idempotency-Key request headers. Both Admin and Student must point to the same backend/database within staging or production.

## Verify HTTPS before rebuilding

Run from an operator machine outside the hosting network after copying the actual public URL from the dashboard. The commands prompt for a public address instead of supplying a fake deployment address:

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System'
$taskPublicApi = (Read-Host 'Paste the deployed public HTTPS API base origin, without /api').Trim().TrimEnd('/')
$env:CAPACITOR_API_BASE_URL = $taskPublicApi
# Validates the URL without building or changing the APK.
node --input-type=module -e "import { androidBuildConfig } from './scripts/android-build-config.mjs'; console.log(androidBuildConfig('production', process.env).apiBaseUrl)"
if ($LASTEXITCODE -ne 0) { throw 'The API base URL is not suitable for a release build.' }
# Free Render may take approximately one minute to wake from idle.
$taskHealth = Invoke-WebRequest -Uri "$taskPublicApi/api/health" -TimeoutSec 120 -UseBasicParsing
$taskReady = Invoke-WebRequest -Uri "$taskPublicApi/api/ready" -TimeoutSec 120 -UseBasicParsing
if ($taskHealth.StatusCode -ne 200 -or $taskReady.StatusCode -ne 200) { throw 'Public health/readiness did not pass.' }
$taskHealth.Content
$taskReady.Content
```

Inspect the health/readiness bodies as well as status codes; they must come from the intended FastAPI service, not an HTML startup page. Confirm the TLS certificate is trusted by the phone, and retry after a legitimate cold start if the free host is still waking. Do not increase timeouts or auto-replay checkout POSTs to hide a backend deployment failure. Continuous database readiness polling can consume the free PostgreSQL compute allowance; this is a deliberate deployment/session check.

## Rebuild, sync and verify the actual bundle

Use the existing project package manager, installed Node 22+ and JDK 21. On this workstation the existing ignored `android/.gradle/config.properties` records the portable JDK 21 path. Reuse it rather than Android Studio's incompatible bundled JBR 25:

```powershell
$taskJdkLine = Get-Content -LiteralPath 'android/.gradle/config.properties' | Where-Object { $_ -match '^java\.home=' } | Select-Object -First 1
if (-not $taskJdkLine) { throw 'Configure the installed JDK 21 path first.' }
$env:JAVA_HOME = $taskJdkLine.Substring('java.home='.Length)
$env:ANDROID_HOME = 'C:\Users\isran\AppData\Local\Android\Sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
& "$env:JAVA_HOME\bin\java.exe" -version

# This selects production frontend validation; Gradle still produces an installable DEBUG APK.
pnpm run build:student:android production
if ($LASTEXITCODE -ne 0) { throw 'Student Android frontend build failed.' }
pnpm exec cap sync android
if ($LASTEXITCODE -ne 0) { throw 'Capacitor sync failed.' }
node scripts/android-release-check.mjs
if ($LASTEXITCODE -ne 0) { throw 'Release backend/bundled asset verification failed.' }
node scripts/build-android-debug.mjs
if ($LASTEXITCODE -ne 0) { throw 'Android debug APK build failed.' }
node scripts/check-android.mjs --built --apk
if ($LASTEXITCODE -ne 0) { throw 'APK payload checks failed.' }
```

Do not use the convenience `pnpm run android:debug` command for this release-configuration step: it starts its own default staging frontend build. The explicit sequence above preserves the selected `production` URL policy. A frontend production mode does not turn a debug-signed APK into a store-ready signed release.

`android-release-check.mjs` checks the expected public API base appears in the compiled Student JavaScript, source/synced assets match, the native config has no `server.url`, and no placeholder backend or Admin login/Mess Management screen is packaged. Existing `check-android.mjs --built --apk` compares the actual APK payload with those assets and checks native resources/configuration. These checks do not replace an authenticated request or phone test.

Output remains:

`C:\Users\isran\Desktop\Canteen-Management-System\android\app\build\outputs\apk\debug\app-debug.apk`

Preserve the existing debug signing key when rebuilding; do not delete or replace it. Inspect signature and package metadata with the installed Android build tools before installation. Record the new APK SHA-256 with `Get-FileHash -Algorithm SHA256` so it is distinguishable from the old placeholder APK.

## Update the installed app safely

Transfer the new APK by USB and install it over the existing Canteen OS app, or enable USB debugging and authorize this workstation:

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices -l
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r 'C:\Users\isran\Desktop\Canteen-Management-System\android\app\build\outputs\apk\debug\app-debug.apk'
& "$env:ANDROID_HOME\platform-tools\adb.exe" shell am start -n com.canteenos.student/.MainActivity
```

Use `-s DEVICE_SERIAL` when more than one device is attached. Same application ID and signing key permit an update retaining app data. A signing mismatch requires review; do not automatically uninstall, erase phone data or delete backend users to solve it. Existing session tokens may expire or become invalid when changing backend environments; sign in to the correct staging/production account again.

## End-to-end acceptance after deployment

1. Confirm the backend-setup notice is absent and app opens its bundled Student UI; the APK must not navigate to a hosted frontend URL.
2. Sign in with an authorized test Student; reject wrong credentials and verify expired sessions return to sign-in without losing unrelated Admin state.
3. Load the actual menu, edit cart, create one authorized test order and inspect order history/tracking after refresh and backend restart. Confirm the server logs show the configured host and intended Student role without logging tokens.
4. Use only disabled payments or a verified provider sandbox; never fake payment capture or enable merchant live credentials as part of this connectivity test. Test order submission with a reviewed test payment/wallet balance that has no real settlement consequence.
5. Disconnect/reconnect mobile network, check graceful errors and retry behavior, and confirm no duplicate order after an uncertain network response. The free host may sleep between test sessions; its current cold-start limitation must be explained to testers.
6. Verify Admin sees the same test order and can update its status, and Android tracking reflects the persisted change. Both web builds and PWA isolation must still pass. Count/compare existing database data during cutover; installation is not permission to reset the database.

**Current boundary:** no deployed HTTPS URL has been provided or externally verified, so no new backend-connected APK or phone login/order success is claimed. Public provider accounts, service configuration, existing-data import validation and the actual public URL remain prerequisites. Store distribution/signing, a paid always-on deployment and a 500-student capacity test are separate later steps.
