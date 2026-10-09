import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { inflateRawSync } from 'node:zlib';
import { createHash } from 'node:crypto';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const ts = require('typescript');
const { androidBuildConfig, STAGING_API_PLACEHOLDER } = await import(pathToFileURL(path.join(repo, 'scripts/android-build-config.mjs')));
let passed = 0;
const check = async (name, test) => { await test(); passed++; console.log('PASS ' + name); };
const read = file => fs.readFileSync(path.join(repo, file), 'utf8');

function moduleHarness(file, env, extras = {}) {
  const exports = {};
  const context = { exports, __viteEnv: env, URL, setTimeout, clearTimeout, AbortController, FormData, ...extras };
  const source = read(file).replaceAll('import.meta.env', '__viteEnv');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, context, { filename: file });
  return exports;
}
function apiHarness(placeholder = false) {
  const stored = new Map([['sco_fastapi_student_token', 'test-student-session'], ['sco_fastapi_admin_token', 'test-admin-session']]);
  const calls = [], events = [];
  let response = async () => ({ ok: true, status: 200, json: async () => ({}) });
  const exports = moduleHarness('src/lib/apiClient.ts', { VITE_NATIVE_APP: 'true', VITE_AUTH_COOKIE_MODE: 'true', VITE_ANDROID_BACKEND_PLACEHOLDER: String(placeholder) }, {
    require: id => { assert.equal(id, './apiConfig'); return { apiUrl: suffix => 'https://api.canteen.test' + suffix }; },
    sessionStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key) },
    localStorage: { removeItem() {} }, window: { dispatchEvent: event => events.push(event) }, Event: class { constructor(type) { this.type = type; } },
    fetch: async (url, options) => { calls.push({ url, options }); return response(url, options); },
  });
  return { ...exports, stored, calls, events, respond: callback => { response = callback; } };
}
function zipEntries(filename) {
  const data = fs.readFileSync(filename);
  let end = -1;
  for (let i = data.length - 22; i >= Math.max(0, data.length - 65557); i--) if (data.readUInt32LE(i) === 0x06054b50) { end = i; break; }
  assert.ok(end >= 0, 'APK has no ZIP central directory');
  const result = new Map();
  let offset = data.readUInt32LE(end + 16);
  for (let i = 0; i < data.readUInt16LE(end + 10); i++) {
    assert.equal(data.readUInt32LE(offset), 0x02014b50);
    const method = data.readUInt16LE(offset + 10), size = data.readUInt32LE(offset + 20), rawSize = data.readUInt32LE(offset + 24);
    const nameLength = data.readUInt16LE(offset + 28), extraLength = data.readUInt16LE(offset + 30), commentLength = data.readUInt16LE(offset + 32);
    const name = data.subarray(offset + 46, offset + 46 + nameLength).toString('utf8');
    const local = data.readUInt32LE(offset + 42);
    const start = local + 30 + data.readUInt16LE(local + 26) + data.readUInt16LE(local + 28);
    result.set(name, () => {
      assert.ok(rawSize <= 64 * 1024 * 1024, 'Unexpectedly large APK entry');
      const payload = data.subarray(start, start + size);
      return method === 0 ? payload : (assert.equal(method, 8), inflateRawSync(payload, { maxOutputLength: 64 * 1024 * 1024 }));
    });
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return result;
}

await check('Staging builds use a clearly marked placeholder and a distinct Student output', () => {
  const config = androidBuildConfig(); assert.equal(config.apiBaseUrl, STAGING_API_PLACEHOLDER); assert.equal(config.placeholder, true); assert.equal(config.outDir, 'dist/student-android');
});
await check('Production requires an explicit real HTTPS backend', () => {
  assert.throws(() => androidBuildConfig('production'), /requires/i);
  assert.throws(() => androidBuildConfig('production', { CAPACITOR_API_BASE_URL: STAGING_API_PLACEHOLDER }), /placeholder/i);
  assert.equal(androidBuildConfig('production', { CAPACITOR_API_BASE_URL: 'https://api.canteen.edu/' }).apiBaseUrl, 'https://api.canteen.edu');
});
await check('Every Android environment rejects unsafe backend URLs', () => {
  const unsafe = ['http://api.canteen.edu', 'https://localhost', 'https://localhost.', 'https://127.0.0.1', 'https://[::1]', 'https://[::ffff:127.0.0.1]', 'https://10.0.2.2', 'https://192.168.1.10', 'https://172.16.1.10', 'https://169.254.1.1', 'https://temporary.trycloudflare.com', 'https://temporary.trycloudflare.com.', 'https://user:password@api.canteen.edu', 'https://api.canteen.edu/api', 'https://api.canteen.edu?token=secret', 'https://api.canteen.edu#fragment', 'not-a-url'];
  for (const environment of ['development', 'staging', 'production']) for (const url of unsafe) assert.throws(() => androidBuildConfig(environment, { CAPACITOR_API_BASE_URL: url }));
  assert.throws(() => androidBuildConfig('unexpected'));
});
await check('Capacitor points to bundled Student assets and has no remote app URL', () => {
  const config = moduleHarness('capacitor.config.ts', {}).default;
  assert.equal(config.appId, 'com.canteenos.student'); assert.equal(config.appName, 'Canteen OS'); assert.equal(config.webDir, 'dist/student-android');
  assert.equal(config.server?.url, undefined); assert.notEqual(config.android?.allowMixedContent, true);
});
await check('Android source manifest grants Internet without cleartext or backups', () => {
  const manifest = read('android/app/src/main/AndroidManifest.xml');
  const permissions = [...manifest.matchAll(/<uses-permission\b[^>]*android:name="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(permissions, ['android.permission.INTERNET']); assert.match(manifest, /android:usesCleartextTraffic="false"/); assert.match(manifest, /android:allowBackup="false"/);
  assert.match(read('android/app/build.gradle'), /applicationId\s+["']com\.canteenos\.student["']/);
  assert.match(read('android/app/src/main/res/values/strings.xml'), /<string name="app_name">Canteen OS<\/string>/);
});
await check('Native launches skip service worker registration while web PWA retains it', () => {
  for (const native of [true, false]) {
    let registered = 0, listeners = 0;
    moduleHarness('student/src/pwa.ts', { PROD: true, VITE_NATIVE_APP: String(native) }, {
      navigator: { serviceWorker: { register: async () => { registered++; }, ready: Promise.resolve() } },
      window: { isSecureContext: true, addEventListener: (_event, callback) => { listeners++; callback(); } }, console: { info() {}, warn() {} },
    }).registerStudentPwa();
    assert.equal(listeners, native ? 0 : 1); assert.equal(registered, native ? 0 : 1);
  }
});
await check('Native authentication uses Bearer JWT even when cookie env is accidentally enabled', async () => {
  const h = apiHarness(); assert.equal(h.usesStudentCookieSession, false);
  await h.apiClient.getMe(); assert.equal(h.calls[0].options.headers.Authorization, 'Bearer test-student-session'); assert.equal(h.calls[0].options.credentials, 'omit');
  h.respond(async () => ({ ok: true, status: 200, json: async () => ({ success: true, token: 'replacement', user: { id: 'student' } }) }));
  await h.apiClient.login('ROLL', 'PASS'); assert.equal(h.calls[1].options.headers['X-Session-Mode'], undefined); assert.equal(h.stored.get('sco_fastapi_student_token'), 'replacement');
});
await check('Native menu, checkout and tracking call the configured backend', async () => {
  const h = apiHarness(); await h.apiClient.getMenu(); await h.apiClient.createOrder([{ id: 'dish', qty: 1 }], 'wallet', 'qa-intent'); await h.apiClient.getTracking(12);
  assert.deepEqual(h.calls.map(call => call.url), ['https://api.canteen.test/api/menu/items', 'https://api.canteen.test/api/student/orders', 'https://api.canteen.test/api/student/orders/12/tracking']);
  assert.equal(h.calls[1].options.headers['Idempotency-Key'], 'qa-intent'); assert.equal(h.calls[0].options.headers.Authorization, undefined);
});
await check('API URL joining preserves explicit backend and normal web relative paths', () => {
  assert.equal(moduleHarness('src/lib/apiConfig.ts', { VITE_API_BASE_URL: 'https://api.canteen.edu/' }).apiUrl('/api/menu/items'), 'https://api.canteen.edu/api/menu/items');
  assert.equal(moduleHarness('src/lib/apiConfig.ts', {}).apiUrl('/api/menu/items'), '/api/menu/items');
});
await check('Placeholder APK shows an actionable error without contacting an imaginary backend', async () => {
  const h = apiHarness(true); await assert.rejects(h.apiClient.getMenu(), error => error.status === 0 && /backend is not configured/i.test(error.message)); assert.equal(h.calls.length, 0);
});
await check('Native expired sessions and failed networks preserve established error handling', async () => {
  const h = apiHarness(); h.respond(async () => ({ ok: false, status: 401, json: async () => ({ detail: 'Expired' }) }));
  await assert.rejects(h.apiClient.getMe(), error => error.status === 401); assert.equal(h.stored.has('sco_fastapi_student_token'), false); assert.equal(h.stored.get('sco_fastapi_admin_token'), 'test-admin-session'); assert.equal(h.events[0].type, 'sco:student-session-expired');
  h.respond(async () => { throw new Error('Network unavailable'); }); await assert.rejects(h.apiClient.getMenu(), error => error.status === 0 && /connection/i.test(error.message));
});

if (process.argv.includes('--built') || process.argv.includes('--apk')) {
  await check('Synced assets match the production-built Student frontend', () => {
    const config = JSON.parse(read('android/app/src/main/assets/capacitor.config.json')); assert.equal(config.server?.url, undefined); assert.equal(config.appId, 'com.canteenos.student');
    const html = read('dist/student-android/index.html'); assert.equal(read('android/app/src/main/assets/public/index.html'), html);
    const scripts = [...html.matchAll(/<script\b[^>]*src="([^"]+)"/g)].map(match => match[1]); assert.ok(scripts.length > 0);
    for (const script of scripts) {
      const file = script.replace(/^\//, ''); const content = read('dist/student-android/' + file); assert.equal(read('android/app/src/main/assets/public/' + file), content);
      assert.doesNotMatch(content, /trycloudflare\.com|localhost:8000|127\.0\.0\.1:8000|Admin Sign In|Mess Management/);
    }
  });
}
if (process.argv.includes('--apk')) {
  const apk = path.join(repo, 'android/app/build/outputs/apk/debug/app-debug.apk'); const entries = zipEntries(apk);
  await check('APK packages the actual Student frontend and native resources', () => {
    assert.ok(entries.has('AndroidManifest.xml')); assert.ok(entries.has('classes.dex')); assert.ok(entries.has('resources.arsc'));
    const config = JSON.parse(entries.get('assets/capacitor.config.json')().toString()); assert.equal(config.appId, 'com.canteenos.student'); assert.equal(config.server?.url, undefined);
    assert.equal(entries.get('assets/public/index.html')().toString(), read('dist/student-android/index.html'));
    for (const [name, content] of entries) {
      assert.doesNotMatch(name, /(?:^|\/)\.env(?:\.|$)|(?:^|\/)local\.properties$|\.(?:pem|key|jks|keystore|dump)$/i, 'Private configuration must not be embedded');
      if (name.startsWith('assets/public/assets/') && name.endsWith('.js')) {
        const payload = content().toString(); assert.doesNotMatch(payload, /trycloudflare\.com|localhost:8000|127\.0\.0\.1:8000|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|\bsk_(?:live|test)_[A-Za-z0-9]{16,}/);
        assert.equal(payload, read('dist/student-android/' + name.slice('assets/public/'.length)));
      }
    }
  });
  console.log('APK SHA-256: ' + createHash('sha256').update(fs.readFileSync(apk)).digest('hex'));
}
console.log('Android QA checks passed: ' + passed);
