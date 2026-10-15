// Focused behavioural checks of the actual lunch editor, timetable and kitchen cards.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
const jsx = (type, props) => ({ type, props });
const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
const text = value => typeof value === 'string' || typeof value === 'number' ? String(value) : Array.isArray(value) ? value.map(text).join(' ') : value && typeof value === 'object' ? text(value.props?.children) : '';
const tick = () => new Promise(resolve => setImmediate(resolve));
function hooks() {
  const states = new Map(), effects = []; let group, index;
  const react = {
    useState(initial) { const i = index++; const slot = group[i] ||= { value: typeof initial === 'function' ? initial() : initial }; return [slot.value, value => { slot.value = typeof value === 'function' ? value(slot.value) : value; }]; },
    useRef(initial) { return group[index++] ||= { current: initial }; },
    useEffect(run, deps) { const i = index++, old = group[i]; if (!old || deps?.some((value, n) => !Object.is(value, old.deps[n]))) { group[i] = { deps }; effects.push(run); } },
  };
  return { react: { ...react, default: react }, begin(key) { if (!states.has(key)) states.set(key, []); group = states.get(key); index = 0; }, commit() { while (effects.length) effects.shift()(); } };
}
function load(file, modules, globals = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, {
    exports, require(name) { if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx }; if (!(name in modules)) throw Error('Unexpected import: ' + name); return modules[name]; }, Date, Set, Promise, Error, console, ...globals,
  });
  return exports;
}
const meal = { day: 'Thursday', meal_type: 'lunch', items: ['Chapati', 'Salad', 'Dal', 'Rice', 'Bhindi', 'Potato'], sabji_options: ['Bhindi', 'Potato'], ordering_enabled: true };
let count = 0;
async function check(name, run) { await run(); count++; console.log('PASS ' + name); }
(async () => {
  const runtime = hooks(), calls = [], saved = [], toasts = []; let failure = null;
  const api = { saveWeeklyMenu: async rows => { calls.push(JSON.parse(JSON.stringify(rows))); if (failure) throw Error(failure); return { schedule: rows }; } };
  const editor = load('src/components/AdminLunchConfiguration.tsx', { react: runtime.react, '../lib/adminOperationsApi': { adminOperationsApi: api } });
  const props = { day: 'Thursday', meal, onSaved: row => saved.push(row), onShowToast: (...args) => toasts.push(args) };
  const render = (key = 'editor', overrides = {}) => { runtime.begin(key); const tree = editor.default({ ...props, ...overrides }); runtime.commit(); return tree; };
  const field = (tree, label) => nodes(tree).find(node => node.props?.['aria-label'] === label);
  const submit = tree => nodes(tree).find(node => node.type === 'button' && /Save (lunch|dinner)/.test(text(node))).props.onClick();
  await check('Editor loads selected-day complete contents and both configured sabjis', () => {
    const tree = render(); assert.equal(field(tree, 'Complete lunch contents').props.value, meal.items.join('\n'));
    assert.equal(field(tree, 'Sabji option 1').props.value, 'Bhindi'); assert.equal(field(tree, 'Sabji option 2').props.value, 'Potato');
    assert.ok(text(tree).includes('Thursday')); assert.ok(text(tree).includes('₹45')); assert.ok(text(tree).includes('₹80')); assert.ok(text(tree).includes('IST'));
  });
  await check('Enabled lunch rejects missing, duplicate and removed sabji selections', async () => {
    let tree = render('invalid'); field(tree, 'Sabji option 2').props.onChange({ target: { value: 'Bhindi' } });
    submit(render('invalid')); await tick(); assert.equal(calls.length, 0); assert.match(text(render('invalid')), /exactly two different/);
    field(render('invalid'), 'Sabji option 2').props.onChange({ target: { value: '' } }); submit(render('invalid')); await tick(); assert.equal(calls.length, 0);
    field(render('invalid'), 'Sabji option 2').props.onChange({ target: { value: 'Potato' } });
    field(render('invalid'), 'Complete lunch contents').props.onChange({ target: { value: 'Chapati\nSalad\nBhindi' } }); submit(render('invalid')); await tick(); assert.equal(calls.length, 0); assert.match(text(render('invalid')), /must be included/);
  });
  await check('Save sends only selected lunch row with actual configuration and handles success', async () => {
    const tree = render(); submit(tree); await tick(); assert.equal(calls.length, 1); assert.deepEqual(calls[0], [meal]); assert.equal(saved.length, 1); assert.equal(toasts.at(-1)[2], 'success');
    assert.equal(nodes(render()).find(node => node.type === 'button').props.disabled, false);
  });
  await check('Backend save error keeps edits and is visible without reporting success', async () => {
    failure = 'Menu changed. Please refresh.'; let tree = render('failed');
    field(tree, 'Complete lunch contents').props.onChange({ target: { value: meal.items.join('\n') + '\nCurd' } }); submit(render('failed')); await tick(); tree = render('failed');
    assert.ok(field(tree, 'Complete lunch contents').props.value.includes('Curd')); assert.match(text(tree), /Menu changed/); assert.equal(saved.length, 1); assert.equal(toasts.at(-1)[2], 'error'); failure = null;
  });
  await check('Unconfigured days start disabled and may save a non-orderable draft', async () => {
    let tree = render('empty', { day: 'Friday', meal: undefined }); assert.equal(field(tree, 'Complete lunch contents').props.value, '');
    assert.equal(nodes(tree).find(node => node.type === 'input').props.checked, false); submit(tree); await tick();
    assert.deepEqual(calls.at(-1), [{ day: 'Friday', meal_type: 'lunch', items: [], sabji_options: [], ordering_enabled: false }]);
  });
  await check('Timetable changes day and passes original meal metadata to the lunch editor', async () => {
    const rt = hooks(), marker = () => null, friday = { ...meal, day: 'Friday', sabji_options: ['Paneer', 'Peas'], items: ['Rice', 'Paneer', 'Peas'] };
    const weekly = load('src/components/WeeklyScheduleView.tsx', { react: rt.react, '../lib/adminOperationsApi': { adminOperationsApi: { weeklyMenu: async () => [meal, friday] } }, './AdminLunchConfiguration': { default: marker } });
    const draw = () => { rt.begin('weekly'); const tree = weekly.default({}); rt.commit(); return tree; }; draw(); await tick();
    let tree = draw(); nodes(tree).find(node => node.type === 'button' && text(node) === 'Friday').props.onClick(); tree = draw();
    const child = nodes(tree).find(node => node.type === marker); assert.equal(child.props.day, 'Friday'); assert.deepEqual(child.props.meal.sabji_options, ['Paneer', 'Peas']);
  });
  await check('Kitchen cards show immutable sabji and contents snapshots alongside ordinary items', async () => {
    const rt = hooks(), order = { id: 'order-1', orderId: 1, pickupToken: '1001', number: '1001', studentName: 'Test Student', rollNumber: 'QA', total: 45, status: 'Queued', date: '2026-10-15', prepTimeMinutes: 10, items: [{ id: 'lunch:chapati-bhaji', name: 'Chapati Bhaji', qty: 1, price: 45, sabjiChoice: 'Bhindi', contents: ['3 chapatis', 'Salad', 'Bhindi'], mealDate: '2026-10-15', mealType: 'lunch' }, { id: 'ordinary', name: 'Tea', qty: 1, price: 10 }] };
    const live = load('src/components/LiveOrdersView.tsx', { react: rt.react, '../lib/adminOperationsApi': { adminOperationsApi: { orders: async () => [order] } }, './PaymentReconciliationPanel': { default: () => null } }, { setInterval() { return 1; }, clearInterval() {}, document: { visibilityState: 'visible' } });
    const draw = () => { rt.begin('orders'); const tree = live.default({}); rt.commit(); return tree; }; draw(); await tick(); const output = text(draw());
    assert.ok(output.includes('Sabji:  Bhindi')); assert.ok(output.includes('3 chapatis · Salad · Bhindi')); assert.ok(output.includes('2026-10-15')); assert.ok(output.includes('Tea')); assert.ok(output.includes('Start Cooking'));
  });
  await check('Shared Dinner editor saves only dinner and reports Dinner-specific validation', async () => {
    const dinner={...meal,meal_type:'dinner',items:['Chapati','Salad','Rice','Beans','Peas'],sabji_options:['Beans','Peas']};
    let tree=render('dinner',{mealType:'dinner',meal:dinner}); assert.equal(field(tree,'Complete dinner contents').props.value,dinner.items.join('\n')); assert.match(text(tree),/Dinner/); submit(tree);await tick();assert.deepEqual(calls.at(-1),[dinner]);assert.equal(toasts.at(-1)[0],'Dinner configuration saved');
    field(render('dinner-invalid',{mealType:'dinner',meal:dinner}),'Complete dinner contents').props.onChange({target:{value:''}});submit(render('dinner-invalid',{mealType:'dinner',meal:dinner}));await tick();assert.match(text(render('dinner-invalid',{mealType:'dinner',meal:dinner})),/complete dinner contents/);
  });
  await check('Weekly timetable exposes independent Lunch/Dinner editors and preserves lunch on dinner save', async () => {
    const rt=hooks(),marker=()=>null,dinner={...meal,meal_type:'dinner',items:['Rice','Beans','Peas'],sabji_options:['Beans','Peas'],ordering_enabled:false};
    const weekly=load('src/components/WeeklyScheduleView.tsx',{react:rt.react,'../lib/adminOperationsApi':{adminOperationsApi:{weeklyMenu:async()=>[meal,dinner]}},'./AdminLunchConfiguration':{default:marker}});
    const draw=()=>{rt.begin('independent-weekly');const tree=weekly.default({});rt.commit();return tree;};draw();await tick();let tree=draw();nodes(tree).find(node=>node.type==='button'&&text(node)==='Thursday').props.onClick();tree=draw();
    let editors=nodes(tree).filter(node=>node.type===marker);assert.equal(editors.length,2);const lunchBefore=JSON.stringify(editors.find(node=>node.props.mealType==='lunch').props.meal);const edited={...dinner,items:[...dinner.items,'Dal']};editors.find(node=>node.props.mealType==='dinner').props.onSaved(edited);editors=nodes(draw()).filter(node=>node.type===marker);assert.equal(JSON.stringify(editors.find(node=>node.props.mealType==='lunch').props.meal),lunchBefore);assert.deepEqual(editors.find(node=>node.props.mealType==='dinner').props.meal.items,edited.items);
  });
  console.log(count + ' Admin lunch/dinner checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
