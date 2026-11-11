'use strict';

const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

process.env.TZ = 'UTC';
const root = path.resolve(__dirname, '..');
const python = process.env.PYTHON || 'python3';
const loadSources = `
import json, runpy
root = 'lib/dashboard/'
def source(file, name):
    return runpy.run_path(root + file)[name]
print(json.dumps({
    'derive': source('derive.py', 'DERIVE_JS'),
    'widget': source('settings_widget.py', 'WIDGET_JS'),
    'settings': source('settings_metric.py', 'SETTINGS_JS'),
    'config': source('chart_config.py', 'CONFIG_JS'),
    'granularity': source('granularity.py', 'GRAN_JS'),
    'render': source('chart_render.py', 'RENDER_JS'),
    'defaults': runpy.run_path('lib/metric_settings.py')['DEFAULT_SETTINGS'],
}))
`;
const sources = JSON.parse(execFileSync(python, ['-c', loadSources], {
  cwd: root,
  encoding: 'utf8',
  maxBuffer: 8 * 1024 * 1024,
}));
const bootEnd = sources.render.indexOf('[RC-BOOT-END]');
assert.notEqual(bootEnd, -1, 'chart boot boundary must be present');
const runtime = [
  sources.derive,
  sources.widget,
  sources.settings,
  sources.config,
  sources.granularity,
  sources.render.slice(0, bootEnd),
].join('\n');

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

class Element {
  constructor(id = '') {
    this.id = id;
    this.children = [];
    this.checked = true;
    this.style = {};
    this.textContent = '';
    this.value = '';
    this.attributes = {};
    this.classList = {
      add() {},
      remove() {},
      toggle() {},
      contains(name) { return name === 'hidden'; },
    };
  }
  set innerHTML(value) {
    this._innerHTML = value;
    this.children = [];
  }
  get innerHTML() { return this._innerHTML || ''; }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  addEventListener() {}
  click() {}
  remove() {}
  querySelectorAll() { return []; }
}

function elementsWithin(element, predicate) {
  return element.children.flatMap(child => [
    ...(predicate(child) ? [child] : []),
    ...elementsWithin(child, predicate),
  ]);
}

function boot(raw, options = {}) {
  const elements = new Map();
  const getElement = id => {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  };
  const document = {
    readyState: 'complete',
    body: new Element('body'),
    getElementById: getElement,
    createElement: () => new Element(),
    createTextNode: text => ({textContent: String(text), children: []}),
    addEventListener() {},
    querySelectorAll(selector) {
      if (selector.startsWith('#cfdTypeWrap ')) {
        return elementsWithin(getElement('cfdTypeWrap'), e => e.className === 'cfdTypeCb'
          && (!selector.includes(':checked') || e.checked));
      }
      if (selector.startsWith('#rcTypeWrap ')) {
        return elementsWithin(getElement('rcTypeWrap'), e => e.className === 'rcTypeCb'
          && (!selector.includes(':checked') || e.checked));
      }
      if (selector.startsWith('#rcDimList ')) {
        return elementsWithin(getElement('rcDimList'), e => e.className === 'rcDimCb'
          && (!selector.includes(':checked') || e.checked));
      }
      return [];
    },
  };
  getElement('rcDim').value = 'project';
  getElement('rcPeriods').value = 'sprint';
  const storage = new Map(Object.entries(options.storage || {}));
  const errors = [];
  const context = {
    document,
    console: {...console, error: (...args) => errors.push(args.join(' '))},
    localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: key => storage.delete(key),
    },
    Chart: class {
      constructor(element, config) {
        this.data = config.data;
        this.options = config.options;
      }
      destroy() {}
    },
    setTimeout,
    clearTimeout,
    RC_RAW: copy(raw),
    PM_DATA: {},
    RC_SETTINGS: copy(sources.defaults),
    RC_ISSUE_DIR: Object.fromEntries(raw.map(r => [r.key, {
      type: r.type,
      status: r.resolutiondate ? 'Done' : 'Open',
      summary: 'Synthetic issue',
      url: 'https://example.invalid/',
    }])),
    RC_HAS_SPRINTS: Boolean(options.hasSprints),
    RC_HAS_SPRINTS_DATA: Boolean(options.hasSprints),
    TEAM_FIELDS: ['Team'],
  };
  context.window = context;
  if (options.sprints) context.RC_SPRINT_CATALOG = copy(options.sprints);
  if (options.coverage) context.RC_SPRINT_COVERAGE = copy(options.coverage);
  vm.createContext(context);
  vm.runInContext(options.runtime || runtime, context, {filename: 'trends-runtime.js', timeout: 10000});
  if (options.settings) {
    context.rcDraft = copy(options.settings);
    context.rcWidgetSettingsApply();
  }
  assert.deepEqual(errors, [], `runtime errors: ${errors.join('; ')}`);
  return {context, errors, document};
}

