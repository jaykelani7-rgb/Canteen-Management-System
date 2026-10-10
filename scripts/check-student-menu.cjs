// Focused behavioural checks execute the actual Student App and shared image component.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const repo = path.resolve(__dirname, '..');
const ts = require(path.join(repo, 'node_modules/typescript'));
let passed = 0;
const check = async (name, run) => { await run(); passed++; console.log('PASS ' + name); };
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

function hooks() {
  const groups = new Map(), effects = [], intervals = new Map();
  let group, cursor = 0, timer = 0;
  const begin = key => { if (!groups.has(key)) groups.set(key, []); group = groups.get(key); cursor = 0; };
  const react = {
    createContext: () => ({ Provider: 'Provider' }), useContext: () => runtime.store,
    useState: value => { const index = cursor++; if (!group[index]) group[index] = { value: typeof value === 'function' ? value() : value }; const slot = group[index]; return [slot.value, next => { slot.value = typeof next === 'function' ? next(slot.value) : next; }]; },
    useRef: value => { const index = cursor++; return group[index] ||= { current: value }; },
    useEffect: (run, deps) => { const index = cursor++, prior = group[index]; if (!prior || !deps || deps.some((value, i) => !Object.is(value, prior.deps[i]))) { group[index] = { deps, cleanup: prior?.cleanup }; effects.push(() => { prior?.cleanup?.(); group[index].cleanup = run(); }); } },
  };
  const runtime = { react, store: null, begin, commit: () => { while (effects.length) effects.shift()(); }, intervals,
    setInterval: callback => { const id = ++timer; intervals.set(id, callback); return id; }, clearInterval: id => intervals.delete(id) };
  return runtime;
}
const jsx = (type, props) => ({ type, props });
function load(file, modules, globals = {}, extra = '') {
  const source = fs.readFileSync(path.join(repo, file), 'utf8') + extra;
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText,
    { exports, require: name => { if (name.endsWith('.css')) return {}; if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx }; if (!(name in modules)) throw Error('Unexpected import ' + name); return modules[name]; }, URL, Error, Promise, Symbol, console, ...globals }, { filename: file });
  return exports;
}
function nodes(element) {
  if (!element || typeof element !== 'object') return [];
  if (Array.isArray(element)) return element.flatMap(nodes);
  return [element, ...nodes(element.props?.children)];
}
const text = element => {
  if (typeof element === 'string' || typeof element === 'number') return String(element);
  if (Array.isArray(element)) return element.map(text).join(' ');
  return element && typeof element === 'object' ? text(element.props?.children) : '';
};
const meal = { id: 'meal', name: 'Dosa', desc: 'South Dish', category: 'Meals', price: 40, photo: '', rating: 0, available: true, veg: true, emoji: '🍽️', prepMins: 10 };

function appHarness(overrides = {}) {
  const runtime = hooks(), user = { id: 'student-a', name: 'Student' };
  const api = { hasSession: () => false, getMenu: async () => [meal], getOrders: async () => [], getNotifications: async () => [], getMe: async () => ({ success: true, user }), login: async () => ({ success: true, user }), logout: async () => {}, ...overrides };
  const app = load('student/src/App.tsx', {
    react: runtime.react, '../../src/lib/apiClient': { apiClient: api, STUDENT_SESSION_EXPIRED: 'expired' },
    '../../src/lib/paymentCheckout': {}, '../../src/components/FoodImage': { default: function FoodImage() {} },
  }, { setTimeout: () => 1, clearTimeout() {}, setInterval: runtime.setInterval, clearInterval: runtime.clearInterval,
    document: { visibilityState: 'visible' }, window: { addEventListener() {}, removeEventListener() {} } }, '\nexport { HomeScreen, MenuScreen };');
  function render() { runtime.begin('App'); runtime.store = app.default().props.value; runtime.commit(); return runtime.store; }
  const mounted = { app, api, runtime, render, login: async () => { await render().loginUser('ROLL', 'PASS'); render(); await tick(); return render(); } };
  render(); return mounted;
}

