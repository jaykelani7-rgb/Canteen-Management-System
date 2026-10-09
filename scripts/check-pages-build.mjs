// Offline behavioural tests only. These fixtures do not represent deployed services or bypass a real build's health gate.
import assert from 'node:assert/strict';
import { pagesBuildConfig, verifyPagesBackend, pagesDeploymentMetadata } from './pages-build-config.mjs';

const variables = {
  VITE_API_BASE_URL: 'https://canteen-qa.onrender.com',
  VITE_STUDENT_APP_URL: 'https://canteen-student-qa.pages.dev',
  VITE_ADMIN_APP_URL: 'https://canteen-admin-qa.pages.dev',
};
let passed = 0;
const check = async (name, task) => { await task(); passed++; console.log('PASS ' + name); };

await check('All three explicit public origins are required', () => {
  for (const key of Object.keys(variables)) assert.throws(() => pagesBuildConfig({ ...variables, [key]: '' }), new RegExp(key));
});
await check('Unsafe API URLs are refused before a release Pages build', () => {
  for (const value of ['http://api.canteen.org', 'https://localhost', 'https://10.0.2.2', 'https://staging-api.canteenos.example', 'https://api.canteen.org/api', 'https://api.canteen.org/prefix', 'https://temporary.trycloudflare.com', 'https://user:private@api.canteen.org', 'https://api.canteen.org?key=private']) {
    assert.throws(() => pagesBuildConfig({ ...variables, VITE_API_BASE_URL: value }));
  }
});
await check('Unsafe Student and Admin web origins are also refused', () => {
  for (const key of ['VITE_STUDENT_APP_URL', 'VITE_ADMIN_APP_URL']) {
    for (const value of ['https://web.example', 'http://web.canteen.org', 'https://web.canteen.org/path', 'https://web.canteen.org#token', 'https://web.canteen.org?token=x', 'https://web.ngrok-free.app']) {
      assert.throws(() => pagesBuildConfig({ ...variables, [key]: value }));
    }
  }
});
await check('Distinct role origins are enforced and equivalent origins are normalized', () => {
  assert.throws(() => pagesBuildConfig({ ...variables, VITE_ADMIN_APP_URL: variables.VITE_STUDENT_APP_URL + '/' }));
  assert.throws(() => pagesBuildConfig({ ...variables, VITE_ADMIN_APP_URL: variables.VITE_API_BASE_URL }));
  assert.equal(pagesBuildConfig({ ...variables, VITE_API_BASE_URL: variables.VITE_API_BASE_URL.toUpperCase() + ':443/' }).apiBaseUrl, variables.VITE_API_BASE_URL);
});
await check('Existing web build outputs remain separate and inherited cookie/native settings are overridden', () => {
  const config = pagesBuildConfig({ ...variables, VITE_AUTH_COOKIE_MODE: 'true', VITE_NATIVE_APP: 'true' });
  assert.equal(config.variables.VITE_AUTH_COOKIE_MODE, 'false');
  assert.equal(config.variables.VITE_NATIVE_APP, 'false');
  assert.equal(config.variables.VITE_ANDROID_BACKEND_PLACEHOLDER, 'false');
  assert.deepEqual(config.builds.map(build => build.output), ['dist/student', 'dist/admin']);
  assert.ok(config.builds.every(build => !build.arguments.some(argument => argument.includes('android'))));
});
await check('Real-build gate requires exact health/readiness JSON and sends no credentials', async () => {
  const calls = [];
  const verified = await verifyPagesBackend(variables.VITE_API_BASE_URL, async (url, options) => {
    calls.push({ url, options });
    return { status: 200, json: async () => url.endsWith('/health') ? { status: 'alive' } : { status: 'ready', database: true, redis: true } };
  });
  assert.deepEqual(calls.map(call => call.url), [variables.VITE_API_BASE_URL + '/api/health', variables.VITE_API_BASE_URL + '/api/ready']);
  assert.ok(calls.every(call => call.options.credentials === 'omit' && call.options.redirect === 'error' && !call.options.headers.Authorization));
  assert.equal(verified.ready, true);
});
await check('A 200 HTML/startup response is not accepted as health', async () => {
  await assert.rejects(verifyPagesBackend(variables.VITE_API_BASE_URL, async () => ({ status: 200, json: async () => { throw new Error('HTML'); } })), /health/);
});
await check('HTTP failure or wrong health JSON stops before readiness', async () => {
  for (const response of [{ status: 503 }, { status: 200, json: async () => ({ status: 'ok' }) }]) {
    let count = 0;
    await assert.rejects(verifyPagesBackend(variables.VITE_API_BASE_URL, async () => { count++; return response; }), /health/);
    assert.equal(count, 1);
  }
});
await check('Unavailable database or Redis cannot certify a Pages build', async () => {
  for (const body of [{ status: 'ready', database: true, redis: false }, { status: 'ready', database: false, redis: true }, { status: 'ready', database: 'true', redis: true }, { status: 'alive', database: true, redis: true }]) {
    await assert.rejects(verifyPagesBackend(variables.VITE_API_BASE_URL, async url => ({ status: 200, json: async () => url.endsWith('/health') ? { status: 'alive' } : body })), /ready/);
  }
});
await check('Public metadata contains exact role/native CORS without secrets or wildcard', () => {
  const config = pagesBuildConfig(variables);
  const metadata = pagesDeploymentMetadata(config, { ready: true });
  assert.deepEqual(metadata.backendEnvironment.CORS_ORIGINS, [variables.VITE_STUDENT_APP_URL, variables.VITE_ADMIN_APP_URL, 'https://localhost']);
  assert.deepEqual(metadata.backendEnvironment.STUDENT_CORS_ORIGINS, [variables.VITE_STUDENT_APP_URL]);
  assert.deepEqual(metadata.backendEnvironment.ADMIN_CORS_ORIGINS, [variables.VITE_ADMIN_APP_URL]);
  assert.deepEqual(metadata.backendEnvironment.TRUSTED_HOSTS, ['canteen-qa.onrender.com', '127.0.0.1']);
  assert.doesNotMatch(JSON.stringify(metadata), /SECRET_KEY|DATABASE_URL|REDIS_URL|\*/);
});
console.log(`Pages build configuration: ${passed} offline checks passed. No build, cloud service, APK or database was changed.`);
