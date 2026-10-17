// Execute the production helper with explicit instants; independent of the laptop timezone.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const repo = path.resolve(__dirname, '..');
const ts = require(path.join(repo, 'node_modules/typescript'));
const exportsObject = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(repo,'src/lib/studentRush.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,{exports:exportsObject,Intl,Number,String});
const {nextRush}=exportsObject;
let passed=0;
const check=(name,run)=>{run();passed++;console.log('PASS '+name);};
const at=time=>new Date(`2026-10-16T${time}+05:30`);
const title=time=>nextRush(at(time))?.title??null;
for(const [time,expected] of [
  ['09:59:00',null],['10:00:00','Beat the 12 PM lunch rush'],
  ['11:59:00','Beat the 12 PM lunch rush'],['12:00:00',null],
  ['17:59:00',null],['18:00:00','Beat the 7 PM dinner rush'],
  ['18:59:00','Beat the 7 PM dinner rush'],['19:00:00',null],['21:49:00',null],
]) check(`Required IST boundary ${time}: ${expected||'no banner'}`,()=>assert.equal(title(time),expected));
check('Seconds around each boundary follow the same half-open windows',()=>{
  assert.equal(title('09:59:59'),null);assert.match(title('10:00:01'),/lunch/);
  assert.match(title('11:59:59'),/lunch/);assert.equal(title('12:00:01'),null);
  assert.equal(title('17:59:59'),null);assert.match(title('18:00:01'),/dinner/);
  assert.match(title('18:59:59'),/dinner/);assert.equal(title('19:00:01'),null);
});
check('Every minute of the IST day shows only the required lunch/dinner lead-in windows',()=>{
  for(let minute=0;minute<1440;minute++){
    const current=at(`${String(Math.floor(minute/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}:00`),value=nextRush(current);
    const expected=minute>=600&&minute<720?'lunch':minute>=1080&&minute<1140?'dinner':null;
    assert.equal(value?.meal??null,expected,String(minute));if(value)assert.doesNotMatch(value.title,/tomorrow/i);
  }
});
check('Service metadata cannot extend promotional windows or replace the requested banner time',()=>{
  for(const schedule of [{serviceStart:'19:30'},{serviceWindow:'20:00 - 23:00'},{serviceStart:'99:99'}]){
    assert.equal(nextRush(at('18:30:00'),null,schedule).title,'Beat the 7 PM dinner rush');
    assert.equal(nextRush(at('21:49:00'),null,schedule),null);assert.equal(nextRush(at('16:00:00'),null,schedule),null);
  }
});
check('UTC and IST representations of the same instant produce identical output',()=>assert.equal(JSON.stringify(nextRush(new Date('2026-10-16T05:00:00Z'))),JSON.stringify(nextRush(at('10:30:00')))));
check('Host timezone never changes IST banner visibility',()=>{
  const prior=process.env.TZ;
  try{for(const timezone of ['America/Los_Angeles','UTC','Asia/Tokyo']){process.env.TZ=timezone;assert.equal(nextRush(new Date('2026-10-16T05:00:00Z')).meal,'lunch');assert.equal(nextRush(new Date('2026-10-16T16:19:00Z')),null);}}
  finally{if(prior===undefined)delete process.env.TZ;else process.env.TZ=prior;}
});
console.log(`Student rush checks passed: ${passed}.`);
