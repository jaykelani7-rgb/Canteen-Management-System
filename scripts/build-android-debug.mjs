import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const windows = process.platform === 'win32';
const command = windows ? 'gradlew.bat' : 'sh';
const args = windows ? ['--no-daemon', 'assembleDebug'] : ['./gradlew', '--no-daemon', 'assembleDebug'];
const result = spawnSync(command, args, {
  cwd: path.join(root, 'android'),
  stdio: 'inherit',
  shell: process.platform === 'win32',
});
if (result.error) {
  console.error(`Android build failed: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) process.exit(result.status ?? 1);
console.log('Debug APK: android/app/build/outputs/apk/debug/app-debug.apk');