function timestamp(date, offset) {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().replace('.000Z', 'Z');
}

function makeIssue(date, index, type, suffix = '') {
  const labels = [index < 2 ? 'alpha-team' : 'beta-team'];
  if (type === 'Bug' && index === 3) labels.push('qa');
  if (type === 'Bug' && index === 4) labels.push('review', 'prod');
  return {
    key: `SYN-${date}-${index}${suffix}`,
    project: 'SYN',
    type,
    status: 'Done',
    team: index < 2 ? 'Component A' : 'Component B',
    epic: index < 2 ? 'Epic A' : 'Epic B',
    person: index < 2 ? 'Alice' : 'Bob',
    labels: labels.join(','),
    fieldvals: {Team: index < 2 ? 'Alpha' : 'Beta'},
    created: timestamp(date, 0),
    resolutiondate: timestamp(date, 7).slice(0, 10),
    events: [
      [timestamp(date, 0), 'Ready for development'],
      [timestamp(date, 1), 'In Progress'],
      [timestamp(date, 3), 'Ready for QA'],
      [timestamp(date, 5), 'Ready for Demo'],
      [timestamp(date, 7), 'Done'],
    ],
    sp: [3, 0, 2, 1, 0][index],
    timeSpent: 3600,
    priority: 'Major',
    sprint: 'Sprint',
  };
}

function activity() {
  const starts = ['2025-09-22', '2025-10-06', '2025-10-20',
    '2025-11-03', '2025-11-17', '2025-12-01'];
  const types = ['Story', 'Task', 'Story', 'Bug', 'Bug'];
  return starts.flatMap((date, period) =>
    Array.from({length: period === starts.length - 1 ? 1 : 30},
      (_, n) => makeIssue(date, n % types.length, types[n % types.length], `-${n}`))
  );
}

function show(context, metric, errors) {
  context.rcSetMetric(metric);
  assert.deepEqual(errors, [], `runtime errors: ${errors.join('; ')}`);
  assert.ok(context.rcChart, `${metric} should produce a chart`);
  return context.rcChart;
}

function setTeamFilter(context, team) {
  context.document.getElementById('rcDim').value = 'team';
  context.rcPopulateDim();
  const boxes = context.document.querySelectorAll('#rcDimList input[type="checkbox"]');
  assert.ok(boxes.length, 'team filters should be available');
  boxes.forEach(box => {
    box.checked = box.value === team;
  });
  context.rcApply();
}

const metricKeys = ['cycle', 'rework', 'lead', 'flow', 'throughput',
  'velocity', 'cycletime', 'backlog', 'designreview', 'bugflow', 'leakage',
  'bugfix', 'incident', 'qa', 'defectdensity', 'wip', 'floweff',
  'escapereview', 'clarcycle', 'reviewcycle'];

function sprintActivity() {
  const raw = activity();
  const starts = [...new Set(raw.map(r => r.created.slice(0, 10)))];
  const sprints = starts.map((date, n) => ({
    id: String(100 - n * 7), name: `Iteration ${n + 1}`, board: String(n % 2 + 1),
    state: 'closed', closed: true, usable: true,
    start: timestamp(date, 0).replace('12:00', '09:00'),
    finish: timestamp(date, 10 + n % 3),
  }));
  raw.forEach(r => {
    const n = starts.indexOf(r.created.slice(0, 10));
    r.sprint_ids = [sprints[n].id];
    r.has_sprint = true;
    r.created_ts = r.created;
    r.resolved_ts = r.events.at(-1)[0];
  });
  return {raw, sprints};
}

function manualRange(context, from, to) {
  context.document.getElementById('rcFrom').value = from;
  context.document.getElementById('rcTo').value = to;
  context.rcCalTouchedSet();
  context.rcApply();
}

test('all twenty metrics use actual irregular sprint IDs, names and the same last five completed periods', () => {
  const {raw, sprints} = sprintActivity();
  const {context, errors} = boot(raw, {sprints});
  const expected = sprints.slice(-5).map(s => s.name);
  for (const metric of metricKeys) {
    assert.deepEqual(Array.from(show(context, metric, errors).data.labels), expected, metric);
    assert.equal(context.RC_WIN_STATE.periodSource, 'jira');
    assert.deepEqual(Array.from(context.RC_WIN_STATE.periodIds),
      sprints.slice(-5).map(s => `jira:${s.id}`));
  }
});

test('Auto uses a strict project-wide majority, including undated Sprint fields', () => {
  for (const populated of [0, 2, 3]) {
    const {raw, sprints} = sprintActivity();
    const subset = raw.slice(0, 4);
    subset.forEach((r, n) => {
      r.has_sprint = n < populated;
      if (!r.has_sprint) r.sprint_ids = [];
    });
    const {context} = boot(subset, {sprints});
    context.rcSetMetric('velocity');
    assert.equal(context.RC_WIN_STATE.periodSource, populated > 2 ? 'jira' : 'calendar');
    context.document.getElementById('rcDim').value = 'person';
    context.rcApply();
    assert.equal(context.rcSprintSource(context.RC_SETTINGS), populated > 2);
  }
  const {context} = boot([{...makeIssue('2025-01-01', 0, 'Story'),
    has_sprint: true, sprint_ids: ['undated']}], {sprints: []});
  assert.equal(context.rcSprintSource(context.RC_SETTINGS), true);
  assert.deepEqual(Array.from(context.rcChart.data.labels), []);
});

