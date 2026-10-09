import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { androidBuildConfig } from './android-build-config.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
try {
  if (process.argv.length > 3) throw new Error('Usage: node scripts/build-student-android.mjs [development|staging|production]');
  const config = androidBuildConfig(process.argv[2] || 'staging', process.env);
  console.info(`Building bundled Student frontend for Android (${config.environment}).`);
  if (config.placeholder) console.warn('Backend is not configured: the APK will show a staging notice. Login and ordering require a deployed backend.');
  const vite = path.join(root, 'node_modules', 'vite', 'bin', 'vite.js');
  const result = spawnSync(process.execPath, [vite, 'build', '--config', 'vite.student.config.ts', '--mode', config.mode], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, CAPACITOR_API_BASE_URL: config.apiBaseUrl, VITE_API_BASE_URL: config.apiBaseUrl, VITE_AUTH_COOKIE_MODE: 'false', VITE_NATIVE_APP: 'true', VITE_ANDROID_BACKEND_PLACEHOLDER: String(config.placeholder) },
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} catch (error) {
  console.error(error instanceof Error ? error.message : 'Android frontend build failed.');
  process.exitCode = 1;
}
