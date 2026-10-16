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
  const api = { hasSession: () => false, getMenu: async () => [meal], getDinnerMenu: async () => ({ date: '2026-10-15', day: 'Thursday', mealType: 'dinner', available: false, unavailableReason: 'Dinner unconfigured', mealRevision: null, contents: [], sabjiOptions: [], options: [] }), getLunchMenu: async () => ({ date: '2026-10-15', day: 'Thursday', mealType: 'lunch', available: false, unavailableReason: 'Lunch unconfigured', mealRevision: null, contents: [], sabjiOptions: [], options: [] }), getOrders: async () => [], getNotifications: async () => [], getMe: async () => ({ success: true, user }), login: async () => ({ success: true, user }), logout: async () => {}, ...overrides };
  const app = load('student/src/App.tsx', {
    react: runtime.react, '../../src/lib/apiClient': { apiClient: api, STUDENT_SESSION_EXPIRED: 'expired' },
    '../../src/lib/paymentCheckout': { checkoutIntent: () => 'lunch-test-key', clearCheckoutIntent() {} }, '../../src/lib/studentLunch': load('src/lib/studentLunch.ts', {}), '../../src/components/FoodImage': { default: function FoodImage() {} },
    '../../src/components/FoodPhotoCredits': { default: function FoodPhotoCredits() {} },
  }, { setTimeout: () => 1, clearTimeout() {}, setInterval: runtime.setInterval, clearInterval: runtime.clearInterval,
    document: { visibilityState: 'visible' }, window: { addEventListener() {}, removeEventListener() {} } }, '\nexport { HomeScreen, MenuScreen, DetailsScreen, CartScreen, OrderDetailsScreen, FoodCardWide };');
  function render() { runtime.begin('App'); runtime.store = app.default().props.value; runtime.commit(); return runtime.store; }
  const mounted = { app, api, runtime, render, login: async () => { await render().loginUser('ROLL', 'PASS'); render(); await tick(); return render(); } };
  render(); return mounted;
}

