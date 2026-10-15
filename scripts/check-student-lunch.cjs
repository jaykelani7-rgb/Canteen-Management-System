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
  const api = { hasSession: () => false, getMenu: async () => [meal], getLunchMenu: async () => ({ date: '2026-10-15', day: 'Thursday', mealType: 'lunch', available: false, unavailableReason: 'Lunch unconfigured', mealRevision: null, contents: [], sabjiOptions: [], options: [] }), getOrders: async () => [], getNotifications: async () => [], getMe: async () => ({ success: true, user }), login: async () => ({ success: true, user }), logout: async () => {}, ...overrides };
  const app = load('student/src/App.tsx', {
    react: runtime.react, '../../src/lib/apiClient': { apiClient: api, STUDENT_SESSION_EXPIRED: 'expired' },
    '../../src/lib/paymentCheckout': { checkoutIntent: () => 'lunch-test-key', clearCheckoutIntent() {} }, '../../src/lib/studentLunch': load('src/lib/studentLunch.ts', {}), '../../src/components/FoodImage': { default: function FoodImage() {} },
    '../../src/components/FoodPhotoCredits': { default: function FoodPhotoCredits() {} },
  }, { setTimeout: () => 1, clearTimeout() {}, setInterval: runtime.setInterval, clearInterval: runtime.clearInterval,
    document: { visibilityState: 'visible' }, window: { addEventListener() {}, removeEventListener() {} } }, '\nexport { HomeScreen, MenuScreen, DetailsScreen, CartScreen, OrderDetailsScreen };');
  function render() { runtime.begin('App'); runtime.store = app.default().props.value; runtime.commit(); return runtime.store; }
  const mounted = { app, api, runtime, render, login: async () => { await render().loginUser('ROLL', 'PASS'); render(); await tick(); return render(); } };
  render(); return mounted;
}

