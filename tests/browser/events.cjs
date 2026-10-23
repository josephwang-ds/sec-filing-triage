// Execute the actual rendered inline client. No live data or model requests.
const {JSDOM} = require('jsdom');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const initial = {ticker:'AAPL', storage:'build_snapshot', status:'current',
  manifest_version:'old', events:[], checked_at:'2026-10-20T00:00:00Z'};
const html = execFileSync(process.env.PYTHON || 'python', ['-c',
  'import json,sys; from company_lens.events.render import render_preview_page; print(render_preview_page(json.loads(sys.argv[1])))',
  JSON.stringify(initial)], {encoding:'utf8'});
const events = Array.from({length:5}, (_,i)=>({id:'event'+i, title:'Title '+i,
  publisher:'Publisher', manifest_version:'new', ask_enabled:true, title_only:true,
  excerpt:'Excerpt '+i, precision_note:{en:'Date only',zh:'仅日期'},
  significance:{en:'Context',zh:'背景'}, source_url:'https://example.com/'+i}));
const feed = {...initial, storage:'blob', manifest_version:'new', status:'partial',
  status_label:{en:'Partial coverage',zh:'覆盖不完整'}, checked_at:'2026-10-23T00:00:00Z',
  coverage_gaps:[{start:'2026-10-01',end:'2026-10-02',reason:'lookback'}], events};
const tick = () => new Promise(resolve=>setTimeout(resolve,20));
async function open(value, fail=false) {
  const calls=[];
  const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://example.com/?lang=zh',
    beforeParse(window) { window.fetch=async (url, opts)=>{
      calls.push({url,opts});
      if(url==='/api/ask') return {ok:true,json:async()=>({answer:[{text:'Answer',citations:[{id:'S1',label:'Source',url:'https://example.com/evidence'}]}],boundaries:[{text:'Cannot infer causation',citations:[]}]})};
      if(fail) throw new Error('network');
      return {ok:true,json:async()=>value};
    }; }});
  await tick(); return {dom,document:dom.window.document,calls};
}
(async()=>{
  const {dom,document:d,calls}=await open(feed);
  assert.equal(d.querySelector('[data-status]').dataset.status,'partial');
  assert.match(d.querySelector('.events-freshness').textContent,/2026-10-23/);
  assert.equal(d.querySelectorAll('.event-card').length,5);
  assert.equal(d.querySelectorAll('.event-list .event-card').length,3);
  assert.equal(d.querySelectorAll('.events-more .event-card').length,2);
  assert.equal(d.querySelector('.event-ask').textContent,'让 AI 解读此事件');
  assert.equal(d.querySelector('.event-badge').textContent,'仅标题');
  assert.equal(d.querySelector('.event-precision').textContent,'仅日期');
  assert.match(d.querySelector('.event-card').textContent,/Excerpt 0/);
  d.getElementById('language-toggle').click();
  assert.match(d.querySelector('.events-gap').textContent,/2026-10-01/);
  assert.equal(d.querySelector('.event-ask').textContent,'Ask AI about this event');
  const button=d.querySelector('.events-more .event-ask'); button.click(); button.click();
  await tick();
  assert.equal(calls.filter(x=>x.url==='/api/ask').length,1);
  const request=JSON.parse(calls.find(x=>x.url==='/api/ask').opts.body);
  assert.equal(request.event_version,'new'); assert.equal(request.event_id,'event3');
  const result=d.querySelector('.events-more .event-ask-result');
  assert.match(result.textContent,/Cannot infer causation/);
  assert.equal(result.querySelector('a').href,'https://example.com/evidence');
  dom.window.close();
  const same=await open({...feed,manifest_version:'old',status:'stale',status_label:{en:'Stale',zh:'已过期'}});
  assert.equal(same.document.querySelector('[data-status]').dataset.status,'stale');
  assert.match(same.document.querySelector('.events-freshness').textContent,/2026-10-23/);
  same.dom.window.close();
  for (const fail of [false,true]) {
    const broken=await open({ticker:'AAPL',status:'unavailable',storage:'unavailable',events:[]},fail);
    assert.equal(broken.document.querySelector('[data-status]').dataset.status,'unavailable');
    assert.match(broken.document.querySelector('.events-content').textContent,/更新的事件源没有载入/);
    broken.dom.window.close();
  }
  const readError=await open({ticker:'AAPL',status:'read_error',storage:'read_error',events:[]});
  assert.equal(readError.document.querySelector('[data-status]').dataset.status,'unavailable');
  readError.dom.window.close();
  const unsafe=await open({...feed,events:[{...events[0],title:'<img src=x onerror=alert(1)>',source_url:'javascript:alert(1)'}]});
  assert.equal(unsafe.document.querySelectorAll('.event-card img,.event-actions a').length,0);
  unsafe.dom.window.close();
  console.log('Events DOM: live metadata, five cards, bilingual controls, same-version status, failure, citations, limits and safe content passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
const api = require('../../ops/vercel/events/index.js');
const checked='2026-10-23T14:00:00Z';
const base={ticker:'AAPL',coverage_tier:'high_frequency',checked_at:checked,status:'current'};
const health=api.healthFromCheckpoint({expected_tickers:['AAPL'],datasets:{news:{states:{AAPL:{key:'AAPL',last_successful_check_at:checked,status:'current'}}}}},Date.parse('2026-10-24T22:00:00Z'));
assert.equal(api.ageFeed({...base},Date.parse('2026-10-24T22:00:00Z')).status,health.sources.find(s=>s.dataset==='news').level);
