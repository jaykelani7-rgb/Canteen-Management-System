const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const repo = process.argv[2] && !process.argv[2].startsWith('--') ? path.resolve(process.argv[2]) : path.resolve(__dirname, '..');
const ts = require(path.join(repo, 'node_modules/typescript'));
let passed = 0;
const check = (name, fn) => Promise.resolve().then(fn).then(() => { passed++; console.log('PASS ' + name); });

function makeStorage(seed = {}) {
  const data = new Map(Object.entries(seed));
  return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: k => data.delete(k), data };
}
function apiHarness(file) {
  const sessionStorage = makeStorage({ sco_fastapi_student_token: 'student-session', sco_fastapi_admin_token: 'admin-session' });
  const localStorage = makeStorage({ sco_auth_token: 'legacy-mock-token', sco_auth_user: 'legacy-profile' });
  const events = [], calls = [];
  let responder = async () => ({ ok: true, status: 200, json: async () => ({}) });
  const exports = {};
  const ctx = vm.createContext({
    exports, require: id => { assert.equal(id, './apiConfig'); return { apiUrl: p => p }; },
    sessionStorage, localStorage, window: { dispatchEvent: e => events.push(e), addEventListener() {}, removeEventListener() {} },
    Event: class Event { constructor(type) { this.type = type; } }, CustomEvent: class CustomEvent { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    AbortController, AbortSignal, setTimeout, clearTimeout,
    fetch: async (url, options) => { calls.push({ url, options }); return responder(url, options); },
  });
  const code = ts.transpileModule(fs.readFileSync(path.join(repo, file), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInContext(code, ctx, { filename: file });
  return { exports, sessionStorage, localStorage, events, calls, respond: fn => { responder = fn; } };
}
function workerHarness() {
  const handlers = {}, matches = [], fetched = [], deleted = [], added = [];
  let failNetwork = false;
  const offline = { marker: 'public-offline-document' }, publicAsset = { marker: 'public-hashed-asset' };
  const assets = ['/offline.html', '/assets/index-a1b2c3.js', '/icons/icon-192.png'];
  const code = fs.readFileSync(path.join(repo, 'student/public/sw.js'), 'utf8').replace('/* PRECACHE_ASSETS */ []', JSON.stringify(assets));
  const context = {
    URL, Set, Promise,
    self: { location: { origin: 'http://localhost:5173' }, addEventListener: (name, fn) => { handlers[name] = fn; }, skipWaiting: async () => {}, clients: { claim: async () => {} } },
    caches: { open: async () => ({ addAll: async list => added.push(...list) }), keys: async () => ['student-static-obsolete', 'unrelated-cache'], delete: async k => deleted.push(k), match: async key => { matches.push(key); return key === '/offline.html' ? offline : key === '/assets/index-a1b2c3.js' ? publicAsset : undefined; } },
    fetch: async request => { fetched.push(request.url); if (failNetwork) throw Error('network unavailable'); return { marker: 'fresh-network-response' }; },
  };
  vm.runInNewContext(code, context, { filename: 'student/public/sw.js' });
  function request(url, options = {}) {
    let response;
    handlers.fetch({ request: { url, method: options.method || 'GET', mode: options.mode || 'cors', headers: { has: name => Boolean(options.authorization && name === 'Authorization') } }, respondWith: promise => { response = promise; } });
    return response;
  }
  return { handlers, matches, fetched, deleted, added, offline, publicAsset, request, fail: () => { failNetwork = true; } };
}

function importGraph(entry) {
  const files = new Set();
  function visit(file) {
    if (files.has(file)) return;
    files.add(file);
    const src = fs.readFileSync(file, 'utf8');
    const ast = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true);
    ast.forEachChild(node => {
      if (!ts.isImportDeclaration(node) && !ts.isExportDeclaration(node)) return;
      if (!node.moduleSpecifier || !ts.isStringLiteral(node.moduleSpecifier)) return;
      if (node.importClause?.isTypeOnly) return;
      const spec = node.moduleSpecifier.text;
      if (!spec.startsWith('.')) return;
      const base = path.resolve(path.dirname(file), spec);
      const found = [base, ...['.ts', '.tsx', '.js', '.jsx'].map(ext => base + ext), path.join(base, 'index.ts'), path.join(base, 'index.tsx')].find(f => fs.existsSync(f) && fs.statSync(f).isFile());
      if (!found) throw Error('Unresolved import: ' + spec + ' from ' + path.relative(repo, file));
      if (/\.[jt]sx?$/.test(found)) visit(found);
    });
  }
  visit(path.join(repo, entry));
  return [...files].map(f => path.relative(repo, f).replace(/\\/g, '/'));
}

(async () => {
  await check('Student login uses student API, removes legacy fallback and preserves admin session', async () => {
    const h = apiHarness('src/lib/apiClient.ts');
    h.respond(async () => ({ ok: true, status: 200, json: async () => ({ success: true, token: 'fresh-student', user: { id: 'student-1' } }) }));
    assert.equal((await h.exports.apiClient.login('ROLL', 'PASS')).success, true);
    assert.equal(h.calls[0].url, '/api/auth/login');
    assert.equal(h.calls[0].options.headers.Authorization, undefined);
    assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), 'fresh-student');
    assert.equal(h.sessionStorage.getItem('sco_fastapi_admin_token'), 'admin-session');
    assert.equal(h.localStorage.getItem('sco_auth_user'), null);
  });
  await check('Student API rejection invalidates only student JWT and never falls back to cached user', async () => {
    const h = apiHarness('src/lib/apiClient.ts');
    h.respond(async () => ({ ok: false, status: 401, json: async () => ({ detail: 'Expired' }) }));
    await assert.rejects(h.exports.apiClient.getMe(), e => e.status === 401);
    assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), null);
    assert.equal(h.sessionStorage.getItem('sco_fastapi_admin_token'), 'admin-session');
    assert.equal(h.events[0].type, 'sco:student-session-expired');
  });
  await check('Old student request cannot clear a replacement student session', async () => {
    const h = apiHarness('src/lib/apiClient.ts');
    h.respond(async () => { h.sessionStorage.setItem('sco_fastapi_student_token', 'replacement'); return { ok: false, status: 401, json: async () => ({ detail: 'Old session expired' }) }; });
    await assert.rejects(h.exports.apiClient.getMe());
    assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), 'replacement');
    assert.equal(h.events.length, 0);
  });
  await check('Student public menu sends no JWT and requests never use HTTP cache', async () => {
    const h = apiHarness('src/lib/apiClient.ts'); await h.exports.apiClient.getMenu();
    assert.equal(h.calls[0].url, '/api/menu/items'); assert.equal(h.calls[0].options.headers.Authorization, undefined); assert.equal(h.calls[0].options.cache, 'no-store');
  });
  await check('Admin rejection invalidates only admin JWT and preserves student session', async () => {
    const h = apiHarness('src/lib/adminApi.ts');
    h.respond(async () => ({ ok: false, status: 403, json: async () => ({ detail: 'Disabled' }) }));
    await assert.rejects(h.exports.getAdminMe(), e => e.status === 403);
    assert.equal(h.sessionStorage.getItem('sco_fastapi_admin_token'), null); assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), 'student-session');
    assert.equal(h.calls[0].options.headers.Authorization, 'Bearer admin-session');
  });
  await check('Old admin request cannot clear a replacement admin session', async () => {
    const h = apiHarness('src/lib/adminApi.ts');
    h.respond(async () => { h.sessionStorage.setItem('sco_fastapi_admin_token', 'replacement'); return { ok: false, status: 401, json: async () => ({ detail: 'Expired' }) }; });
    await assert.rejects(h.exports.getAdminMe()); assert.equal(h.sessionStorage.getItem('sco_fastapi_admin_token'), 'replacement'); assert.equal(h.events.length, 0);
  });
  await check('Student logout clears only student authentication', async () => {
    const h = apiHarness('src/lib/apiClient.ts'); await h.exports.apiClient.logout(); assert.equal(h.calls[0].url, '/api/auth/logout'); assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), null); assert.equal(h.sessionStorage.getItem('sco_fastapi_admin_token'), 'admin-session');
  });
  await check('Pending logout clears JWT immediately and cannot erase a fresh login', async () => {
    const h = apiHarness('src/lib/apiClient.ts'); let resolve;
    h.respond(() => new Promise(r => { resolve = r; })); const pending = h.exports.apiClient.logout();
    assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), null);
    h.sessionStorage.setItem('sco_fastapi_student_token', 'replacement-login');
    resolve({ ok: true, status: 200, json: async () => ({ success: true }) }); await pending;
    assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), 'replacement-login');
  });
  await check('Admin logout clears only admin authentication', () => {
    const h = apiHarness('src/lib/adminApi.ts'); h.exports.adminLogout(); assert.equal(h.sessionStorage.getItem('sco_fastapi_admin_token'), null); assert.equal(h.sessionStorage.getItem('sco_fastapi_student_token'), 'student-session');
  });
  await check('SW bypasses API paths, POSTs, cross-origin and authorized requests', async () => {
    const h = workerHarness();
    for (const [url, opts] of [['http://localhost:5173/api', {}], ['http://localhost:5173/api/student/wallet', {}], ['http://localhost:5173/api/auth/login', { method: 'POST' }], ['https://backend.example/api/student/orders', {}], ['http://localhost:5173/assets/index-a1b2c3.js', { authorization: true }]]) assert.equal(h.request(url, opts), undefined);
    assert.equal(h.matches.length, 0); assert.equal(h.fetched.length, 0);
  });
  await check('SW serves only explicit public assets and ignores arbitrary user URLs', async () => {
    const h = workerHarness(); assert.equal(await h.request('http://localhost:5173/assets/index-a1b2c3.js'), h.publicAsset);
    assert.equal(h.request('http://localhost:5173/profile.json'), undefined); assert.equal(h.request('http://localhost:5173/assets/user-history.json'), undefined);
  });
  await check('Offline navigation uses generic offline page, never cached user UI/data', async () => {
    const h = workerHarness(); h.fail(); assert.equal(await h.request('http://localhost:5173/profile', { mode: 'navigate' }), h.offline); assert.deepEqual(h.matches, ['/offline.html']);
    const html = fs.readFileSync(path.join(repo, 'student/public/offline.html'), 'utf8'); assert.match(html, /offline/i); assert.doesNotMatch(html, /localStorage|sessionStorage|walletBalance|token/i);
  });
  await check('SW cache cleanup affects only obsolete student-static caches', async () => {
    const h = workerHarness(); let pending; h.handlers.activate({ waitUntil: p => { pending = p; } }); await pending; assert.deepEqual(h.deleted, ['student-static-obsolete']);
  });
  await check('Student manifest has standalone metadata and valid 192/512 PNG icons', () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(repo, 'student/public/manifest.webmanifest'), 'utf8'));
    assert.equal(manifest.name, 'Smart Canteen'); assert.equal(manifest.short_name, 'Canteen'); assert.equal(manifest.display, 'standalone'); assert.equal(manifest.start_url, '/'); assert.equal(manifest.scope, '/');
    for (const pixels of [192, 512]) {
      const icon = manifest.icons.find(i => i.sizes === `${pixels}x${pixels}`); assert.ok(icon); const png = fs.readFileSync(path.join(repo, 'student/public', icon.src));
      assert.equal(png.subarray(1, 4).toString(), 'PNG'); assert.equal(png.readUInt32BE(16), pixels); assert.equal(png.readUInt32BE(20), pixels);
    }
  });
  if (process.argv.includes('--built')) await check('Built service worker precaches only existing public shell and generated static assets', async () => {
    const sw = fs.readFileSync(path.join(repo, 'dist/student/sw.js'), 'utf8'); assert.doesNotMatch(sw, /\/\* PRECACHE_ASSETS \*\//);
    const assets = JSON.parse(sw.match(/const PRECACHE_ASSETS = (\[[^\n]+\]);/)[1]); assert.ok(assets.some(p => p.startsWith('/assets/')));
    for (const asset of assets) { assert.doesNotMatch(asset, /^\/api(?:\/|$)|auth|orders|wallet|profile/); assert.ok(fs.existsSync(path.join(repo, 'dist/student', asset === '/' ? '/index.html' : asset)), asset + ' missing from build'); }
    assert.ok(assets.includes('/offline.html'));
  });
  if (!process.argv.includes('--skip-graph')) {
    await check('Student dependency graph excludes admin and prototype auth modules', () => {
      const graph = importGraph('student/src/main.tsx'); const bad = graph.filter(f => /Admin|Mess|messApi|adminApi|server\/auth|server\/db|apiMiddleware/.test(f)); assert.deepEqual(bad, []); console.log('Student modules: ' + graph.length);
    });
    await check('Admin dependency graph excludes student entry and prototype auth modules', () => {
      const graph = importGraph('src/main.tsx'); const bad = graph.filter(f => /^student\/|studentTypes|apiClient|server\/auth|server\/db|apiMiddleware/.test(f)); assert.deepEqual(bad, []); console.log('Admin modules: ' + graph.length);
    });
  }
  console.log('QA checks passed: ' + passed);
})().catch(error => { console.error(error); process.exitCode = 1; });
