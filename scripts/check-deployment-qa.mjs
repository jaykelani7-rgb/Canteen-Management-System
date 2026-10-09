// Offline behavioural QA: synthetic tokens/URLs only; no real network or secrets.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { androidBuildConfig } from './android-build-config.mjs';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ts = createRequire(import.meta.url)('typescript');
let passed = 0;
const check = async (name, task) => { await task(); passed++; console.log('PASS ' + name); };

function harness(file, env, modules = {}) {
  const storage = new Map([['sco_fastapi_student_token', 'synthetic-student'], ['sco_fastapi_admin_token', 'synthetic-admin']]);
  const calls = [];
  const module = { exports: {} };
  const source = fs.readFileSync(path.join(repo, file), 'utf8').replaceAll('import.meta.env', '__viteEnv');
  const context = {
    exports: module.exports, module, __viteEnv: env,
    require: name => { if (name in modules) return modules[name]; assert.equal(name, './apiConfig'); return { apiUrl: suffix => 'https://canteen-fixture.onrender.com' + suffix }; },
    sessionStorage: { getItem: name => storage.get(name) ?? null, setItem: (name, value) => storage.set(name, value), removeItem: name => storage.delete(name) },
    localStorage: { removeItem() {} }, FormData, AbortController, AbortSignal, setTimeout, clearTimeout,
    window: { dispatchEvent() {}, addEventListener() {}, removeEventListener() {} },
    Event: class { constructor(type) { this.type = type; } }, CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, status: 200, json: async () => ({}) }; },
  };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, context, { filename: file });
  return { ...module.exports, calls };
}

await check('Student web Bearer works across provider origins without cookies', async () => {
  const student = harness('src/lib/apiClient.ts', { VITE_NATIVE_APP: 'false', VITE_AUTH_COOKIE_MODE: 'false' });
  await student.apiClient.getOrders();
  const call = student.calls[0];
  assert.equal(call.url, 'https://canteen-fixture.onrender.com/api/student/orders');
  assert.equal(call.options.credentials, 'omit');
  assert.equal(call.options.headers.Authorization, 'Bearer synthetic-student');
  assert.equal(call.options.headers['X-Session-Mode'], undefined);
});
await check('Admin web Bearer works across provider origins without cookies', async () => {
  const admin = harness('src/lib/adminApi.ts', { VITE_AUTH_COOKIE_MODE: 'false' });
  await admin.adminRequest('/me');
  const call = admin.calls[0];
  assert.equal(call.url, 'https://canteen-fixture.onrender.com/api/admin/me');
  assert.equal(call.options.credentials, 'omit');
  assert.equal(call.options.headers.Authorization, 'Bearer synthetic-admin');
});
await check('Weekly Schedule uses the configured credential mode across provider origins', async () => {
  for (const cookieMode of ['false', 'true']) {
    const env = { VITE_AUTH_COOKIE_MODE: cookieMode };
    const admin = harness('src/lib/adminApi.ts', env);
    const operations = harness('src/lib/adminOperationsApi.ts', env, { './adminApi': admin });
    await operations.adminOperationsApi.weeklyMenu();
    const call = operations.calls[0];
    assert.equal(call.url, 'https://canteen-fixture.onrender.com/api/menu/weekly');
    assert.equal(call.options.credentials, cookieMode === 'true' ? 'include' : 'omit');
    assert.equal(call.options.headers?.Authorization, undefined);
  }
});

await check('Same-site web cookie configuration includes credentials, no Bearer token', async () => {
  const student = harness('src/lib/apiClient.ts', { VITE_NATIVE_APP: 'false', VITE_AUTH_COOKIE_MODE: 'true' });
  await student.apiClient.getOrders();
  assert.equal(student.calls[0].options.credentials, 'include');
  assert.equal(student.calls[0].options.headers.Authorization, undefined);
  const admin = harness('src/lib/adminApi.ts', { VITE_AUTH_COOKIE_MODE: 'true' });
  await admin.adminRequest('/me');
  assert.equal(admin.calls[0].options.credentials, 'include');
  assert.equal(admin.calls[0].options.headers.Authorization, undefined);
});
await check('Packaged Android enforces Bearer even if inherited web cookie flag is true', async () => {
  const student = harness('src/lib/apiClient.ts', { VITE_NATIVE_APP: 'true', VITE_AUTH_COOKIE_MODE: 'true', VITE_ANDROID_BACKEND_PLACEHOLDER: 'false' });
  await student.apiClient.getOrders();
  assert.equal(student.calls[0].options.credentials, 'omit');
  assert.equal(student.calls[0].options.headers.Authorization, 'Bearer synthetic-student');
});
await check('Release configuration rejects placeholders, tunnels, loopback and malformed bases', () => {
  const rejected = ['https://staging-api.canteenos.example', 'https://localhost', 'http://api.canteen.org',
    'https://api.canteen.org/api', 'https://temporary.trycloudflare.com', 'https://10.0.2.2',
    'https://user:password@api.canteen.org', 'https://api.canteen.org?token=synthetic'];
  for (const url of rejected) assert.throws(() => androidBuildConfig('production', { CAPACITOR_API_BASE_URL: url }));
  assert.throws(() => androidBuildConfig('production', {}));
});
await check('Stable HTTPS release URL remains public configuration and targets Student assets', () => {
  const result = androidBuildConfig('production', { CAPACITOR_API_BASE_URL: 'https://canteen-fixture.onrender.com/' });
  assert.equal(result.apiBaseUrl, 'https://canteen-fixture.onrender.com');
  assert.equal(result.placeholder, false);
  assert.equal(result.outDir, 'dist/student-android');
});
console.log(`Deployment QA: ${passed} offline behavioural checks passed. No deployment, real account, secret or database mutation was performed.`);
