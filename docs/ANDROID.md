# Canteen OS Android app

The Android app packages the existing React Student frontend using Capacitor 8. It does not open a Cloudflare tunnel or download the app shell from a website. The Admin Web and the shared FastAPI/PostgreSQL/Redis architecture are unchanged.

## Build configuration

| Item | Value |
| --- | --- |
| Application ID | `com.canteenos.student` |
| Display name | `Canteen OS` |
| Student web build | `pnpm run build:student` → `dist/student` |
| Admin web build | `pnpm run build:admin` → `dist/admin` |
| Android Student build | `pnpm run build:student:android` → `dist/student-android` |
| Android assets after sync | `android/app/src/main/assets/public` |
| Debug APK | `android/app/build/outputs/apk/debug/app-debug.apk` |
| Minimum Android version | Android 7.0 / API 24 |
| Compile / target SDK | API 36 |

The development build requires Node.js 22+, pnpm, JDK 21 and the Android SDK with platform API 36, build tools and platform tools. Configure `JAVA_HOME`, `ANDROID_HOME`, and a local `android/local.properties` with `sdk.dir` if Android Studio has not already done so. Keep machine-specific paths, signing keys and credentials out of Git. Gradle uses the checked-in wrapper; its first build needs access to dependency repositories.

On this workstation a portable JDK 21 was installed for the build. Android Studio's bundled JBR 25 must not replace it for this Gradle wrapper. The ignored `android/.gradle/config.properties` sets `java.home` to the installed JDK 21, and the ignored `android/.idea/gradle.xml` selects `#GRADLE_LOCAL_JAVA_HOME`. When opening/importing the project, confirm **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JDK** uses that JDK 21. On another machine, install JDK 21 and set the local path yourself; these files are deliberately not portable project configuration. Command-line builds also need `JAVA_HOME` pointing to JDK 21 and the corresponding Java `bin` directory on PATH.

## Public backend URL

The default **staging** APK uses `https://staging-api.canteenos.example`. This is a reserved documentation placeholder, not a deployed server. The UI displays a configuration notice and API calls show a clear configuration error. Login, menu, orders and tracking cannot be tested end to end until a real backend is deployed.

Set `CAPACITOR_API_BASE_URL` to the externally reachable HTTPS FastAPI **origin**, without a trailing `/api`; the existing client adds `/api/...`. This is public configuration, not a secret. Changing it requires rebuilding and reinstalling the APK.

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System'
$env:CAPACITOR_API_BASE_URL = 'https://api.your-owned-domain.tld'
pnpm run build:student:android staging
pnpm exec cap sync android
node scripts/build-android-debug.mjs
```

For development, use an externally reachable HTTPS development backend with a certificate trusted by the phone and replace `staging` with `development`. For production, use `production`; missing and documentation-placeholder URLs are rejected. Every Android mode rejects HTTP, localhost/loopback and private IP addresses, URL credentials/query strings/fragments and `*.trycloudflare.com` quick tunnels. A stable Cloudflare-managed domain can be used if it serves the deployed backend reliably over HTTPS.

Native builds force Bearer authentication, omit browser cookies and bypass PWA service-worker registration. Existing login/session-expiry/network error handling stays in place. JWTs are received after sign-in; no JWT signing secret or payment provider secret belongs in the APK. API requests use the configured backend directly; Vite's development proxy is not present inside the APK.

Capacitor serves the **bundled assets** under its internal `https://localhost` origin by default. This origin is not the API server. Configure the backend's explicit `CORS_ORIGINS` to include `https://localhost`, retain the existing Student/Admin web origins, and allow the existing Authorization, Content-Type and Idempotency-Key headers and required methods. Native authentication uses Bearer JWTs, so it does not require enabling Student cookie sessions for this origin. Configure `TRUSTED_HOSTS` for the backend's real hostname and use valid HTTPS certificates. No backend authentication relaxation is necessary.

## Build and sync

With prerequisites installed, the default placeholder APK can be built without deploying a backend:

```powershell
Set-Location 'C:\Users\isran\Desktop\Canteen-Management-System'
pnpm install --frozen-lockfile
pnpm run android:debug
node scripts/check-android.mjs --built --apk
```

`android:debug` builds the Student assets, runs Capacitor sync and invokes `assembleDebug`. For Android Studio, run `pnpm run android:open` or open the existing `android` folder as a project. Let Gradle sync complete, select the `app` module and the debug variant, then use **Build → Generate App Bundles or APKs → Generate APKs**. Menu wording can vary by Android Studio version. Run **Generate APKs**, rather than only the Run action, when producing an APK for manual transfer.