test('Sprint overrides rebuild state without stale decisions and calendar views include unassigned issues', () => {
  const {raw, sprints} = sprintActivity();
  raw[1].sprint_ids = [];
  raw[1].has_sprint = false;
  const {context} = boot(raw, {sprints});
  context.rcSetMetric('velocity');
  for (const [source, expected] of [['none', 'calendar'], ['available', 'jira'], ['auto', 'jira']]) {
    context.rcDraft = copy(context.RC_SETTINGS);
    context.rcDraft.sprintData = source;
    context.rcWidgetSettingsApply();
    assert.equal(context.RC_WIN_STATE.periodSource, expected);
    assert.equal(context.rcSprintsAvail(), source !== 'none');
  }
  manualRange(context, '2025-09-01', '2025-12-31');
  assert.ok(!context.RC_TABLE.rows.includes(raw[1].key));
  context.document.getElementById('rcPeriods').value = 'monthly';
  context.rcPeriodsChanged();
  context.rcApply();
  assert.ok(context.RC_TABLE.rows.includes(raw[1].key));
});

test('all metrics retain Team dimension filters in actual sprint mode', () => {
  const {raw, sprints} = sprintActivity();
  const settings = copy(sources.defaults);
  settings.teamConfig = {source: 'field', fieldName: 'Team'};
  settings.statusSets.review = ['Ready for Demo'];
  settings.metrics.designreview.designStart = 'In Progress';
  settings.metrics.designreview.reviewDone = 'Ready for Demo';
  settings.metrics.escapereview.qaLabel = 'qa';
  settings.metrics.escapereview.reviewLabel = 'review';
  const {context, errors} = boot(raw, {sprints, settings});
  let axis;
  for (const metric of metricKeys) {
    show(context, metric, errors);
    setTeamFilter(context, 'Beta');
    assert.equal(context.document.getElementById('rcFrom').value, '2025-09-22', metric);
    if (!axis) axis = Array.from(context.rcChart.data.labels);
    assert.deepEqual(Array.from(context.rcChart.data.labels), axis, metric);
    assert.ok(context.RC_TABLE.rows.every(key => raw.find(r => r.key === key).fieldvals.Team === 'Beta'), metric);
  }
});

test('available forces real sprints below 50%, while clearing a manual range restores Default N', () => {
  const {raw, sprints} = sprintActivity();
  const settings = copy(sources.defaults);
  settings.sprintData = 'available';
  const {context} = boot(raw, {sprints, settings, coverage: {total: 100, populated: 20}});
  assert.equal(context.RC_WIN_STATE.periodSource, 'jira');
  manualRange(context, '2025-09-01', '2025-12-31');
  assert.equal(context.rcChart.data.labels.length, 6);
  manualRange(context, '', '');
  assert.equal(context.rcChart.data.labels.length, 5);
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcDraft.sprintData = 'auto';
  context.rcWidgetSettingsApply();
  assert.equal(context.RC_WIN_STATE.periodSource, 'calendar');
});

test('Sprint overrides persist and export without introducing a second period-source setting', () => {
  const {raw, sprints} = sprintActivity();
  const settings = copy(sources.defaults);
  settings.sprintData = 'none';
  const {context, document} = boot(raw, {sprints, settings});
  const saved = context.localStorage.getItem('dedaa_metric_settings');
  const restored = boot(raw, {sprints, storage: {dedaa_metric_settings: saved}}).context;
  assert.equal(restored.RC_WIN_STATE.periodSource, 'calendar');
  let exported;
  context.Blob = class { constructor(parts) { this.parts = parts; } };
  context.URL = {createObjectURL(blob) { exported = JSON.parse(blob.parts.join('')); return 'blob:synthetic'; }};
  context.rcSettingsExport();
  assert.deepEqual(exported, copy(context.RC_SETTINGS));
  assert.equal(exported.sprintData, 'none');
  assert.ok(document.body.children.length > 0);
  assert.throws(() => context.rcMergeSettings(context.RC_SETTINGS, {sprintData: 'invalid'}), /sprintData/);
});

