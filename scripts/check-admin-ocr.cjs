// Behavioural OCR review/progress/retry checks against the actual Admin component.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const repo = path.resolve(__dirname, '..'), ts = require(path.join(repo, 'node_modules/typescript'));
const jsx = (type, props) => ({ type, props });
const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
const text = value => typeof value === 'string' || typeof value === 'number' ? String(value) : Array.isArray(value) ? value.map(text).join(' ') : value && typeof value === 'object' ? text(value.props?.children) : '';
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };
const tick = () => new Promise(resolve => setImmediate(resolve));
const schedule = [{day:'Friday',meal_type:'dinner',items:['Actual reviewed dish','Rice']}];
function load(file, modules, globals={}) {
  const exports={};
  const source=fs.readFileSync(path.join(repo,file),'utf8').replaceAll('import.meta.env','__env');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,
    {exports,__env:{},require:name=>name==='react/jsx-runtime'?{jsx,jsxs:jsx}:modules[name]||(()=>{throw Error('Unexpected import '+name)})(),Error,Promise,console,...globals},{filename:file});
  return exports;
}
function harness(overrides={}) {
  let index=0,now=0;const slots=[],effects=[],timers=new Map(),extractions=[],saves=[],toasts=[];
  const react={useState:initial=>{const i=index++;const slot=slots[i]||=( {value:typeof initial==='function'?initial():initial} );return[slot.value,next=>{slot.value=typeof next==='function'?next(slot.value):next}];},useRef:initial=>slots[index++]||={current:initial},useEffect:(fn)=>{const i=index++;if(!slots[i]){slots[i]={};effects.push(()=>{slots[i].cleanup=fn()});}}};
  const api={extractMenu:async file=>{extractions.push(file);return{schedule:structuredClone(schedule)};},saveWeeklyMenu:async value=>{saves.push(value);return{schedule:value};},...overrides};
  class Reader { readAsDataURL(){this.onload({target:{result:'data:image/png;base64,diagnostic'}});} }
  const component=load('src/components/OcrMenuUpload.tsx',{react,'../lib/adminOperationsApi':{adminOperationsApi:api}},{FileReader:Reader,Date:{now:()=>now},setInterval:fn=>{const id=timers.size+1;timers.set(id,fn);return id;},clearInterval:id=>timers.delete(id),prompt:()=> 'Reviewed addition'}).default;
  const render=()=>{index=0;const view=component({onShowToast:(...args)=>toasts.push(args)});while(effects.length)effects.shift()();return view;};
  const choose=file=>nodes(render()).find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[file]}});
  const button=(pattern)=>nodes(render()).find(n=>n.type==='button'&&pattern.test(text(n)));
  render();return{api,render,choose,button,extractions,saves,toasts,timers,advance:ms=>{now+=ms;for(const fn of timers.values())fn();},unmount:()=>{for(const slot of slots)slot?.cleanup?.();}};
}
const file={name:'menu.png',size:100000,type:'image/png'};
let passed=0;const check=async(name,run)=>{await run();passed++;console.log('PASS '+name);};
(async()=>{
  await check('Invalid images fail before provider requests or database writes',()=>{
    const h=harness();for(const candidate of [{...file,type:'text/plain'},{...file,size:0},{...file,size:6*1024*1024}])h.choose(candidate);
    assert.match(text(h.render()),/nonempty PNG/);assert.equal(h.extractions.length,0);assert.equal(h.saves.length,0);
  });
  await check('One extraction runs at a time with truthful elapsed progress and no automatic save',async()=>{
    const pending=deferred();let count=0;const h=harness({extractMenu:()=>{count++;return pending.promise;}});h.choose(file);
    const run=h.button(/Process via OCR/).props.onClick;const first=run();run();h.advance(21000);
    assert.equal(count,1);assert.match(text(h.render()),/21s.*No menu has been saved/);assert.equal(h.saves.length,0);
    assert.equal(h.button(/Extracting Text/).props.disabled,true);pending.resolve({schedule});await first;assert.equal(h.timers.size,0);
  });
  await check('Provider timeout is retryable and cannot leave review or save stale menu entries',async()=>{
    let count=0;const h=harness({extractMenu:async()=>{if(++count===1)throw Error('The OCR provider did not finish before the extraction deadline. No menu was saved.');return{schedule};}});h.choose(file);
    await h.button(/Process via OCR/).props.onClick();assert.match(text(h.render()),/extraction deadline.*No menu was saved/);assert.equal(h.saves.length,0);assert.equal(h.timers.size,0);
    await h.button(/Process via OCR/).props.onClick();assert.equal(count,2);assert.match(text(h.render()),/Review required before saving/);assert.equal(h.saves.length,0);
  });
  await check('Review edits require explicit save, prevent simultaneous writes and disable repeated saves',async()=>{
    const pending=deferred(),saved=[];const h=harness({saveWeeklyMenu:value=>{saved.push(value);return pending.promise;}});h.choose(file);await h.button(/Process via OCR/).props.onClick();
    h.button(/Add Dish Item/).props.onClick();assert.match(text(h.render()),/Reviewed addition/);
    const save=h.button(/Confirm & Save/).props.onClick;const first=save();save();assert.equal(saved.length,1);assert.equal(saved[0][0].items.at(-1),'Reviewed addition');
    pending.resolve({schedule:saved[0]});await first;assert.equal(h.button(/Saved to Weekly Database/).props.disabled,true);await h.button(/Saved to Weekly Database/).props.onClick();assert.equal(saved.length,1);
  });
  await check('Failed saves preserve reviewed data for safe explicit retry',async()=>{
    let count=0;const h=harness({saveWeeklyMenu:async()=>{if(++count===1)throw Error('Save unavailable');return{schedule};}});h.choose(file);await h.button(/Process via OCR/).props.onClick();
    await h.button(/Confirm & Save/).props.onClick();assert.match(text(h.render()),/Save unavailable/);assert.match(text(h.render()),/Actual reviewed dish/);await h.button(/Confirm & Save/).props.onClick();assert.equal(count,2);
  });
  await check('Starting another extraction clears old review; failure cannot expose an old save',async()=>{
    const h=harness();h.choose(file);await h.button(/Process via OCR/).props.onClick();assert.match(text(h.render()),/Actual reviewed dish/);
    h.api.extractMenu=async()=>{throw Error('Provider unavailable');};await h.button(/Process via OCR/).props.onClick();assert.doesNotMatch(text(h.render()),/OCR Extraction Results/);assert.equal(h.saves.length,0);
  });
  await check('Unmount clears extraction progress timer',async()=>{
    const pending=deferred();const h=harness({extractMenu:()=>pending.promise});h.choose(file);const request=h.button(/Process via OCR/).props.onClick();assert.equal(h.timers.size,1);h.unmount();assert.equal(h.timers.size,0);pending.reject(Error('Disconnected'));await request;
  });
  await check('OCR transport timeout gives extraction-specific safe retry guidance without replaying the POST',async()=>{
    let count=0;const storage=new Map([['sco_fastapi_admin_token','test-only-admin']]);
    const api=load('src/lib/adminApi.ts',{'./apiConfig':{apiUrl:path=>'https://api.test.invalid'+path}},{FormData,AbortSignal,sessionStorage:{getItem:key=>storage.get(key),removeItem:key=>storage.delete(key)},window:{dispatchEvent(){}},CustomEvent:class{},fetch:async()=>{count++;const error=Error('Timeout');error.name='TimeoutError';throw error;}});
    await assert.rejects(api.adminRequest('/menu/upload-ocr','POST',new FormData()),error=>error.status===408&&/No menu has been saved/.test(error.message));assert.equal(count,1);
  });
  console.log(`Admin OCR checks passed: ${passed}. No network, provider calls or database changes.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
