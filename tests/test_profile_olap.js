'use strict';

const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = execFileSync(process.env.PYTHON || 'python3', ['-c', `
import inspect
from lib.dashboard.scripts_tab3 import build_scripts_part1
kw = {name: "[]" for name in inspect.signature(build_scripts_part1).parameters}
kw["jm"] = {"open_bug_by_prio": {}}
for key in ("trend_js", "tis_js", "module1_js", "module3_js", "cl_dist_js"):
    kw[key] = ""
print(build_scripts_part1(**kw))
`], {cwd: path.resolve(__dirname, '..'), encoding: 'utf8'});
const code = script.slice(script.indexOf('// ---- Tab 3: OLAP Slice'),
                          script.indexOf('// ---- Process Metrics - Trends'));

function boot(issues, links) {
  const elements = new Map();
  function get(id) {
    if (!elements.has(id)) elements.set(id, {
      value: '', innerHTML: '', textContent: '', disabled: false,
      options: [], appendChild(option) { this.options.push(option); },
    });
    return elements.get(id);
  }
  const document = {getElementById: get, createElement: () => ({})};
  const context = vm.createContext({document});
  const js = code.replace('var OLAP_ROWS = [];', `var OLAP_ROWS = ${JSON.stringify(issues)};`)
    .replace('var OLAP_LINK_ROWS = [];', `var OLAP_LINK_ROWS = ${JSON.stringify(links)};`);
  vm.runInContext(js, context);
  return {context, get};
}

test('issue OLAP pages all slices, keeps unique totals, and filters every component', () => {
  const issues = Array.from({length: 205}, (_, i) => ({
    type: 'Story', assignee: `user${i}`, priority: 'None', status: 'Open',
    components: i === 0 ? ['one', '<second>'] : ['one'], life: i === 0 ? 2 : null,
  }));
  const {context, get} = boot(issues, []);
  assert.match(get('olapSummary').textContent, /206 slice\(s\) · 205 unique issue/);
  assert.match(get('olapSummary').textContent, /showing 1–200 of 206/);
  context.olapPage(1);
  assert.match(get('olapSummary').textContent, /showing 201–206 of 206/);
  get('olapComponent').value = '<second>';
  context.olapApply();
  assert.match(get('olapSummary').textContent, /1 slice\(s\) · 1 unique issue/);
  assert.match(get('olapBody').innerHTML, /&lt;second&gt;/);
  assert.match(get('olapBody').innerHTML, /2\.0/);
  assert.equal(get('olapPrev').disabled, true);
  assert.equal(get('olapNext').disabled, true);
});

test('link OLAP pages and filters directed records independently', () => {
  const links = Array.from({length: 205}, (_, i) => ({
    link_type: `link${i}`, direction: i === 204 ? 'inward' : 'outward',
    source_type: 'Story', target_type: 'Bug', source_status: 'Open',
    target_status: 'Done',
  }));
  const {context, get} = boot([], links);
  context.olapLinkApply();
  assert.match(get('olapLinkSummary').textContent, /showing 1–200 of 205/);
  context.olapLinkPage(1);
  assert.match(get('olapLinkSummary').textContent, /showing 201–205 of 205/);
  get('olapLinkDir').value = 'inward';
  context.olapLinkApply();
  assert.match(get('olapLinkSummary').textContent, /1 link record/);
  assert.match(get('olapLinkSummary').textContent, /showing 1–1 of 1/);
  get('olapLinkDir').value = 'missing';
  context.olapLinkApply();
  assert.match(get('olapLinkBody').innerHTML, /N\/A/);
  assert.match(get('olapLinkSummary').textContent, /showing 0–0 of 0/);
});