test('manual dates select whole sprints and per-metric Default N does not leak overlapping period IDs', () => {
  const {raw, sprints} = sprintActivity();
  const settings = copy(sources.defaults);
  settings.metrics.velocity.defaultN = 2;
  const extra = {...sprints[4], id: '500', name: 'Parallel', start: sprints[3].start,
    finish: sprints[3].finish};
  raw.push({...raw.at(-1), key: 'PARALLEL', sprint_ids: [extra.id]});
  const {context} = boot(raw, {sprints: [...sprints, extra], settings});
  context.rcSetMetric('velocity');
  assert.deepEqual(Array.from(context.rcChart.data.labels), ['Iteration 5', 'Iteration 6']);
  manualRange(context, '2025-11-18', '2025-11-19');
  assert.deepEqual(Array.from(context.rcChart.data.labels), ['Iteration 5']);
  assert.equal(context.RC_TABLE.rows.length, 30, 'completion after the calendar To remains in its selected sprint');
  context.rcSetMetric('throughput');
  assert.equal(context.rcChart.data.labels.length, 5);
  context.rcSetMetric('velocity');
  assert.deepEqual(Array.from(context.rcChart.data.labels), ['Iteration 5']);
});

test('sprint membership, not last historical entry, resolves anchors and rejects overlap ambiguity', () => {
  const {raw, sprints} = sprintActivity();
  const {context} = boot(raw, {sprints});
  const C = context.rcSprintContext('sprint', null, null, false);
  const it = {key: 'X', sprint_ids: [sprints[0].id, sprints[1].id],
    anchor_ts: timestamp('2025-10-06', 7)};
  assert.equal(C.key(it), `jira:${sprints[1].id}`);
  it.anchor_ts = '2030-01-01T00:00:00Z';
  assert.equal(C.key(it), null);
  const overlapping = {...sprints[1], id: '900', name: 'Other board', board: '9'};
  context.RC_SPRINT_CATALOG.push(overlapping);
  const overlap = context.rcSprintContext('sprint', null, null, false);
  it.sprint_ids = [sprints[1].id, overlapping.id];
  it.anchor_ts = timestamp('2025-10-06', 7);
  assert.equal(overlap.key(it), null);
});

test('exact timestamp offsets and half-open boundaries are independent of truncated calendar dates', () => {
  const {raw, sprints} = sprintActivity();
  const {context} = boot(raw, {sprints});
  const C = context.rcSprintContext('sprint', null, null, false);
  const it = {key: 'EDGE', sprint_ids: [sprints[0].id]};
  it.anchor_ts = sprints[0].start;
  assert.equal(C.key(it), `jira:${sprints[0].id}`);
  it.anchor_ts = sprints[0].finish;
  assert.equal(C.key(it), null);
  it.anchor_ts = '2025-09-22T11:00:00+02:00';
  assert.equal(C.key(it), `jira:${sprints[0].id}`);
  const velocity = context.PM_DATA.velocity[0];
  assert.equal(velocity.anchor_ts, raw[0].resolved_ts);
  const flow = context.PM_DATA.flow.find(it => it.key === raw[0].key && it.series === 'opened');
  assert.equal(flow.anchor_ts, raw[0].created_ts);
});

test('unfinished sprints require a manual window and never contribute to the trend', () => {
  const {raw, sprints} = sprintActivity();
  const current = {...sprints[0], id: '999', name: 'Current', state: 'active',
    closed: false, start: '2026-01-01T00:00:00Z', finish: null};
  const issue = makeIssue('2026-01-02', 0, 'Story');
  Object.assign(issue, {key: 'CURRENT', sprint_ids: ['999'], has_sprint: true,
    created_ts: issue.created, resolved_ts: issue.events.at(-1)[0],
    updated_ts: '2026-01-15T00:00:00Z'});
  const future = {...current, id: '1000', name: 'Future', state: 'future',
    start: '2026-02-01T00:00:00Z'};
  const {context} = boot([...raw, issue], {sprints: [...sprints, current, future]});
  context.rcSetMetric('velocity');
  assert.ok(!context.rcChart.data.labels.includes('Current'));
  manualRange(context, '2025-09-01', '2026-03-01');
  assert.ok(context.rcChart.data.labels.includes('Current'));
  assert.ok(!context.rcChart.data.labels.includes('Future'));
  const trend = context.rcChart.data.datasets.find(d => d.label === 'Trend');
  assert.ok(trend);
  assert.equal(trend.data.at(-1), null);
  assert.match(context.RC_WIN_STATE.periodNote, /partial.*excluded/);
});

test('duplicate sprint names are disambiguated without merging their identities', () => {
  const {raw, sprints} = sprintActivity();
  sprints[4].name = sprints[5].name = 'Duplicate';
  const {context} = boot(raw, {sprints});
  assert.equal(new Set(context.rcChart.data.labels).size, 5);
  assert.match(context.rcChart.data.labels.at(-1), /Board 2, #65/);
});

test('the actual Sprint widget control invokes the widget collector, preserving metric types', () => {
  const {raw, sprints} = sprintActivity();
  const {context, document} = boot(raw, {sprints});
  context.rcDraftBase = copy(context.RC_SETTINGS);
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcWidgetSettingsRender();
  const html = document.getElementById('rcWidgetSettingsBody').innerHTML;
  const control = /<select id="rcSet_sprintData"[^>]*onchange="([^"]+)"/.exec(html);
  assert.ok(control, 'rendered widget must expose the actual handler');
  document.getElementById('rcSet_sprintData').value = 'none';
  const types = copy(context.rcDraft.metrics.velocity.types);
  vm.runInContext(control[1], context);
  assert.equal(context.rcDraft.sprintData, 'none');
  assert.deepEqual(copy(context.rcDraft.metrics.velocity.types), types);
});