const h = load('src/lib/studentLunch.ts', {});
const lunch = { date: '2026-10-15', day: 'Thursday', mealType: 'lunch', available: true, unavailableReason: null, mealRevision: 'rev-a', contents: ['Rice','Dal','Chapati','Salad','Cabbage','Potato'], sabjiOptions: ['Cabbage','Potato'], options: [{id:h.CHAPATI_BHAJI_ID,name:'Chapati Bhaji',price:45},{id:h.THALI_ID,name:'Thali',price:80}] };
const [chapati, thali] = h.lunchItems(lunch);
const dinner = { ...lunch, mealType: 'dinner', currentMealType: 'dinner', serviceWindow: '19:30 - 22:30', mealRevision: 'dinner-rev', contents: ['3 chapatis', 'Salad', 'Rice', 'Dal', 'Beans', 'Peas'], sabjiOptions: ['Beans', 'Peas'], options: [{ id: h.DINNER_CHAPATI_BHAJI_ID, name: 'Chapati Bhaji', price: 45 }, { id: h.DINNER_THALI_ID, name: 'Thali', price: 80 }] };
const [dinnerChapati, dinnerThali] = h.lunchItems(dinner);
const paneerLunch = { ...lunch, contents: ['3 chapatis','Salad','Paneer','Aloo'], sabjiOptions: ['Paneer','Aloo'] };
const alooLunch = { ...paneerLunch, mealRevision: 'rev-aloo', contents: ['3 chapatis','Salad','Aloo'], sabjiOptions: ['Aloo'] };
const [alooChapati, alooThali] = h.lunchItems(alooLunch);
const harness = (overrides = {}) => appHarness({ getLunchMenu: async () => structuredClone(lunch), ...overrides });
function view(app, name, props) { app.render(); app.runtime.begin(name); return app.app[name](props); }
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
  await check('Home removes every meal summary and selector while preserving other content and navigation', async () => {
    const app=harness({getDinnerMenu:async()=>structuredClone(dinner)});await app.login();const home=view(app,'HomeScreen'),all=nodes(home);
    assert.equal(all.filter(node=>node.type?.name==='LunchNotice').length,0);
    assert.equal(all.filter(node=>node.type?.name==='FoodCardWide'&&node.props.item.lunch).length,0);
    assert.ok(all.some(node=>node.type?.name==='SearchBar'));
    assert.match(text(home),/Good afternoon.*Hey,.*Student.*Main Block Canteen/);
    assert.match(text(home),/Snacks.*Meals.*Beverages.*Quick Bites.*Beat the 1 PM rush.*Order ahead.*Popular today.*See all/);
    assert.doesNotMatch(text(home),/Today.s lunch|Today.s dinner|Chapati Bhaji|Thali|19:30|Lunch closed/);
    assert.ok(all.some(node=>node.type?.name==='FoodCardWide'&&node.props.item.id===meal.id));
    all.find(node=>node.type==='button'&&text(node).includes('Meals')).props.onClick();assert.equal(app.render().menuCategory,'Meals');assert.equal(app.render().screen,'menu');
  });
  await check('Closed meal cards are hidden from Menu while available catalogue records remain', async () => {
    const app=harness({getLunchMenu:async()=>({...structuredClone(lunch),available:false,unavailableReason:'Lunch closed'}),getDinnerMenu:async()=>({...structuredClone(dinner),available:false,unavailableReason:'Dinner unconfigured'})});await app.login();
    const cards=nodes(view(app,'MenuScreen')).filter(node=>node.type?.name==='FoodCardWide');assert.equal(cards.length,1);assert.equal(cards[0].props.item.id,meal.id);
    assert.equal(app.render().add(chapati,1,'Potato'),false);assert.equal(app.render().add(dinnerThali),false);assert.equal(app.render().cart.length,0);
  });
  await check('Order details render immutable contents, choice and meal date', async () => {
    const app=harness();await app.login();app.render().selectOrder({id:'old',number:'#1',status:'Completed',payment:'Paid',createdAt:'2026-10-14T07:00:00Z',items:[{id:h.CHAPATI_BHAJI_ID,name:'Chapati Bhaji',qty:1,price:45,contents:['3 chapatis','Salad','Old sabji'],sabjiChoice:'Old sabji',mealDate:'2026-10-14',mealType:'lunch'}],itemTotal:45,packagingFee:0,gst:0,total:45,paymentMethod:'wallet',pickupCounter:'A'}); const page=view(app,'OrderDetailsScreen');assert.match(text(page),/Old sabji/);assert.match(text(page),/3 chapatis.*Salad.*Old sabji/);assert.match(text(page),/2026-10-14.*lunch/);assert.doesNotMatch(text(page),/Cabbage/);
  });
  await check('Dinner shares helpers while retaining independent IDs, contents and cart keys', () => {
    assert.equal(dinnerChapati.price,45); assert.equal(dinnerThali.price,80); assert.equal(dinnerThali.lunch.mealType,'dinner');
    assert.equal(h.lunchContents(dinnerThali).join('|'),dinner.contents.join('|'));
    assert.notEqual(h.lunchLineKey(chapati,'Potato'),h.lunchLineKey(dinnerChapati,'Potato'));
    assert.equal(h.mealCartError([{item:chapati,sabjiChoice:'Potato'},{item:dinnerChapati,sabjiChoice:'Beans'}],lunch,dinner),null);
    assert.match(h.mealCartError([{item:dinnerChapati,sabjiChoice:'Potato'}],lunch,dinner),/exactly one/);
    assert.match(h.mealCartError([{item:dinnerThali}],lunch,null),/Dinner could not be verified/);
  });
  await check('All and Meals show both independently configured periods as regular cards without separate tabs or sections', async () => {
    const app=harness({getDinnerMenu:async()=>structuredClone(dinner)});await app.login();
    for(const category of ['All','Meals']) {
      app.render().setMenuCategory(category);const page=view(app,'MenuScreen'),all=nodes(page),cards=all.filter(node=>node.type?.name==='FoodCardWide');
      assert.equal(cards.length,5);assert.equal(cards.filter(node=>node.props.item.lunch).length,4);assert.ok(cards.every(node=>node.props.item.category==='Meals'));
      for(const id of [h.CHAPATI_BHAJI_ID,h.THALI_ID,h.DINNER_CHAPATI_BHAJI_ID,h.DINNER_THALI_ID]) assert.ok(cards.some(node=>node.props.item.id===id));
      assert.equal(all.filter(node=>node.type?.name==='LunchNotice').length,0);
      assert.equal(all.filter(node=>node.props?.['aria-label']==='Choose meal period'||node.props?.['aria-label']==='Meal period').length,0);
      assert.equal(all.filter(node=>node.type==='button'&&['Lunch','Dinner'].includes(text(node).trim())).length,0);
      assert.doesNotMatch(text(page),/Today.s lunch|Today.s dinner|Chapati Bhaji · Thali/);
    }
  });
  await check('Menu search and other categories include matching bundles without leaking them into unrelated categories', async () => {
    const snack={...meal,id:'snack',name:'Samosa',category:'Snacks',price:25};const app=harness({getMenu:async()=>[meal,snack],getDinnerMenu:async()=>structuredClone(dinner)});await app.login();
    let page=view(app,'MenuScreen');nodes(page).find(node=>node.type==='input').props.onChange({target:{value:' Chapati Bhaji '}});
    page=view(app,'MenuScreen');let cards=nodes(page).filter(node=>node.type?.name==='FoodCardWide');assert.equal(cards.length,2);assert.ok(cards.every(node=>node.props.item.name==='Chapati Bhaji'));
    nodes(page).find(node=>node.type==='input').props.onChange({target:{value:'beans'}});page=view(app,'MenuScreen');cards=nodes(page).filter(node=>node.type?.name==='FoodCardWide');assert.equal(cards.length,1);assert.equal(cards[0].props.item.id,h.DINNER_THALI_ID);
    nodes(page).find(node=>node.type==='input').props.onChange({target:{value:''}});app.render().setMenuCategory('Snacks');page=view(app,'MenuScreen');cards=nodes(page).filter(node=>node.type?.name==='FoodCardWide');assert.equal(cards.length,1);assert.equal(cards[0].props.item.id,'snack');
    app.render().setMenuCategory('Beverages');assert.equal(nodes(view(app,'MenuScreen')).filter(node=>node.type?.name==='FoodCardWide').length,0);
    app.render().setMenuCategory('Meals');assert.equal(nodes(view(app,'MenuScreen')).filter(node=>node.type?.name==='FoodCardWide').length,5);
  });
  await check('Aloo-only lunch remains listed at 45 while disabled dinner stays hidden and selection is required', async () => {
    const app=harness({getLunchMenu:async()=>structuredClone(alooLunch),getDinnerMenu:async()=>({...structuredClone(dinner),available:false})});await app.login();const cards=nodes(view(app,'MenuScreen')).filter(node=>node.type?.name==='FoodCardWide');
    assert.equal(cards.length,3);const option=cards.find(node=>node.props.item.id===h.CHAPATI_BHAJI_ID).props.item;assert.equal(option.price,45);assert.equal(option.lunch.sabjiOptions.join('|'),'Aloo');assert.equal(app.render().add(option),false);assert.equal(app.render().add(option,1,'Paneer'),false);assert.equal(app.render().add(option,1,'Aloo'),true);assert.equal(app.render().cartTotal,45);
  });
  await check('Background meal request failure hides only that period and preserves independent available cards', async () => {
    const app=harness({getDinnerMenu:async()=>structuredClone(dinner)});await app.login();app.api.getLunchMenu=async()=>{throw Error('Lunch network unavailable');};await app.render().refresh();let cards=nodes(view(app,'MenuScreen')).filter(node=>node.type?.name==='FoodCardWide'&&node.props.item.lunch);assert.equal(cards.length,2);assert.ok(cards.every(node=>node.props.item.id.startsWith('dinner-')));
    app.api.getLunchMenu=async()=>structuredClone(lunch);await app.render().refresh();cards=nodes(view(app,'MenuScreen')).filter(node=>node.type?.name==='FoodCardWide'&&node.props.item.lunch);assert.equal(cards.length,4);
  });
  await check('Shared regular meal cards open choice details and keep direct Thali add interaction', async () => {
    const app=harness({getDinnerMenu:async()=>structuredClone(dinner)});await app.login();const card=view(app,'FoodCardWide',{item:app.render().menu.find(item=>item.id===h.DINNER_CHAPATI_BHAJI_ID)});
    assert.match(text(card),/Chapati Bhaji.*45.*Dinner.*Choose sabji/);nodes(card).find(node=>node.type==='button'&&text(node).includes('Choose sabji')).props.onClick();assert.equal(app.render().screen,'details');assert.equal(app.render().cart.length,0);
    const details=view(app,'DetailsScreen'),radios=nodes(details).filter(node=>node.type==='input'&&node.props.type==='radio');assert.equal(radios.length,2);assert.equal(radios.map(node=>node.props.value).join('|'),'Beans|Peas');assert.equal(nodes(details).find(node=>node.type?.name==='Button'&&text(node).includes('Add')).props.disabled,true);
    const thaliCard=view(app,'FoodCardWide',{item:app.render().menu.find(item=>item.id===h.THALI_ID)});nodes(thaliCard).find(node=>node.type==='button'&&text(node).includes('Add')).props.onClick();assert.equal(app.render().cart.length,1);assert.equal(app.render().cart[0].item.id,h.THALI_ID);assert.equal(app.render().cartTotal,80);
  });
  await check('Dinner Details requires its own sabji, sends dinner revision and keeps lunch snapshot', async () => {
    const calls=[]; const app=harness({getDinnerMenu:async()=>structuredClone(dinner),createOrder:async(items)=>{calls.push(items);return {id:'d1',orderId:8,items:[],payment:'Paid'};}}); await app.login();
    app.render().select(app.render().menu.find(item=>item.id===h.DINNER_CHAPATI_BHAJI_ID)); let page=view(app,'DetailsScreen');
    const radios=nodes(page).filter(node=>node.type==='input'&&node.props.type==='radio'); assert.equal(radios.length,2); assert.ok(radios.every(node=>!node.props.checked));
    assert.equal(nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')).props.disabled,true);
    radios.find(node=>node.props.value==='Beans').props.onChange(); page=view(app,'DetailsScreen'); nodes(page).find(node=>node.type?.name==='Button'&&text(node).includes('Add')).props.onClick();
    assert.equal(app.render().cartTotal,45); await app.render().submitOrder('wallet'); assert.equal(JSON.stringify(calls[0]),JSON.stringify([{id:h.DINNER_CHAPATI_BHAJI_ID,qty:1,mealRevision:'dinner-rev',sabjiChoice:'Beans'}])); assert.equal(chapati.lunch.revision,'rev-a');
  });
  await check('Mixed-period checkout refreshes both APIs and rejects stale dinner without creating payment', async () => {
    let created=0,lunchReads=0,dinnerReads=0;const app=harness({getDinnerMenu:async()=>structuredClone(dinner),createOrder:async()=>{created++;throw Error('Should not create');}}); await app.login(); app.render().add(chapati,1,'Potato'); app.render().add(dinnerThali);
    assert.equal(app.render().cart.length,2); app.api.getLunchMenu=async()=>{lunchReads++;return structuredClone(lunch);}; app.api.getDinnerMenu=async()=>{dinnerReads++;return {...structuredClone(dinner),mealRevision:'changed-dinner'};};
    await assert.rejects(app.render().submitOrder('wallet'),/dinner menu has changed/); assert.ok(lunchReads>=1); assert.ok(dinnerReads>=1); assert.equal(created,0); assert.equal(app.render().cart.length,2); assert.equal(app.render().cart[1].item.lunch.revision,'dinner-rev');
  });
  await check('Dinner with no sabji disables only Chapati and leaves configured Thali orderable', async () => {
    const noSabji={...structuredClone(dinner),sabjiOptions:[],options:[{...dinner.options[0],available:false,unavailableReason:'No dinner sabji available'},dinner.options[1]]};
    const [blocked,allowed]=h.lunchItems(noSabji); assert.equal(blocked.available,false); assert.equal(allowed.available,true); assert.equal(h.mealCartError([{item:allowed}],lunch,noSabji),null); assert.match(h.mealCartError([{item:blocked}],lunch,noSabji),/No dinner sabji/);
  });
  console.log(`Student lunch/dinner checks passed: ${passed}. No network, database, deployment or APK changes performed.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
