// Behavioural checks use the actual admin form, private image client and Student bill screens.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const repo = path.resolve(__dirname, '..'), ts = require(path.join(repo, 'node_modules/typescript'));
const tick = () => new Promise(resolve => setImmediate(resolve)), jsx = (type, props) => ({ type, props });
const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
const text = value => typeof value === 'string' || typeof value === 'number' ? String(value) : Array.isArray(value) ? value.map(text).join(' ') : value && typeof value === 'object' ? text(value.props?.children) : '';
function load(file, modules, globals = {}, extra = '') {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(repo, file), 'utf8') + extra, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText,
    { exports, require: name => { if (name.endsWith('.css')) return {}; if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx }; if (!(name in modules)) throw Error('Unexpected import ' + name); return modules[name]; }, URL, Error, Promise, console, ...globals }, { filename: file });
  return exports;
}
function hooks() {
  const states = new Map(), effects = []; let group, index;
  const begin = key => { if (!states.has(key)) states.set(key, []); group = states.get(key); index = 0; };
  const react = {
    createContext: () => ({ Provider: 'Provider' }), useContext: () => runtime.store,
    useState: initial => { const i = index++; const slot = group[i] ||= { value: typeof initial === 'function' ? initial() : initial }; return [slot.value, value => { slot.value = typeof value === 'function' ? value(slot.value) : value; }]; },
    useRef: initial => group[index++] ||= { current: initial },
    useEffect: (run, deps) => { const i = index++, old = group[i]; if (!old || !deps || deps.some((value, n) => !Object.is(value, old.deps[n]))) { group[i] = { deps, cleanup: old?.cleanup }; const slot = group[i]; effects.push(() => { old?.cleanup?.(); slot.cleanup = run(); }); } },
  };
  const runtime = { react: { ...react, default: react }, begin, store: null, commit: () => { while (effects.length) effects.shift()(); } }; return runtime;
}
const food = { id: 'menu-1', name: 'Samosa', desc: 'Snack', category: 'Snacks', price: 25, prepMins: 5, emoji: '🍽️', photo: '', veg: true, available: false, timingWindow: 'all_day', customizations: [] };
const asset = { id: 'a'.repeat(32), dishName: 'Samosa', source: 'Own canteen photograph', license: 'Owned', attribution: 'Canteen manager', photo: 'https://api.canteen.edu/api/food-images/a', width: 100, height: 100 };
let count = 0; async function check(name, run) { await run(); count++; console.log('PASS ' + name); }
(async () => {
  const runtime = hooks(), chosen = [], pending = [], uploaded = [], revoked = []; let serial = 0;
  class LocalURL extends URL { static createObjectURL() { return 'blob:admin-preview-' + ++serial; } static revokeObjectURL(url) { revoked.push(url); } }
  const pickerModule = load('src/components/AdminFoodImagePicker.tsx', { react: runtime.react, '../lib/adminOperationsApi': { adminOperationsApi: { foodImage: async () => asset, foodImages: async () => [asset], foodImageBlob: async () => new Blob(['image'], { type: 'image/webp' }), uploadFoodImage: async input => { uploaded.push(input); return asset; } } } }, { URL: LocalURL, AbortController, setTimeout: callback => { callback(); return 1; }, clearTimeout() {} });
  const props = { dishName: 'Samosa', imageId: null, confirmed: false, disabled: false, onImageChange: id => { chosen.push(id); props.imageId = id; }, onConfirmedChange: value => { props.confirmed = value; }, onBusyChange() {}, onPendingChange: value => pending.push(value) };
  const renderPicker = () => { runtime.begin('picker'); const view = pickerModule.default(props); runtime.commit(); return view; };
  await check('Upload rejects unsupported MIME, empty files and oversized photographs', () => {
    for (const file of [{ type: 'text/html', size: 100 }, { type: 'image/png', size: 0 }, { type: 'image/jpeg', size: 5 * 1024 * 1024 + 1 }]) assert.ok(pickerModule.validateFoodImageFile(file));
    assert.equal(pickerModule.validateFoodImageFile({ type: 'image/webp', size: 1000 }), '');
  });
  await check('Device preview stays local, upload requires rights and returns a reusable unconfirmed image reference', async () => {
    let view = renderPicker(); nodes(view).find(node => node.type === 'input' && node.props.type === 'file').props.onChange({ target: { files: [{ type: 'image/png', size: 1000, name: 'samosa.png' }] } });
    renderPicker(); view = renderPicker(); assert.equal(pending.at(-1), true);
    const preview = nodes(view).find(node => node.type === 'img'); assert.match(preview.props.src, /^blob:admin-preview-/); const originalUrl = preview.props.src;
    preview.props.onLoad({ currentTarget: { naturalWidth: 100, naturalHeight: 100, classList: { remove() {} } } });
    for (const [label, value] of [['Source / original URL', 'Own canteen photograph'], ['License / permission', 'Owned'], ['Attribution / credit', 'Canteen manager']]) {
      view = renderPicker(); const field = nodes(view).find(node => node.type === 'label' && text(node).startsWith(label)); nodes(field).find(node => node.type === 'input').props.onChange({ target: { value } });
    }
    view = renderPicker(); const uploadButton = nodes(view).find(node => node.type === 'button' && text(node) === 'Upload to library'); assert.equal(uploadButton.props.disabled, true);
    const rights = nodes(view).find(node => node.type === 'label' && text(node).includes('use it commercially')); nodes(rights).find(node => node.type === 'input').props.onChange({ target: { checked: true } });
    view = renderPicker(); nodes(view).find(node => node.type === 'button' && text(node) === 'Upload to library').props.onClick(); await tick(); renderPicker(); renderPicker();
    assert.equal(uploaded.length, 1); assert.equal(uploaded[0].rightsConfirmed, true); assert.equal(uploaded[0].attribution, 'Canteen manager'); assert.equal(chosen.at(-1), asset.id); assert.equal(props.confirmed, false); assert.equal(pending.at(-1), false); assert.ok(revoked.includes(originalUrl));
  });
  await check('Private preview uses an authenticated fixed URL and rejects non-image responses', async () => {
    let request, invalid = false; class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
    const module = load('src/lib/adminOperationsApi.ts', { './adminApi': { adminRequest() {}, usesAdminCookieSession: false, getAdminToken: () => 'test-session', clearAdminToken() {}, AdminApiError: ApiError }, './apiConfig': { apiUrl: value => 'https://api.canteen.edu' + value } }, { Blob, FormData, AbortController, setTimeout, clearTimeout, AbortSignal, fetch: async (url, options) => { request = { url, options }; return { ok: true, blob: async () => new Blob(['image'], { type: invalid ? 'text/html' : 'image/webp' }) }; } });
    await module.adminOperationsApi.foodImageBlob(asset.id); assert.ok(request.url.endsWith('/' + asset.id + '/content')); assert.ok(!request.url.includes('test-session')); assert.equal(request.options.headers.Authorization, 'Bearer test-session'); assert.equal(request.options.credentials, 'omit');
    invalid = true; await assert.rejects(module.adminOperationsApi.foodImageBlob(asset.id), error => error.status === 502);
  });
  function inventoryHarness() {
    const runtime = hooks(), creates = [], updates = []; function Picker() {};
    const api = { catalogue: async () => [food], createItem: async input => { creates.push(input); return { ...input, id: 'new', photo: '', rating: 0 }; }, updateItem: async (id, input) => { updates.push(input); return { ...food, ...input, id }; }, availability: async () => food };
    const module = load('src/components/AlaCarteManagement.tsx', { react: runtime.react, '../lib/adminOperationsApi': { adminOperationsApi: api }, './FoodImage': { default() {} }, './AdminFoodImagePicker': { default: Picker } }, { confirm: () => true });
    const render = () => { runtime.begin('inventory'); const view = module.default({}); runtime.commit(); return view; }; return { creates, updates, Picker, render };
  }
  await check('New dishes start as drafts; pending upload blocks save and a confirmed image unlocks publication', async () => {
    const h = inventoryHarness(); h.render(); await tick(); let view = h.render(); nodes(view).find(node => node.type === 'button' && text(node).includes('Add New Item')).props.onClick(); view = h.render(); nodes(view).find(node => node.type === 'input' && node.props.placeholder === 'e.g. Paneer Tikka Roll').props.onChange({ target: { value: 'Future dish' } }); view = h.render();
    let picker = nodes(view).find(node => node.type === h.Picker); assert.equal(picker.props.imageId, null); assert.equal(picker.props.confirmed, false);
    picker.props.onPendingChange(true); view = h.render(); nodes(view).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); await tick(); assert.equal(h.creates.length, 0);
    picker.props.onPendingChange(false); picker.props.onImageChange(asset.id); view = h.render(); picker = nodes(view).find(node => node.type === h.Picker); picker.props.onConfirmedChange(true); view = h.render();
    const availability = nodes(view).find(node => node.type === 'div' && node.props.className === 'flex items-center justify-between p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]' && text(node).includes('Available to Students'));
    const toggle = nodes(availability).find(node => node.type === 'button'); assert.equal(toggle.props.disabled, false); toggle.props.onClick(); view = h.render(); nodes(view).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); await tick();
    assert.equal(h.creates.length, 1); assert.equal(h.creates[0].available, true); assert.equal(h.creates[0].imageId, asset.id); assert.equal(h.creates[0].imageConfirmed, true); assert.ok(!('photo' in h.creates[0]));
  });
  await check('Removing a photograph saves an inactive draft without deleting the menu item', async () => {
    const h = inventoryHarness(); h.render(); await tick(); let view = h.render(); nodes(view).find(node => node.type === 'button' && node.props.title === 'Edit Item').props.onClick(); view = h.render(); nodes(view).find(node => node.type === h.Picker).props.onImageChange(null); view = h.render(); nodes(view).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); await tick();
    assert.equal(h.updates.length, 1); assert.equal(h.updates[0].imageId, null); assert.equal(h.updates[0].available, false); assert.equal(h.updates[0].imageConfirmed, false);
  });
  const bills = hooks();
  const app = load('student/src/App.tsx', { react: bills.react, '../../src/lib/apiClient': { apiClient: { getPaymentsConfig: async () => ({ enabled: false }) }, STUDENT_SESSION_EXPIRED: 'expired' }, '../../src/lib/paymentCheckout': {}, '../../src/components/FoodImage': { default() {} }, '../../src/components/FoodPhotoCredits': { default() {} } }, {}, '\nexport { CartScreen, CheckoutScreen, OrderDetailsScreen };');
  bills.store = { cart: [{ item: food, qty: 2 }], cartTotal: 50, go() {}, submitOrder() {}, user: { walletBalance: 300 }, menu: [food] };
  await check('New Cart and Checkout totals equal item total and contain no tax or packaging rows', () => {
    for (const screen of ['CartScreen', 'CheckoutScreen']) { bills.begin(screen); const view = app[screen](); const rows = nodes(view).filter(node => typeof node.type === 'function' && node.props.l); assert.equal(rows.find(node => node.props.l === 'To pay').props.v, '₹50'); assert.equal(rows.filter(node => /GST|packaging/i.test(node.props.l)).length, 0); }
  });
  await check('Old order charges remain visible and zero-fee new orders hide the extra row', () => {
    for (const fee of [8, 0]) { bills.store.order = { ...food, id: 'order', number: '#1', items: [], itemTotal: 50, packagingFee: fee, gst: 0, total: 50 + fee, payment: 'Paid', status: 'Completed', paymentMethod: 'wallet', date: new Date().toISOString() }; bills.begin('history-' + fee); const rows = nodes(app.OrderDetailsScreen()).filter(node => node.props?.l === 'Taxes & packaging'); assert.equal(rows.length, fee ? 1 : 0); if (fee) assert.equal(rows[0].props.v, '₹8'); }
  });
  console.log(`${count} admin image and pricing checks passed.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