test('real-sprint WIP and backlog snapshots use the same membership as their issue tables', () => {
  const {raw, sprints} = sprintActivity();
  const first = sprints[4], second = sprints[5];
  const carry = {...raw[0], key: 'CARRY', has_sprint: true, sprint_ids: [first.id, second.id],
    created: '2025-11-18T12:00:00Z', created_ts: '2025-11-18T12:00:00Z',
    resolutiondate: '2025-12-03', resolved_ts: '2025-12-03T12:00:00Z',
    events: [['2025-11-18T12:00:00Z', 'In Progress'], ['2025-12-03T12:00:00Z', 'Done']]};
  const ready = {...carry, key: 'READY', sprint_ids: [first.id], status: 'Ready for development',
    resolutiondate: '', resolved_ts: '', events: [['2025-11-18T12:00:00Z', 'Ready for development']]};
  const unassigned = {...carry, key: 'NO-SPRINT', sprint_ids: [], has_sprint: false, events: carry.events.slice(0, 1)};
  const {context} = boot([...raw, carry, ready, unassigned], {sprints});
  context.rcSetMetric('wip');
  const bars = context.rcChart.data.datasets[0].data;
  assert.deepEqual(Array.from(bars), [0, 0, 0, 1, 0]);
  assert.deepEqual(Array.from(context.RC_TABLE.rows), ['CARRY']);
  context.rcSetMetric('backlog');
  assert.ok(context.RC_TABLE.rows.includes('READY'));
  assert.ok(!context.RC_TABLE.rows.includes('NO-SPRINT'));
  const readyPeriod = context.rcChart.data.datasets[0].data[3];
  assert.ok(readyPeriod > 0, 'ready inventory has a matching completed-work denominator');
  assert.equal(context.rcChart.data.datasets[0].data[4], 0, 'a first-sprint member is not counted in the next snapshot');
});

test('Velocity SP fill uses only included sprint events and preserves explicit unit settings', () => {
  const {raw, sprints} = sprintActivity();
  const selected = raw.filter(r => r.sprint_ids[0] === sprints[5].id);
  const second = {...selected[0], key: 'SECOND', sp: 0};
  const outside = {...selected[0], key: 'OUTSIDE', sp: 100, sprint_ids: [sprints[0].id]};
  const {context} = boot([...selected, second, outside], {sprints});
  context.rcSetMetric('velocity');
  assert.equal(context.RC_WIN_STATE.velSpFill, 0.5);
  assert.equal(context.rcMetricState('velocity').state, 'sp');
  assert.equal(context.rcChart.data.datasets[0].data.at(-1), 3);
  assert.ok(!context.RC_TABLE.rows.includes('OUTSIDE'));
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcDraft.metrics.velocity.velocityMode = 'items';
  context.rcSettingsApply();
  assert.equal(context.rcChart.data.datasets[0].data.at(-1), 2);
});

test('Reset and import discard stale Sprint drafts before rebuilding, while Cancel keeps the chart', () => {
  const {raw, sprints} = sprintActivity();
  const {context, document} = boot(raw, {sprints});
  context.rcSetMetric('velocity');
  context.rcDraftBase = copy(context.RC_SETTINGS);
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcDraft.sprintData = 'none';
  context.rcWidgetSettingsClose();
  assert.equal(context.RC_WIN_STATE.periodSource, 'jira');
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcDraft.sprintData = 'none';
  context.rcSettingsReset();
  assert.equal(context.RC_WIN_STATE.periodSource, 'jira', 'Reset must render committed defaults, not discarded draft');

  const imported = copy(context.RC_SETTINGS);
  imported.sprintData = 'none';
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcDraft.sprintData = 'available';
  context.FileReader = class {
    readAsText(file) { this.result = file.content; this.onload(); }
  };
  const create = document.createElement;
  document.createElement = () => {
    const element = create();
    element.files = [{content: JSON.stringify(imported)}];
    element.click = () => element.onchange();
    return element;
  };
  context.alert = message => assert.fail(message);
  context.rcSettingsImport();
  assert.equal(context.RC_WIN_STATE.periodSource, 'calendar');
  assert.equal(context.rcDraft, null);
});