const h = load('src/lib/studentLunch.ts', {});
const lunch = { date: '2026-10-15', day: 'Thursday', mealType: 'lunch', available: true, unavailableReason: null, mealRevision: 'rev-a', contents: ['Rice','Dal','Chapati','Salad','Cabbage','Potato'], sabjiOptions: ['Cabbage','Potato'], options: [{id:h.CHAPATI_BHAJI_ID,name:'Chapati Bhaji',price:45},{id:h.THALI_ID,name:'Thali',price:80}] };
const [chapati, thali] = h.lunchItems(lunch);
const paneerLunch = { ...lunch, contents: ['3 chapatis','Salad','Paneer','Aloo'], sabjiOptions: ['Paneer','Aloo'] };
const alooLunch = { ...paneerLunch, mealRevision: 'rev-aloo', contents: ['3 chapatis','Salad','Aloo'], sabjiOptions: ['Aloo'] };
const [alooChapati, alooThali] = h.lunchItems(alooLunch);
const harness = (overrides = {}) => appHarness({ getLunchMenu: async () => structuredClone(lunch), ...overrides });
function view(app, name) { app.render(); app.runtime.begin(name); return app.app[name](); }
(async () => {
  await check('Backend prices are used without a client price table', () => { assert.equal(chapati.price,45); assert.equal(thali.price,80); assert.equal(h.lunchItems({...lunch,options:[{...lunch.options[0],price:47}]})[0].price,47); });
  await check('Thali contents reflect configured current lunch', () => assert.equal(thali.lunch.contents.join('|'),lunch.contents.join('|')));
  await check('Identical sabji variants have stable keys', () => assert.equal(h.lunchLineKey(chapati,'Potato'),h.lunchLineKey(chapati,'Potato')));
  await check('Different sabjis have separate keys', () => assert.notEqual(h.lunchLineKey(chapati,'Potato'),h.lunchLineKey(chapati,'Cabbage')));
  await check('Different revisions have separate keys', () => assert.notEqual(h.lunchLineKey(chapati,'Potato'),h.lunchLineKey({...chapati,lunch:{...chapati.lunch,revision:'rev-b'}},'Potato')));
  await check('Sabji is required', () => assert.match(h.lunchCartError([{item:chapati}],lunch),/exactly one/));
  await check('Unknown sabji is rejected', () => assert.match(h.lunchCartError([{item:chapati,sabjiChoice:'Paneer'}],lunch),/exactly one/));
  await check('Both valid sabjis and Thali are accepted', () => assert.equal(h.lunchCartError([{item:chapati,sabjiChoice:'Potato'},{item:chapati,sabjiChoice:'Cabbage'},{item:thali}],lunch),null));
  await check('Paneer unavailable leaves Aloo Chapati Bhaji enabled at 45 with effective Thali contents', () => {
    assert.equal(alooChapati.available,true); assert.equal(alooChapati.price,45); assert.equal(alooThali.price,80);
    assert.equal(alooChapati.lunch.sabjiOptions.join('|'),'Aloo'); assert.equal(h.lunchContents(alooThali).join('|'),'3 chapatis|Salad|Aloo');
    assert.equal(h.lunchCartError([{item:alooChapati,sabjiChoice:'Aloo'},{item:alooThali}],alooLunch),null);
  });
  await check('One remaining sabji still requires selection and rejects unavailable Paneer', () => {
    assert.match(h.lunchCartError([{item:alooChapati}],alooLunch),/exactly one/);
    assert.match(h.lunchCartError([{item:alooChapati,sabjiChoice:'Paneer'}],alooLunch),/exactly one/);
    assert.match(h.lunchCartError([{item:alooChapati,sabjiChoice:'Aloo'}],{...alooLunch,sabjiOptions:[]}),/exactly one/);
  });
  await check('Individual disabled Chapati does not disable an available Thali', () => {
    const menu={...alooLunch,options:[{...alooLunch.options[0],available:false,unavailableReason:'Chapatis unavailable'},{...alooLunch.options[1],available:true}]};
    const [disabledChapati,availableThali]=h.lunchItems(menu); assert.equal(disabledChapati.available,false); assert.equal(availableThali.available,true); assert.equal(disabledChapati.lunch.unavailableReason,'Chapatis unavailable');
    assert.equal(h.lunchCartError([{item:disabledChapati,sabjiChoice:'Aloo'}],menu),'Chapatis unavailable'); assert.equal(h.lunchCartError([{item:availableThali}],menu),null);
  });
  await check('Closed meal preserves the server reason', () => assert.equal(h.lunchCartError([{item:thali}],{...lunch,available:false,unavailableReason:'Lunch closed'}),'Lunch closed'));
  await check('Changed date is rejected', () => assert.match(h.lunchCartError([{item:thali}],{...lunch,date:'2026-10-16'}),/changed/));
  await check('Changed revision is rejected', () => assert.match(h.lunchCartError([{item:thali}],{...lunch,mealRevision:'rev-b'}),/changed/));
  await check('Changed price is rejected without repricing the snapshot', () => { assert.match(h.lunchCartError([{item:thali}],{...lunch,options:[lunch.options[0],{...lunch.options[1],price:85}]}),/changed/); assert.equal(thali.price,80); });
  await check('Network/configuration failure blocks meal checkout', () => assert.match(h.lunchCartError([{item:thali}],null),/verified/));
  await check('Catalogue-only checkout does not require lunch', () => assert.equal(h.lunchCartError([{item:meal}],null),null));
  await check('Payload sends revision and choice, without client price', () => assert.equal(JSON.stringify(h.lunchOrderInput({item:chapati,qty:2,sabjiChoice:'Potato'})),JSON.stringify({id:h.CHAPATI_BHAJI_ID,qty:2,mealRevision:'rev-a',sabjiChoice:'Potato'})));
  await check('Chapati contents contain only the chosen sabji', () => assert.equal(h.lunchContents(chapati,'Cabbage').join('|'),'3 chapatis|Salad|Cabbage'));
  await check('Catalogue order payload remains unchanged', () => assert.equal(JSON.stringify(h.lunchOrderInput({item:meal,qty:1})),JSON.stringify({id:meal.id,qty:1})));
  await check('Actual Details UI disables Add until a sabji radio is selected', async () => {
    const app=harness(); let store=await app.login(); store.select(store.menu.find(item=>item.id===h.CHAPATI_BHAJI_ID));
    let page=view(app,'DetailsScreen'), add=nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add'));
    assert.equal(add.props.disabled,true); const radios=nodes(page).filter(node=>node.type==='input'&&node.props.type==='radio'); assert.equal(radios.length,2); assert.ok(radios.every(node=>!node.props.checked));
    assert.equal(app.render().add(chapati),false); assert.equal(app.render().cart.length,0);
    radios[0].props.onChange(); page=view(app,'DetailsScreen'); add=nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')); assert.equal(add.props.disabled,false); add.props.onClick(); store=app.render(); assert.equal(store.cart.length,1); assert.equal(store.cart[0].sabjiChoice,'Cabbage');
  });
  await check('Actual Details UI displays only Aloo and requires explicit selection before adding at 45', async () => {
    const app=harness({getLunchMenu:async()=>structuredClone(alooLunch)}); let store=await app.login(); store.select(store.menu.find(item=>item.id===h.CHAPATI_BHAJI_ID));
    let page=view(app,'DetailsScreen'),add=nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add'));
    const radios=nodes(page).filter(node=>node.type==='input'&&node.props.type==='radio'); assert.equal(radios.length,1); assert.equal(radios[0].props.value,'Aloo'); assert.equal(radios[0].props.checked,false); assert.equal(add.props.disabled,true); assert.doesNotMatch(text(page),/today’s two sabjis/);
    assert.equal(app.render().add(alooChapati,1,'Paneer'),false); assert.equal(app.render().cart.length,0);
    radios[0].props.onChange(); page=view(app,'DetailsScreen'); add=nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')); assert.equal(add.props.disabled,false); add.props.onClick(); store=app.render(); assert.equal(store.cartTotal,45); assert.equal(store.cart[0].sabjiChoice,'Aloo');
  });
  await check('Actual Details refresh removes Paneer and disables its stale selection until Aloo is selected', async () => {
    const app=harness({getLunchMenu:async()=>structuredClone(paneerLunch)}); await app.login(); app.render().select(app.render().menu.find(item=>item.id===h.CHAPATI_BHAJI_ID));
    let page=view(app,'DetailsScreen'); nodes(page).find(node=>node.type==='input'&&node.props.value==='Paneer').props.onChange();
    app.api.getLunchMenu=async()=>structuredClone(alooLunch); await app.render().refresh(); page=view(app,'DetailsScreen');
    const radios=nodes(page).filter(node=>node.type==='input'&&node.props.type==='radio'); assert.equal(radios.length,1); assert.equal(radios[0].props.value,'Aloo'); assert.equal(radios[0].props.checked,false); assert.equal(nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')).props.disabled,true);
    radios[0].props.onChange(); page=view(app,'DetailsScreen'); assert.equal(nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')).props.disabled,false);
  });
  await check('Turning Paneer back on restores its selectable radio without auto-selection', async () => {
    const app=harness({getLunchMenu:async()=>structuredClone(alooLunch)}); await app.login(); app.render().select(app.render().menu.find(item=>item.id===h.CHAPATI_BHAJI_ID)); view(app,'DetailsScreen');
    app.api.getLunchMenu=async()=>({...structuredClone(paneerLunch),mealRevision:'rev-restored'}); await app.render().refresh(); let page=view(app,'DetailsScreen');
    const radios=nodes(page).filter(node=>node.type==='input'&&node.props.type==='radio'); assert.equal(radios.length,2); assert.ok(radios.every(node=>!node.props.checked));
    radios.find(node=>node.props.value==='Paneer').props.onChange(); page=view(app,'DetailsScreen'); nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')).props.onClick(); assert.equal(app.render().cart[0].sabjiChoice,'Paneer'); assert.equal(app.render().cartTotal,45);
  });
  await check('Actual cart isolates quantity edits and removal by sabji variant', async () => {
    const app=harness(); await app.login(); app.render().add(chapati,1,'Cabbage'); app.render().add(chapati,2,'Potato'); let store=app.render(); assert.equal(store.cart.length,2); assert.equal(store.cartTotal,135);
    const key=store.cart.find(line=>line.sabjiChoice==='Cabbage').key; store.setQty(key,3); store=app.render(); assert.equal(store.cart.find(line=>line.sabjiChoice==='Potato').qty,2); assert.equal(store.cartTotal,225); store.setQty(key,0); store=app.render(); assert.equal(store.cart.length,1); assert.equal(store.cart[0].sabjiChoice,'Potato'); assert.equal(store.cart[0].qty,2);
  });
  await check('Actual checkout refreshes lunch then sends choice/revision without client price', async () => {
    const calls=[]; const app=harness({createOrder:async(items,method,key)=>{calls.push({items,method,key});return {id:'o1',orderId:1,items:[],payment:'Paid'};}}); await app.login(); app.render().add(chapati,2,'Potato'); let fresh=0; app.api.getLunchMenu=async()=>{fresh++;return structuredClone(lunch);};
    await app.render().submitOrder('wallet'); assert.ok(fresh>=1); assert.equal(calls.length,1); assert.equal(calls[0].method,'wallet'); assert.equal(calls[0].key,'lunch-test-key'); assert.equal(JSON.stringify(calls[0].items),JSON.stringify([{id:h.CHAPATI_BHAJI_ID,qty:2,mealRevision:'rev-a',sabjiChoice:'Potato'}])); assert.equal(app.render().cart.length,0);
  });
  await check('Actual checkout rejects stale meal before order/payment creation', async () => {
    let created=0;const app=harness({createOrder:async()=>{created++;throw Error('Should not create');}}); await app.login(); app.render().add(thali); app.api.getLunchMenu=async()=>({...structuredClone(lunch),mealRevision:'rev-b'});
    await assert.rejects(app.render().submitOrder('wallet'),/changed/); assert.equal(created,0); assert.equal(app.render().cart[0].item.lunch.revision,'rev-a'); assert.equal(app.render().cartTotal,80);
  });
  await check('Actual Aloo-only checkout sends available choice at the current revision', async () => {
    const calls=[]; const app=harness({getLunchMenu:async()=>structuredClone(alooLunch),createOrder:async(items)=>{calls.push(items);return {id:'aloo-order',orderId:2,items:[],payment:'Paid'};}}); await app.login(); assert.equal(app.render().add(alooChapati,1,'Aloo'),true); assert.equal(app.render().cartTotal,45);
    await app.render().submitOrder('wallet'); assert.equal(calls.length,1); assert.equal(JSON.stringify(calls[0]),JSON.stringify([{id:h.CHAPATI_BHAJI_ID,qty:1,mealRevision:'rev-aloo',sabjiChoice:'Aloo'}]));
  });
  await check('Actual checkout rejects Paneer cart when availability changes before payment', async () => {
    let created=0; const app=harness({getLunchMenu:async()=>structuredClone(paneerLunch),createOrder:async()=>{created++;throw Error('Should not create');}}); await app.login(); const item=app.render().menu.find(item=>item.id===h.CHAPATI_BHAJI_ID); assert.equal(app.render().add(item,1,'Paneer'),true);
    app.api.getLunchMenu=async()=>structuredClone(alooLunch); await assert.rejects(app.render().submitOrder('wallet'),/changed/); assert.equal(created,0); assert.equal(app.render().cart[0].sabjiChoice,'Paneer'); assert.equal(app.render().cartTotal,45);
  });
  await check('Background refresh preserves old contents and separate meal cart lines', async () => {
    const app=harness(); await app.login(); app.render().add(chapati,1,'Cabbage'); app.render().add(chapati,1,'Potato'); app.api.getLunchMenu=async()=>({...structuredClone(lunch),mealRevision:'rev-b',contents:['New meal'],sabjiOptions:['Peas','Beans']}); await app.render().refresh();const store=app.render(); assert.equal(store.cart.length,2); assert.equal(store.cart[0].item.lunch.revision,'rev-a'); assert.equal(store.cart[0].item.lunch.contents.join('|'),lunch.contents.join('|'));assert.match(h.lunchCartError(store.cart,store.lunch),/changed/);
  });
  await check('Actual Home and Menu keep both closed lunch cards visible', async () => {
    const app=harness({getLunchMenu:async()=>({...structuredClone(lunch),available:false,unavailableReason:'Lunch closed'})});await app.login();for(const name of ['HomeScreen','MenuScreen']) {const cards=nodes(view(app,name)).filter(node=>node.type?.name==='FoodCardWide'&&node.props.item.lunch);assert.equal(cards.length,2);assert.ok(cards.every(node=>node.props.item.available===false));}
  });
  await check('Order details render immutable contents, choice and meal date', async () => {
    const app=harness();await app.login();app.render().selectOrder({id:'old',number:'#1',status:'Completed',payment:'Paid',createdAt:'2026-10-14T07:00:00Z',items:[{id:h.CHAPATI_BHAJI_ID,name:'Chapati Bhaji',qty:1,price:45,contents:['3 chapatis','Salad','Old sabji'],sabjiChoice:'Old sabji',mealDate:'2026-10-14',mealType:'lunch'}],itemTotal:45,packagingFee:0,gst:0,total:45,paymentMethod:'wallet',pickupCounter:'A'}); const page=view(app,'OrderDetailsScreen');assert.match(text(page),/Old sabji/);assert.match(text(page),/3 chapatis.*Salad.*Old sabji/);assert.match(text(page),/2026-10-14.*lunch/);assert.doesNotMatch(text(page),/Cabbage/);
  });
  console.log(`Student lunch checks passed: ${passed}. No network, database, deployment or APK changes performed.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
