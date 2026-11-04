'use strict';

const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
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
  const storage = new Map();
  const errors = [];
  const context = {
    document,
    console: {...console, error: (...args) => errors.push(args.join(' '))},
    localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
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
  vm.createContext(context);
  vm.runInContext(runtime, context, {filename: 'trends-runtime.js', timeout: 10000});
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

test('without sprint dates, all metrics use the same two-week fallback', () => {
  const {context, errors} = boot(activity(), {hasSprints: true});
  for (const metric of metricKeys) {
    assert.deepEqual(Array.from(show(context, metric, errors).data.labels),
      ['2025-W39-40', '2025-W41-42', '2025-W43-44', '2025-W45-46', '2025-W47-48'], metric);
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