test('the separate Delivery CFD remains calendar-based with either Trends Sprint source', () => {
  const {raw, sprints} = sprintActivity();
  const {context, document} = boot(raw, {sprints});
  document.getElementById('cfdDim').value = 'project';
  document.getElementById('cfdPeriods').value = 'sprint';
  context.cfdPopulateTypes();
  context.cfdSyncCalendar();
  context.cfdApply();
  const expected = copy(context.cfdChartRef.data);
  assert.ok(expected.labels.every(label => /^\d{4}-W/.test(label)));
  assert.ok(expected.datasets.some(ds => ds.data.some(value => value > 0)));
  context.rcDraft = copy(context.RC_SETTINGS);
  context.rcDraft.sprintData = 'none';
  context.rcWidgetSettingsApply();
  context.cfdApply();
  assert.deepEqual(copy(context.cfdChartRef.data), expected);
});

const dashboards = JSON.parse(process.env.DEDAA_DASHBOARDS || '[]');
test('optional regenerated HTML executes all metrics and matches independent Velocity accounting',
  {skip: dashboards.length === 0}, () => {
    for (const spec of dashboards) {
      const html = fs.readFileSync(spec.path, 'utf8');
      const start = html.indexOf('var PM_DATA = {');
      const end = html.indexOf('[RC-BOOT-END]');
      assert.ok(start >= 0 && end > start, 'generated HTML must contain the widget runtime');
      const {context, errors} = boot([], {runtime: html.slice(start, end)});
      let labels;
      for (const metric of metricKeys) {
        const chart = show(context, metric, errors);
        assert.equal(context.RC_WIN_STATE.periodSource, spec.source);
        if (!labels) labels = Array.from(chart.data.labels);
        else assert.deepEqual(Array.from(chart.data.labels), labels);
      }
      assert.equal(labels.length, 5);
      if (spec.source !== 'jira') continue;
      context.rcSetMetric('velocity');
      const periods = Array.from(context.RC_WIN_STATE.periodIds);
      const catalog = Array.from(context.RC_SPRINT_CATALOG).filter(s => s.usable && s.closed);
      const sums = Object.fromEntries(periods.map(id => [id, {n: 0, sp: 0}]));
      const keys = new Set();
      let filled = 0, total = 0;
      for (const it of context.PM_DATA.velocity) {
        const t = Date.parse(it.anchor_ts);
        const candidates = catalog.filter(s => it.sprint_ids.includes(s.id)
          && t >= Date.parse(s.start) && t < Date.parse(s.finish));
        if (candidates.length !== 1) continue;
        const bucket = sums[`jira:${candidates[0].id}`];
        if (!bucket) continue;
        bucket.n++;
        bucket.sp += it.sp || 0;
        total++;
        if (it.sp > 0) filled++;
        keys.add(it.key);
      }
      assert.equal(context.RC_WIN_STATE.velSpFill, total ? filled / total : 0);
      const unit = context.rcMetricState('velocity').state === 'sp' ? 'sp' : 'n';
      assert.deepEqual(Array.from(context.rcChart.data.datasets[0].data), periods.map(p => sums[p][unit]));
      assert.deepEqual(new Set(context.RC_TABLE.rows), keys);
    }
  });

test('all existing metrics share the five latest active two-week periods', () => {
  const {context, errors} = boot(activity());
  assert.deepEqual(Object.keys(context.RC_CFG).sort(), [...metricKeys].sort());
  const expected = ['2025-W39-40', '2025-W41-42', '2025-W43-44',
    '2025-W45-46', '2025-W47-48'];
  for (const metric of metricKeys) {
    const labels = Array.from(show(context, metric, errors).data.labels);
    assert.deepEqual(labels, expected, metric);
  }
});

test('real sprint mode without usable dates is N/A, never fabricated periods', () => {
  const {context, errors} = boot(activity(), {hasSprints: true});
  for (const metric of metricKeys) {
    assert.deepEqual(Array.from(show(context, metric, errors).data.labels), [], metric);
    assert.match(context.document.getElementById('rcConclusion').textContent, /N\/A/);
  }
});

test('field and label team sources filter derived data across metric families', () => {
  for (const teamConfig of [
    {source: 'field', fieldName: 'Team'},
    {source: 'labels', labels: ['alpha-team', 'beta-team']},
  ]) {
    const settings = copy(sources.defaults);
    settings.teamConfig = teamConfig;
    settings.statusSets.review = ['Ready for Demo'];
    settings.metrics.designreview.designStart = 'In Progress';
    settings.metrics.designreview.reviewDone = 'Ready for Demo';
    settings.metrics.escapereview.qaLabel = 'qa';
    settings.metrics.escapereview.reviewLabel = 'review';
    const raw = activity();
    raw[0].labels += ',beta-team';
    const byKey = new Map(raw.map(item => [item.key, item]));
    const {context, errors} = boot(raw, {settings});
    for (const family of [...metricKeys, 'cfd']) {
      assert.ok(context.PM_DATA[family].length, `${family} should have representative data`);
    }
    for (const [family, items] of Object.entries(context.PM_DATA)) {
      for (const item of items) {
        const source = byKey.get(item.key);
        assert.ok(source, `${family} item must refer to a source issue`);
        const expected = teamConfig.source === 'field'
          ? [source.fieldvals.Team]
          : source.labels.split(',').filter(label => teamConfig.labels.includes(label));
        assert.deepEqual(Array.from(context.rcItemTeams(item)), expected,
          `${family}: ${item.key}`);
      }
    }
    show(context, 'throughput', errors);
    setTeamFilter(context, teamConfig.source === 'field' ? 'Alpha' : 'alpha-team');
    assert.deepEqual(Array.from(context.rcChart.data.datasets[0].data), [12, 12, 12, 12, 12]);
    assert.deepEqual(errors, []);
  }
});

