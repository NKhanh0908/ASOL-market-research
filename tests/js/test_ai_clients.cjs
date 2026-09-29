const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the actual client script with a minimal event-driven DOM, no browser/network.
class Element {
  constructor() { this.events = {}; this.dataset = {}; this.children = []; this.disabled = false; this.open = false; }
  addEventListener(name, handler) { (this.events[name] ??= []).push(handler); }
  async fire(name) { await Promise.all((this.events[name] ?? []).map(handler => handler())); }
  showModal() { this.open = true; }
  close() { this.open = false; return this.fire('close'); }
  focus() { this.focused = true; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  set innerHTML(_) { throw new Error('Untrusted content must not use innerHTML'); }
}

const ready = () => ({state:'ready', quote:'signed', scope:{analysis_date:'2026-09-25', markets:['vn']},
  provider_id:'fake', model_id:'fixture', max_output_tokens:2000, timeout_seconds:60,
  cost_mode:'free_tier', free_tier_confirmed:true, attempts_remaining:5, warnings:['<script>unsafe</script>']});

function dashboard(respond) {
  const elements = Object.fromEntries(['create','confirm','submit','cancel','unknown','unknown-label','warning',
    'feedback','inspect-history','scope','provider','limits','cost','attempts','coverage'].map(id => ['ai-'+id,new Element()]));
  elements['ai-create'].dataset = {date:'2026-09-25', market:'vn', csrf:'token'};
  const calls = [], visits = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/casual_scout/web/static/recommendations.js'),'utf8'), {
    document:{getElementById:id=>elements[id], createElement:()=>new Element()},
    window:{location:{assign:url=>visits.push(url)}},
    fetch:async (url,options)=>{ calls.push({url,...options}); return respond(url,options); }
  });
  return {elements,calls,visits};
}
const response = data => ({ok:true,json:async()=>data});

test('load is inert; explicit preflight binds scope and cancellation performs no dispatch', async()=>{
  const {elements:e,calls,visits} = dashboard(()=>response(ready()));
  assert.equal(calls.length,0);
  await e['ai-create'].fire('click');
  assert.deepEqual(JSON.parse(calls[0].body),{analysis_date:'2026-09-25',market:'vn'});
  assert.equal(calls[0].headers['X-CSRF-Token'],'token');
  assert.equal(e['ai-submit'].disabled,true);
  assert.equal(e['ai-coverage'].children[0].textContent,'<script>unsafe</script>');
  await e['ai-cancel'].fire('click');
  await e['ai-submit'].fire('click');
  assert.equal(calls.length,1);
  assert.equal(visits.length,0);
  assert.equal(e['ai-create'].focused,true);
});

test('consent and double click dispatch exactly once', async()=>{
  let finish;
  const {elements:e,calls,visits} = dashboard(url=>url.endsWith('preflight') ? response(ready()) : new Promise(resolve=>{finish=resolve;}));
  await e['ai-create'].fire('click');
  await e['ai-submit'].fire('click');
  assert.equal(calls.length,1);
  e['ai-unknown'].checked=true;
  await e['ai-unknown'].fire('change');
  const first=e['ai-submit'].fire('click');
  await e['ai-submit'].fire('click');
  assert.equal(calls.length,2);
  assert.deepEqual(JSON.parse(calls[1].body),{quote:'signed',confirm_unknown:true});
  finish(response({run_id:'run/1'}));
  await first;
  assert.deepEqual(visits,['/recommendations/run%2F1']);
});

test('ambiguous submit consumes quote without automatic retry', async()=>{
  const {elements:e,calls,visits} = dashboard(url=>{
    if(url.endsWith('preflight')) return response(ready());
    throw new Error('Connection lost');
  });
  await e['ai-create'].fire('click');
  e['ai-unknown'].checked=true;
  await e['ai-unknown'].fire('change');
  await e['ai-submit'].fire('click');
  await e['ai-submit'].fire('click');
  assert.equal(calls.length,2);
  assert.equal(visits.length,0);
  assert.equal(e['ai-inspect-history'].hidden,false);
  assert.match(e['ai-feedback'].textContent,/Connection lost/);
});

test('Escape ignores a late preflight and reopening needs a new quote', async()=>{
  let finish;
  const {elements:e,calls} = dashboard(()=>new Promise(resolve=>{finish=resolve;}));
  const opening=e['ai-create'].fire('click');
  await e['ai-confirm'].fire('cancel');
  await e['ai-confirm'].close(); // Native Escape closes after cancel event.
  finish(response(ready()));
  await opening;
  e['ai-unknown'].checked=true;
  await e['ai-submit'].fire('click');
  assert.equal(calls.length,1);
  assert.equal(e['ai-submit'].disabled,true);
});

test('unattested or exhausted policy cannot enable confirmation', async()=>{
  for(const policy of [{free_tier_confirmed:false},{attempts_remaining:0},{max_output_tokens:2001}]) {
    const {elements:e,calls}=dashboard(()=>response({...ready(),...policy}));
    await e['ai-create'].fire('click');
    e['ai-unknown'].checked=true;
    await e['ai-submit'].fire('click');
    assert.equal(calls.length,1);
    assert.equal(e['ai-submit'].disabled,true);
  }
});

test('metered injected policy follows its positive cap without the Free Tier token ceiling', async()=>{
  const {elements:e,calls}=dashboard(()=>response({...ready(),cost_mode:'metered',max_output_tokens:4000,
    max_cost_per_run_usd:'0.10',free_tier_confirmed:false,attempts_remaining:null}));
  await e['ai-create'].fire('click');
  e['ai-unknown'].checked=true;
  await e['ai-unknown'].fire('change');
  assert.equal(e['ai-submit'].disabled,false);
  assert.equal(calls.length,1);
});
