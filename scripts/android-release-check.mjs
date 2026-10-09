import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { androidBuildConfig } from './android-build-config.mjs';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
try {
  // This assertion intentionally refuses to bless an absent or placeholder URL.
  const config = androidBuildConfig('production', process.env);
  const built = path.join(repo, config.outDir);
  const synced = path.join(repo, 'android/app/src/main/assets/public');
  const nativeConfig = JSON.parse(fs.readFileSync(path.join(repo, 'android/app/src/main/assets/capacitor.config.json'), 'utf8'));
  assert.equal(nativeConfig.appId, 'com.canteenos.student');
  assert.equal(nativeConfig.server?.url, undefined, 'Native app must load bundled assets');
  const html = fs.readFileSync(path.join(built, 'index.html'), 'utf8');
  assert.equal(fs.readFileSync(path.join(synced, 'index.html'), 'utf8'), html, 'Run Capacitor sync after the new Student build');
  const entryScripts = [...html.matchAll(/<script\b[^>]*src="([^"]+)"/g)].map(match => match[1]);
  assert.ok(entryScripts.length > 0, 'Student HTML must reference its bundled entry');
  assert.ok(entryScripts.every(src => src.startsWith('/assets/')), 'App shell must reference local bundled scripts');
  let containsExpectedBase = false;
  for (const name of fs.readdirSync(path.join(built, 'assets'))) {
    if (!name.endsWith('.js')) continue;
    const content = fs.readFileSync(path.join(built, 'assets', name), 'utf8');
    assert.equal(fs.readFileSync(path.join(synced, 'assets', name), 'utf8'), content, 'Synced Student JS must match the current build');
    if (content.includes(config.apiBaseUrl)) containsExpectedBase = true;
    assert.doesNotMatch(content, /https:\/\/(?:[\w.-]+\.)?(?:example\.(?:com|org|net)|example|invalid|test)(?:[/:"']|$)|staging-api\.canteenos\.example|trycloudflare\.com|ngrok-free\.(?:app|dev)|localhost:8000|127\.0\.0\.1:8000|Admin Sign In|Mess Management/, 'Release bundle contains an unsafe backend or Admin screen');
  }
  assert.ok(containsExpectedBase, 'Expected backend base URL is not embedded in the current Student bundle');
  console.log('PASS bundled Student assets are synced and contain the configured public HTTPS API base: ' + config.apiBaseUrl);
  console.log('This offline check does not verify public health, login, payments or a phone installation.');
} catch (error) {
  console.error(error instanceof Error ? error.message : 'Android release configuration check failed.');
  process.exitCode = 1;
}
