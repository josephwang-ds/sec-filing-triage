// Run with jsdom available: node tests/browser/history_interactions.cjs healthy.html sparse.html
// Fixtures are rendered by Python from the deterministic benchmark test data.
const {JSDOM, VirtualConsole} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');

async function check(path, available) {
  const errors = [], requests = [];
  const console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(fs.readFileSync(path, 'utf8'), {
    url: 'https://lens.test/abc.html', runScripts: 'dangerously', virtualConsole: console,
    beforeParse(window) {
      window.fetch = async (url, options) => {
        requests.push({url, method: options?.method || 'GET'});
        return {ok: true, json: async () => ({
          models: [{id: 'test', provider: 'Test', model: 'fixture'}],
          scopes: [{id: 'core', label: 'Core'}], default_scope: 'core',
        })};
      };
    },
  });
  try {
    await new Promise(resolve => setImmediate(resolve));
    const window = dom.window, document = window.document;
    const element = selector => document.querySelector(selector);
    assert.deepEqual(errors, [], 'page initialization must work');
    assert.equal(element('[data-benchmark="QQQ"]').disabled, !available);
    assert.match(element('#relative-copy').textContent, /percentage points/);
    assert.match(element('#history-return-comparison').textContent, /SPY:.*cumulative return/);
    const briefReturn = element('#total-return').textContent;
    const spyEnding = element('#benchmark-ending').textContent;
    if (available) {
      element('[data-benchmark="QQQ"]').click();
      assert.equal(element('#legend-benchmark').textContent, 'QQQ');
      assert.match(element('#history-return-comparison').textContent, /QQQ:/);
      assert.equal(element('#total-return').textContent, briefReturn);
      assert.notEqual(element('#benchmark-ending').textContent, spyEnding);
      assert.match(element('#benchmark-note').textContent, /stay on SPY/);
    }
    element('#ask-question').value = 'Keep my edited question';
    element('#language-toggle').click();
    assert.equal(document.documentElement.lang, 'zh-CN');
    assert.match(element('#relative-copy').textContent, /个百分点/);
    assert.match(element('#history-return-comparison').textContent, /累计回报/);
    assert.equal(element('#legend-benchmark').textContent, available ? 'QQQ' : 'SPY');
    assert.equal(element('#ask-question').value, 'Keep my edited question');
    element('[data-period="1Y"]').click();
    assert.equal(element('[data-period="1Y"]').getAttribute('aria-pressed'), 'true');
    element('[data-benchmark="SPY"]').click();
    assert.equal(element('#legend-benchmark').textContent, 'SPY');
    element('[data-ask-task="risk"]').focus();
    function arrow(key) {
      document.activeElement.dispatchEvent(new window.KeyboardEvent('keydown', {key, bubbles: true}));
    }
    arrow('ArrowRight');
    assert.equal(element('.ask-more-tasks').open, true);
    assert.equal(document.activeElement.dataset.askTask, 'limits');
    assert.equal(document.activeElement.getAttribute('aria-selected'), 'true');
    arrow('ArrowRight');
    assert.equal(document.activeElement.dataset.askTask, 'quality');
    arrow('ArrowLeft');
    assert.equal(document.activeElement.dataset.askTask, 'limits');
    arrow('ArrowLeft');
    assert.equal(document.activeElement.dataset.askTask, 'risk');
    element('[data-ask-task="filing"]').click();
    assert.equal(document.activeElement.id, 'ask-question', 'clicking still focuses the draft');
    assert.equal(element('#ask-submit').disabled, false, 'question controls initialize');
    const resultsLink = element('[data-ask-task-link="results"]');
    if (resultsLink) {
      resultsLink.click();
      assert.equal(element('.ask-more-tasks').open, true);
      assert.match(element('#ask-question').value, /最新财报/);
      assert.equal(element('[data-ask-task="results"]').getAttribute('aria-selected'), 'true');
    }
    assert.equal(requests.filter(request => request.method === 'POST').length, 0);
    assert.deepEqual(errors, []);
  } finally {
    dom.window.close();
  }
}

(async () => {
  const [healthy, sparse] = process.argv.slice(2);
  assert.ok(healthy && sparse, 'Pass healthy and two-shared-session rendered fixture paths');
  await check(healthy, true);
  await check(sparse, false);
  console.log('PASS: healthy/sparse initialization, benchmark/period/language, draft preservation, keyboard focus, zero POST requests');
})().catch(error => {console.error(error); process.exitCode = 1;});