The exact expected output is:

`C:\Users\isran\Desktop\Canteen-Management-System\android\app\build\outputs\apk\debug\app-debug.apk`

The debug APK is automatically debug-signed and can be installed directly. It is not a production release or a Play Store submission. Keep production signing keys private and plan release signing/distribution separately.

## Transfer and install on a phone

### File transfer

1. Connect the Android phone using USB and select **File transfer**.
2. Copy `app-debug.apk` from the output path above into the phone's Downloads folder.
3. Open Downloads in the phone's file manager and tap the APK.
4. If prompted, allow **Install unknown apps** for that file manager only, then install. You may revoke that permission afterward.
5. Open **Canteen OS** from the launcher. With the default staging placeholder, expect the backend configuration notice; a real backend URL must be configured and the APK rebuilt before online features work.

### USB debugging / adb

Enable Developer options and USB debugging on the phone, connect USB, and approve the phone's computer authorization prompt. Then:

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r 'C:\Users\isran\Desktop\Canteen-Management-System\android\app\build\outputs\apk\debug\app-debug.apk'
& "$env:ANDROID_HOME\platform-tools\adb.exe" shell am start -n com.canteenos.student/.MainActivity
```

Use `-s DEVICE_SERIAL` when multiple devices are listed. Updating an existing installation requires the same signing key; a signature mismatch needs deliberate migration/uninstall, not an automatic destructive action. Updating the app should retain local state when using the same ID/signature. Do not uninstall merely to conceal a build problem.

## Verification boundaries and phone checklist

### Local results — 9 October 2026

- Debug APK build completed successfully using JDK 21 / Gradle 8.14.3 with the Student assets bundled locally. APK size: **4,093,961 bytes**.
- Independent Android QA: **13 checks passed**, including synced asset identity and actual APK ZIP payload inspection.
- Coordinator verification: TypeScript checks, both Student/Admin web builds and **22 separation/PWA checks passed**.
- Android build tools confirmed application ID `com.canteenos.student`, display name `Canteen OS`, minimum SDK 24, target SDK 36 and a valid v2 Android debug signature. This is a debuggable APK.
- APK SHA-256: `44549e601a03c06aaf28a49ded82019d16aeaeae718b07e7c253ea2caa18534a`.
- Android Studio was launched with the Android project path. Completed Studio UI import, emulator launch and physical phone installation have **not** been verified. No phone was connected.
- The APK uses the documented staging placeholder. Real login, menu, checkout, history/tracking and payment-provider interactions still require a deployed HTTPS backend and device testing.

`node scripts/check-android.mjs` checks URL validation, local bundle configuration, native Bearer mode, API paths, session expiry, network errors, manifest safety and the native/PWA registration boundary. `--built` compares synced assets to the built Student frontend. `--apk` additionally reads the APK ZIP, checks bundled HTML/JS/config against the built assets and prints its SHA-256. This proves packaging, not a successful launch or login on a physical device. APK secrets scanning is a bounded check for private files and common embedded secret patterns; all `VITE_*` values are public regardless of this check.

After deploying the backend and rebuilding, test on an actual phone:

- Launch Canteen OS: Student interface, existing beige/white/orange styling, icon/splash and readable system bars.
- Sign in with an existing test Student account; confirm rejected/expired sessions return to sign-in cleanly.
- Load the real menu, add/remove items, create an authorized test order and verify history/tracking after refresh.
- Inspect backend logs to confirm requests target the configured hostname and have the expected authenticated Student identity. Avoid logging tokens.
- Disable network and confirm useful error/retry states; re-enable it and confirm recovery without duplicate checkout.
- Test Android Back navigation, keyboard, safe areas and portrait/landscape layout on supported versions.
- Confirm Student PWA and Admin Web still build and behave independently.
- Exercise payment redirects/UPI apps only with provider test configuration and authorization; Capacitor packaging alone does not verify every payment flow.

No physical phone installation, emulator launch, real login/order or live payment is implied by a successful APK build. Record these separately when actually performed.

References: [Capacitor configuration](https://capacitorjs.com/docs/config), [Capacitor Android setup](https://capacitorjs.com/docs/android), [Android build and run documentation](https://developer.android.com/studio/run).