test('issues without a configured team remain in the undefined team group', () => {
  for (const teamConfig of [
    {source: 'field', fieldName: 'Team'},
    {source: 'labels', labels: ['alpha-team', 'beta-team']},
  ]) {
    const settings = copy(sources.defaults);
    settings.teamConfig = teamConfig;
    const raw = activity();
    raw[0].fieldvals = {};
    raw[0].labels = '';
    const {context} = boot(raw, {settings});
    const item = context.PM_DATA.throughput.find(item => item.key === raw[0].key);
    assert.ok(item);
    assert.deepEqual(Array.from(context.rcItemTeams(item)), ['Team is not defined']);
    assert.ok(Array.from(context.rcDimValues('team')).includes('Team is not defined'));
  }
});

test('default production label rejects unrelated labels and keeps overrides', () => {
  const unrelated = ['product', 'non-prod', 'preprod'];
  for (const label of unrelated) {
    const item = makeIssue('2025-01-01', 4, 'Bug');
    item.labels = label;
    const {context} = boot([item]);
    assert.equal(context.PM_DATA.incident.length, 0, label);
    assert.equal(context.PM_DATA.leakage.filter(item => item.role === 'numerator').length, 0, label);
  }
  for (const label of ['prod', 'production', 'prod_bug', 'PROD']) {
    const item = makeIssue('2025-01-01', 4, 'Bug');
    item.labels = label;
    const {context} = boot([item]);
    assert.equal(context.PM_DATA.incident.length, 1, label);
    assert.equal(context.PM_DATA.leakage.filter(item => item.role === 'numerator').length, 1, label);
  }
  const first = makeIssue('2025-01-01', 3, 'Bug', '-one');
  const second = makeIssue('2025-01-01', 4, 'Bug', '-two');
  first.labels = 'product';
  second.labels = 'prod_bug';
  const {context, errors} = boot([first, second]);
  assert.deepEqual(Array.from(context.PM_DATA.incident, item => item.key), [second.key]);
  assert.deepEqual(Array.from(context.PM_DATA.leakage.filter(item => item.role === 'numerator'),
    item => item.key), [second.key]);

  const settings = copy(sources.defaults);
  settings.prodLabel = 'product';
  context.rcDraft = settings;
  context.rcWidgetSettingsApply();
  assert.deepEqual(Array.from(context.PM_DATA.incident, item => item.key), [first.key]);
  assert.deepEqual(Array.from(context.PM_DATA.leakage.filter(item => item.role === 'numerator'),
    item => item.key), [first.key]);
  assert.deepEqual(errors, []);

  const variants = ['prod_bug', 'production', 'prod'].map((label, index) => {
    const item = makeIssue('2025-01-01', 4, 'Bug', `-${index}`);
    item.labels = label;
    return item;
  });
  const mixedRun = boot(variants);
  const mixed = mixedRun.context;
  assert.deepEqual(Array.from(mixed.PM_DATA.incident, item => item.key),
    variants.map(item => item.key));

  const specific = copy(sources.defaults);
  specific.prodLabel = 'product';
  specific.metrics.incident.prodLabel = 'prod_bug';
  specific.metrics.leakage.prodLabel = 'prod_bug';
  mixed.rcDraft = specific;
  mixed.rcWidgetSettingsApply();
  assert.deepEqual(Array.from(mixed.PM_DATA.incident, item => item.key), [variants[0].key]);
  assert.deepEqual(Array.from(mixed.PM_DATA.leakage.filter(item => item.role === 'numerator'),
    item => item.key), [variants[0].key]);
  assert.deepEqual(mixedRun.errors, []);
});