(async () => {
  const resolver = load('src/lib/foodImageSource.ts', {}).foodImageSource;
  await check('Safe images accept HTTPS/local assets and reject empty, malformed and unsafe sources', () => {
    assert.equal(resolver(' https://images.canteen.edu/dosa.jpg '), 'https://images.canteen.edu/dosa.jpg');
    assert.equal(resolver('/icons/icon-192.png'), '/icons/icon-192.png');
    for (const value of [null, '', '  ', 'not an image', 'javascript:alert(1)', 'http://images.canteen.edu/a', '//foreign.site/photo', '/\\foreign.site/photo', 'https://user:password@images.canteen.edu/a', '/bad\u0000.jpg']) assert.equal(resolver(value), null);
  });
  await check('Missing/failed images use neutral accessible fallback; valid/replaced images recover', () => {
    const runtime = hooks();
    const component = load('src/components/FoodImage.tsx', { react: runtime.react, '../lib/foodImageSource': { foodImageSource: resolver } }).default;
    let currentSource, attempt = 0;
    const render = src => { const entry = component({ src, alt: 'Dosa' }); if (entry.props.source !== currentSource) { currentSource = entry.props.source; attempt++; } runtime.begin('FoodImageAttempt-' + attempt); return entry.type(entry.props); };
    let view = render(''); assert.equal(nodes(view).filter(node => node.type === 'img').length, 0); assert.equal(view.props.role, 'img'); assert.match(view.props['aria-label'], /photo unavailable/);
    view = render('https://images.canteen.edu/dosa.jpg'); let image = nodes(view).find(node => node.type === 'img'); assert.equal(image.props.alt, ''); assert.match(image.props.className, /opacity-0/);
    image.props.onLoad(); view = render('https://images.canteen.edu/dosa.jpg'); assert.equal(view.props['aria-label'], 'Dosa');
    nodes(view).find(node => node.type === 'img').props.onError(); view = render('https://images.canteen.edu/dosa.jpg'); assert.equal(nodes(view).filter(node => node.type === 'img').length, 0);
    view = render('https://images.canteen.edu/new-dosa.jpg'); assert.ok(nodes(view).some(node => node.type === 'img'));
  });
  await check('Returning to loaded or failed image URLs starts a fresh hidden attempt; stale events cannot affect it', () => {
    const runtime = hooks();
    const component = load('src/components/FoodImage.tsx', { react: runtime.react, '../lib/foodImageSource': { foodImageSource: resolver } }).default;
    let currentSource, attempt = 0;
    const render = src => { const entry = component({ src, alt: 'Dosa' }); if (entry.props.source !== currentSource) { currentSource = entry.props.source; attempt++; } runtime.begin('FoodImageAttempt-' + attempt); return entry.type(entry.props); };
    const a = 'https://images.canteen.edu/a.jpg', b = 'https://images.canteen.edu/b.jpg';
    let view = render(a), oldA = nodes(view).find(node => node.type === 'img'); oldA.props.onLoad();
    assert.equal(render(a).props['aria-label'], 'Dosa'); render(b); view = render(a);
    let freshA = nodes(view).find(node => node.type === 'img'); assert.match(freshA.props.className, /opacity-0/);
    freshA.props.onError(); assert.equal(nodes(render(a)).filter(node => node.type === 'img').length, 0);
    render(b); view = render(a); freshA = nodes(view).find(node => node.type === 'img'); assert.ok(freshA); assert.match(freshA.props.className, /opacity-0/);
    oldA.props.onLoad(); assert.match(nodes(render(a)).find(node => node.type === 'img').props.className, /opacity-0/);
    freshA.props.onLoad(); assert.equal(render(a).props['aria-label'], 'Dosa');
  });
  await check('Successful menu settles Home independently of a slow orders request', async () => {
    const orders = deferred(); const h = appHarness({ getOrders: () => orders.promise });
    let store = await h.login(); assert.equal(store.menu.length, 1); assert.equal(store.menuLoading, false); assert.equal(store.loading, true);
    h.runtime.begin('Home'); assert.doesNotMatch(text(h.app.HomeScreen()), /Loading your canteen/);
    orders.resolve([]); await tick(); store = h.render(); assert.equal(store.loading, false);
  });
  await check('Background menu polling retains content without reintroducing initial loading', async () => {
    const h = appHarness(); await h.login(); const menu = deferred(); h.api.getMenu = () => menu.promise;
    const running = h.render().refresh(); await tick(); let store = h.render(); assert.equal(store.menu.length, 1); assert.equal(store.menuLoading, false);
    menu.resolve([meal]); await running; assert.equal(h.render().menuError, null);
  });
  await check('Failed menu requests settle and retry clears the error', async () => {
    const h = appHarness({ getMenu: async () => { throw Error('Menu offline'); } }); let store = await h.login();
    assert.equal(store.menuLoading, false); assert.equal(store.loading, false); assert.equal(store.menuError, 'Menu offline');
    h.runtime.begin('Home'); assert.match(text(h.app.HomeScreen()), /Menu offline.*Retry/);
    h.api.getMenu = async () => [meal]; await h.render().refresh(); store = h.render(); assert.equal(store.menu.length, 1); assert.equal(store.menuError, null);
  });
  await check('Synchronous API failure and malformed menu data cannot strand loading or retry locks', async () => {
    const h = appHarness({ getMenu: () => { throw Error('Immediate failure'); } }); let store = await h.login(); assert.equal(store.menuLoading, false); assert.equal(store.loading, false);
    h.api.getMenu = async () => ({ invalid: true }); await h.render().refresh(); store = h.render(); assert.match(store.menuError, /invalid menu/); assert.equal(store.loading, false);
    h.api.getMenu = async () => [meal]; await h.render().refresh(); assert.equal(h.render().menuError, null);
  });
  await check('A prior session cannot overwrite or unlock a newer pending refresh', async () => {
    const first = deferred(), second = deferred(); let menus = 0, login = 0;
    const h = appHarness({ getMenu: () => (++menus === 1 ? first.promise : second.promise), login: async () => ({ success: true, user: { id: ++login === 1 ? 'student-a' : 'student-b', name: 'Student' } }) });
    await h.login(); await h.render().logoutUser(); h.render(); await h.login(); first.resolve([{ ...meal, name: 'Old session menu' }]); await tick();
    let store = h.render(); assert.equal(store.menu.length, 0); assert.equal(store.menuLoading, true); await store.refresh(); assert.equal(menus, 2);
    second.resolve([{ ...meal, name: 'Current menu' }]); await tick(); store = h.render(); assert.equal(store.menu[0].name, 'Current menu'); assert.equal(store.menuLoading, false);
  });
  await check('Home category shortcuts pass the real taxonomy into menu filtering', async () => {
    const h = appHarness(); await h.login(); h.runtime.begin('Home'); const home = h.app.HomeScreen();
    const beverages = nodes(home).find(node => node.type === 'button' && text(node).includes('Beverages'));
    assert.ok(beverages); beverages.props.onClick(); let store = h.render(); assert.equal(store.menuCategory, 'Beverages'); assert.equal(store.screen, 'menu');
    h.runtime.begin('Home'); const quick = nodes(h.app.HomeScreen()).find(node => node.type === 'button' && text(node).includes('Quick Bites')); quick.props.onClick(); assert.equal(h.render().menuCategory, 'Quick Bites');
  });
  await check('Search, category, availability and refreshed prices use authoritative menu records', async () => {
    const snack = { ...meal, id: 'snack', name: 'Samosa', category: 'Snacks', price: 25 }, sold = { ...meal, id: 'sold', available: false };
    const h = appHarness({ getMenu: async () => [meal, snack, sold] }); await h.login(); let store = h.render(); store.setMenuCategory('Meals'); store = h.render();
    h.runtime.begin('Menu'); let view = h.app.MenuScreen(); let cards = nodes(view).filter(node => node.type?.name === 'FoodCardWide'); assert.equal(cards.length, 2); assert.ok(cards.every(node => node.props.item.category === 'Meals'));
    nodes(view).find(node => node.type === 'input').props.onChange({ target: { value: ' South Dish ' } }); h.runtime.begin('Menu'); view = h.app.MenuScreen(); assert.equal(nodes(view).filter(node => node.type?.name === 'FoodCardWide').length, 2);
    store.add({ ...sold, available: true }); assert.equal(h.render().cart.length, 0); h.render().add({ ...meal, price: 999 }); store = h.render(); assert.equal(store.cartTotal, 40);
    h.api.getMenu = async () => [{ ...meal, price: 30, available: false }]; await store.refresh(); store = h.render(); assert.equal(store.cartTotal, 30); assert.equal(store.cart[0].item.available, false); await assert.rejects(store.submitOrder('wallet'), /unavailable/);
  });
  console.log(`Student menu checks passed: ${passed}. No network, database or build changes performed.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
