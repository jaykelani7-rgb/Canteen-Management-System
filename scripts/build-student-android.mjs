import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
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
  if (result.status === 0) {
    const assets = path.join(root, 'backend', 'food_assets');
    const manifest = JSON.parse(readFileSync(path.join(assets, 'manifest.json'), 'utf8'));
    const output = path.join(root, 'dist', 'student-android', 'food-library');
    mkdirSync(output, { recursive: true });
    for (const image of manifest.images) {
      if (!/^[a-z0-9-]+\.webp$/.test(image.filename)) throw new Error('Invalid bundled food photograph filename.');
      const source = path.join(assets, image.filename);
      const bytes = readFileSync(source);
      if (bytes.toString('ascii', 0, 4) !== 'RIFF' || createHash('sha256').update(bytes).digest('hex') !== image.sha256) {
        throw new Error('Bundled photograph is missing or differs from its licensed manifest. Fetch the reviewed asset before building.');
      }
      copyFileSync(source, path.join(output, image.filename));
    }
    for (const name of ['manifest.json', 'SOURCES.md']) copyFileSync(path.join(assets, name), path.join(output, name));
    console.info(`Bundled ${manifest.images.length} licensed food photographs and attribution records. Live image associations continue to come from the shared API.`);
  }
  process.exitCode = result.status ?? 1;
} catch (error) {
  console.error(error instanceof Error ? error.message : 'Android frontend build failed.');
  process.exitCode = 1;
}