test('issue-type and metric settings change the derived throughput and velocity', () => {
  const {context, errors} = boot(activity());
  let chart = show(context, 'throughput', errors);
  assert.deepEqual(Array.from(chart.data.datasets[0].data), [30, 30, 30, 30, 30]);
  const typeBoxes = context.document.querySelectorAll('#rcTypeWrap input[type="checkbox"]');
  typeBoxes.forEach(box => { box.checked = box.value === 'Story'; });
  context.rcTypeMemChanged();
  context.rcApply();
  chart = context.rcChart;
  assert.deepEqual(Array.from(chart.data.datasets[0].data), [12, 12, 12, 12, 12]);

  typeBoxes.forEach(box => { box.checked = true; });
  const settings = copy(sources.defaults);
  settings.metrics.velocity.velocityMode = 'sp';
  context.rcDraft = settings;
  context.rcSettingsApply();
  chart = show(context, 'velocity', errors);
  assert.deepEqual(Array.from(chart.data.datasets[0].data), [36, 36, 36, 36, 36]);
});

test('duration metrics use their configured end event as the period anchor', () => {
  const item = makeIssue('2025-01-01', 0, 'Story');
  item.created = timestamp('2024-11-01', 0);
  item.resolutiondate = '2025-01-20';
  item.events = [
    [timestamp('2024-12-05', 0), 'In Progress'],
    [timestamp('2025-01-03', 0), 'Ready for QA'],
    [timestamp('2025-01-05', 0), 'Ready for Demo'],
    [timestamp('2025-01-20', 0), 'Done'],
  ];
  const settings = copy(sources.defaults);
  settings.metrics.designreview.designStart = 'In Progress';
  settings.metrics.designreview.reviewDone = 'Ready for Demo';
  const {context} = boot([item], {settings});
  const expected = {
    cycle: '2024-12-05T12:00:00',
    cycletime: '2025-01-20T12:00:00',
    lead: '2025-01-20T12:00:00',
    qa: '2025-01-05T12:00:00',
    floweff: '2025-01-20T12:00:00',
    designreview: '2025-01-05T12:00:00',
  };
  for (const [metric, end] of Object.entries(expected)) {
    assert.equal(context.PM_DATA[metric].length, 1, metric);
    assert.equal(context.PM_DATA[metric][0].dev_start, end, metric);
  }
});

test('automatic velocity uses story points at 50% fill and counts below it', () => {
  for (const [estimated, expectedState, expectedValue] of [
    [15, 'sp', 15],
    [14, 'items', 30],
  ]) {
    const raw = activity();
    raw.forEach((item, index) => { item.sp = index % 30 < estimated ? 1 : 0; });
    const {context, errors} = boot(raw);
    const chart = show(context, 'velocity', errors);
    assert.equal(context.rcMetricState('velocity').state, expectedState);
    assert.deepEqual(Array.from(chart.data.datasets[0].data),
      Array(5).fill(expectedValue));
  }
});

test('flow efficiency bars use total active days divided by total duration', () => {
  const first = makeIssue('2025-01-01', 0, 'Story', '-one');
  const second = makeIssue('2025-01-05', 1, 'Story', '-two');
  for (const [item, start] of [[first, '2025-01-02'], [second, '2025-01-06']]) {
    item.resolutiondate = '2025-01-09';
    item.events = [
      [timestamp(start, 0), 'In Progress'],
      [timestamp('2025-01-09', 0), 'Done'],
    ];
  }
  const {context, errors} = boot([first, second]);
  const chart = show(context, 'floweff', errors);
  const values = Array.from(chart.data.datasets[0].data).filter(value => value !== null);
  assert.equal(values.length, 1);
  assert.ok(Math.abs(values[0] - (10 / 12 * 100)) < 1e-9);
  assert.match(context.document.getElementById('rcAvgBox').textContent, /83[.,]3/);
});

test('flow trend uses net balance and relative trend thresholds', () => {
  const {context} = boot(activity());
  assert.equal(context.rcFlowVerdict([10, 10, 10], [15, 15, 15]).cls, 'improving');
  assert.equal(context.rcFlowVerdict([15, 15, 15], [10, 10, 10]).cls, 'degrading');
  assert.equal(context.rcFlowVerdict([10, 10, 10], [10, 10, 10]).cls, 'stable');
  assert.equal(context.rcTrendVerdict([100, 100, 120], 'up', 10).cls, 'improving');
  assert.equal(context.rcTrendVerdict([100, 100, 102], 'up', 10).cls, 'stable');
  assert.equal(context.rcTrendVerdict([100, 120], 'up', 10).reason, 'few');
});

test('biweekly bucket end is the end of Sunday in local time', () => {
  const {context} = boot(activity());
  const previous = process.env.TZ;
  try {
    for (const zone of ['UTC', 'America/New_York', 'Asia/Kolkata']) {
      process.env.TZ = zone;
      const end = new Date(context.rcBucketEnd('2025-W47-48', 'sprint'));
      assert.equal(end.getFullYear(), 2025, zone);
      assert.equal(end.getMonth(), 10, zone);
      assert.equal(end.getDate(), 30, zone);
      assert.equal(end.getHours(), 23, zone);
      assert.equal(end.getMinutes(), 59, zone);
    }
  } finally {
    process.env.TZ = previous;
  }
});
