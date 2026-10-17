// Runs the actual App, navigation controller, and Capacitor bridge with an isolated native mock.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const repo = path.resolve(__dirname, '..');
const ts = require(path.join(repo, 'node_modules/typescript'));
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const jsx = (type, props) => ({ type, props });
let passed = 0;
const check = async (name, test) => { await test(); passed++; console.log('PASS ' + name); };
function load(file, modules, globals = {}, extra = '') {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(repo, file), 'utf8') + extra, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText,
    { exports, require: name => name.endsWith('.css') ? {} : name === 'react/jsx-runtime' ? { jsx, jsxs: jsx } : name in modules ? modules[name] : (() => { throw Error('Unexpected import ' + name); })(), console, Promise, Symbol, ...globals }, { filename: file });
  return exports;
}
function nativeHarness({ native = true, delayed = false } = {}) {
  const handlers = new Set(), pending = deferred(); let exits = 0, registrations = 0, removals = 0;
  const App = {
    addListener: async (event, callback) => {
      assert.equal(event, 'backButton'); registrations++; handlers.add(callback);
      const handle = { remove: async () => { removals++; handlers.delete(callback); } };
      if (delayed) await pending.promise;
      return handle;
    },
    exitApp: async () => { exits++; },
  };
  const bridge = load('student/src/native.ts', { '@capacitor/core': { Capacitor: { isNativePlatform: () => native } }, '@capacitor/app': { App } });
  return { bridge, handlers, pending, press: () => { for (const callback of handlers) callback({ canGoBack: true }); }, get exits() { return exits; }, get registrations() { return registrations; }, get removals() { return removals; } };
}
function appHarness() {
  const groups = new Map(), effects = []; let group, cursor = 0, store;
  const begin = name => { if (!groups.has(name)) groups.set(name, []); group = groups.get(name); cursor = 0; };
  const react = {
    createContext: () => ({ Provider: 'Provider' }), useContext: () => store,
    useState: initial => { const i = cursor++; if (!group[i]) group[i] = { value: typeof initial === 'function' ? initial() : initial }; const slot = group[i]; return [slot.value, next => { slot.value = typeof next === 'function' ? next(slot.value) : next; }]; },
    useRef: current => { const i = cursor++; return group[i] ||= { current }; },
    useEffect: (run, deps) => { const i = cursor++, prior = group[i]; if (!prior || !deps || deps.some((value, j) => !Object.is(value, prior.deps[j]))) { const slot = group[i] = { deps, cleanup: prior?.cleanup }; effects.push(() => { prior?.cleanup?.(); slot.cleanup = run(); }); } },
  };
  const user = { id: 'test-student', name: 'Navigation QA', walletBalance: 200 };
  let requests = 0;
  const api = { hasSession: () => false, login: async () => ({ success: true, user }), getMe: async () => ({ success: true, user }), getMenu: async () => [{ id: 'food', name: 'Snack', price: 20, available: true }], getLunchMenu: async () => ({ mealType: 'lunch', options: [], contents: [], sabjiOptions: [] }), getDinnerMenu: async () => ({ mealType: 'dinner', options: [], contents: [], sabjiOptions: [] }), getOrders: async () => [], getNotifications: async () => [], getPaymentsConfig: async () => ({ enabled: false }), createOrder: async () => { requests++; throw Error('Back must never submit an order'); } };
  const native = nativeHarness();
  const app = load('student/src/App.tsx', { react, './navigation': load('student/src/navigation.ts', {}), './native': native.bridge,
    '../../src/lib/apiClient': { apiClient: api, STUDENT_SESSION_EXPIRED: 'expired' }, '../../src/lib/paymentCheckout': {}, '../../src/lib/studentLunch': load('src/lib/studentLunch.ts', {}), '../../src/lib/studentRush': load('src/lib/studentRush.ts', {}) },
    { setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {}, document: { visibilityState: 'visible' }, window: { addEventListener() {}, removeEventListener() {} } }, '\nexport { CheckoutScreen };');
  const commit = () => { while (effects.length) effects.shift()(); };
  const render = () => { begin('App'); store = app.default().props.value; commit(); return store; };
  const unmount = name => { for (const slot of groups.get(name) || []) slot?.cleanup?.(); groups.delete(name); };
  render();
  return { native, user, render, unmount, login: async () => { await render().loginUser('QA', 'private'); render(); await tick(); return render(); }, checkout: override => { render(); if (override) store = override; begin('Checkout'); const element = app.CheckoutScreen(); commit(); return element; }, setStore: next => { store = next; }, get requests() { return requests; } };
}
function nodes(element) { return !element || typeof element !== 'object' ? [] : Array.isArray(element) ? element.flatMap(nodes) : [element, ...nodes(element.props?.children)]; }
const text = element => typeof element === 'string' ? element : Array.isArray(element) ? element.map(text).join(' ') : element && typeof element === 'object' ? text(element.props?.children) : '';
(async () => {
  await check('Native Back follows actual Checkout → Cart → previous screen without reopening Checkout', async () => {
    const h = appHarness(); let s = await h.login(); s.go('menu'); s = h.render(); s.add(s.menu[0]); s.go('cart'); h.render().go('checkout');
    assert.equal(h.render().screen, 'checkout'); assert.equal(h.native.handlers.size, 1);
    h.native.press(); assert.equal(h.render().screen, 'cart'); await tick(); assert.equal(h.render().screen, 'cart');
    h.native.press(); assert.equal(h.render().screen, 'menu');
    assert.equal(h.render().cart.length, 1); assert.equal(h.render().user.walletBalance, 200); assert.equal(h.requests, 0);
    h.unmount('App'); await tick(); assert.equal(h.native.handlers.size, 0);
  });
  await check('Rapid native Back presses use synchronous latest navigation state', async () => {
    const h = appHarness(); await h.login(); h.render().go('cart'); h.render().go('checkout'); h.native.press(); h.native.press();
    assert.equal(h.render().screen, 'home'); assert.equal(h.native.exits, 0); h.native.press(); assert.equal(h.native.exits, 1); h.unmount('App');
  });
  await check('Checkout own Back arrow uses the same Cart path and preserves cart and sabji', async () => {
    const h = appHarness(); await h.login(); let s = h.render(); s.go('menu'); s.add(s.menu[0]); h.render().go('cart'); h.render().go('checkout');
    const before = JSON.stringify(h.render().cart); const top = nodes(h.checkout()).find(n => n.type?.name === 'TopBar'); top.props.onBack();
    assert.equal(h.render().screen, 'cart'); assert.equal(JSON.stringify(h.render().cart), before); assert.equal(h.requests, 0); h.unmount('Checkout'); h.unmount('App');
    const navigation = load('student/src/navigation.ts', {}).createStudentNavigation(() => {}); const variants = [{ sabjiChoice: 'Aloo', qty: 2 }]; navigation.reset('home'); navigation.go('cart'); navigation.go('checkout'); navigation.back(); assert.equal(variants[0].sabjiChoice, 'Aloo');
  });
  await check('Completed order navigation never returns to an old payment form', () => {
    const seen = []; const nav = load('student/src/navigation.ts', {}).createStudentNavigation(screen => seen.push(screen)); nav.reset('home'); nav.go('cart'); nav.go('checkout'); nav.go('confirm'); nav.back(); assert.equal(seen.at(-1), 'home');
  });
  await check('Payment completion after leaving Checkout cannot navigate away from Cart', async () => {
    const h = appHarness(); await h.login(); const result = deferred(); let submissions = 0;
    h.render().go('cart'); h.render().go('checkout');
    const s = h.render();
    const page = h.checkout({ ...s, cart: [{ key: 'food', item: { id: 'food', name: 'Snack', price: 20 }, qty: 1 }], cartTotal: 20,
      submitOrder: async () => { submissions++; return result.promise; } });
    const button = nodes(page).find(n => n.type?.name === 'Button' && /Pay .*place order/.test(text(n)));
    assert.ok(button, 'Checkout has an explicit submit button'); button.props.onClick(); assert.equal(submissions, 1);
    h.native.press(); assert.equal(h.render().screen, 'cart'); h.unmount('Checkout');
    result.resolve({ payment: 'Paid' }); await tick();
    assert.equal(h.render().screen, 'cart'); assert.equal(h.requests, 0); assert.equal(submissions, 1); h.unmount('App');
  });
  await check('Async native listener registration is removed after early cleanup', async () => {
    const h = nativeHarness({ delayed: true }); let back = 0; const cleanup = h.bridge.attachStudentNativeBack(() => { back++; return true; }); await tick(); cleanup(); h.press(); assert.equal(back, 0); h.pending.resolve(); await tick(); assert.equal(h.handlers.size, 0); assert.equal(h.removals, 1);
  });
  await check('StrictMode cleanup/remount leaves exactly one effective native callback', async () => {
    const h = nativeHarness(); let back = 0; const first = h.bridge.attachStudentNativeBack(() => { back++; return true; }); first(); const second = h.bridge.attachStudentNativeBack(() => { back++; return true; }); await tick(); assert.equal(h.handlers.size, 1); h.press(); assert.equal(back, 1); second(); await tick(); assert.equal(h.handlers.size, 0);
  });
  await check('Web/PWA navigation attaches no native listener and does not touch browser history', async () => {
    const h = nativeHarness({ native: false }); h.bridge.attachStudentNativeBack(() => false)(); await tick(); assert.equal(h.registrations, 0); assert.equal(h.exits, 0);
    const source = fs.readFileSync(path.join(repo, 'student/src/navigation.ts'), 'utf8'); assert.doesNotMatch(source, /window\.history|popstate|location\.reload|setTimeout/);
  });
  console.log(`${passed} Student navigation checks passed.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
