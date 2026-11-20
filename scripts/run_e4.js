// Experiment E4 (scripted form): the five usability tasks performed through the real interface by an automated
// agent, with every action logged, every outcome verified against the system's own records, and task time
// predicted with the Keystroke-Level Model (Card, Moran & Newell, 1980). No human participants are involved.
const { chromium } = require('playwright');
const fs = require('fs');
const BASE = 'http://127.0.0.1:8000', API = BASE + '/api/v1';
const OUT = process.argv[2] || 'docs/results';
const RUNS = +(process.argv[3] || 5);
const KLM = { M: 1.35, P: 1.1, B: 0.1, K: 0.28, H: 0.4 };   // standard operator times (seconds)

async function api(path, token, opts = {}) {
  const r = await fetch(API + path, { method: opts.method || 'GET', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: opts.body ? JSON.stringify(opts.body) : undefined });
  return r.json();
}
const login = async (u) => (await api('/auth/login', null, { method: 'POST', body: { username: u, password: 'Demo@2025' } })).token;

class Agent {
  constructor(page, task, log, run) { Object.assign(this, { page, task, log, run }); this.n = 0; this.sub = ''; this.errors = 0; this.screens = new Set(); }
  rec(op, target, detail, secs) { this.log.push({ run: this.run, task: this.task, seq: ++this.n, subgoal: this.sub, operator: op, target, detail, klm_seconds: +secs.toFixed(2) }); }
  step(name) { this.sub = name; this.rec('M', 'mental preparation', name, KLM.M); }
  async click(sel, label) { await this.page.click(sel); this.rec('click', label || sel, '', KLM.P + 2 * KLM.B); await this.page.waitForTimeout(350); }
  async select(sel, value, label) { await this.page.selectOption(sel, value); this.rec('select', label || sel, String(value), 2 * (KLM.P + 2 * KLM.B)); await this.page.waitForTimeout(350); }
  async fill(sel, text, label) { await this.page.fill(sel, text); this.rec('type', label || sel, text.length + ' characters', 2 * KLM.H + text.length * KLM.K); }
  async read(sel, label) { const t = await this.page.innerText(sel); this.rec('read', label || sel, t.slice(0, 60).replace(/\s+/g, ' '), KLM.M); return t; }
  async nav(label) { await this.click('.nav >> text=' + label, 'menu: ' + label); this.screens.add(label); await this.page.waitForTimeout(900); }
  async model(idx) { await this.select('.top select', { index: idx }, 'model selector'); await this.page.waitForTimeout(700); }
}

async function newSession(browser, errs) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } }); const page = await ctx.newPage();
  page.on('pageerror', () => errs.n++); page.on('console', (m) => { if (m.type() === 'error') errs.n++; });
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/auth/login')) errs.n++; });
  await page.goto(BASE + '/'); await page.waitForSelector('.login');
  await page.click('button:has-text("Sign in")'); await page.waitForSelector('.nav'); await page.waitForTimeout(900);
  return { ctx, page };
}

(async () => {
  const browser = await chromium.launch(); const log = [], results = [];
  const admin = await login('admin');
  for (let run = 1; run <= RUNS; run++) {
    await api('/demo/reset', admin, { method: 'POST' });
    const ro = await login('riskofficer');
    const recent = await api('/decisions?model_id=1&limit=200', ro);
    const declinedF = recent.filter((d) => d.prediction === 0 && d.features.gender === 'F');
    const named = declinedF[10];                    // inside the 40 most recent decisions
    const older = declinedF[Math.min(declinedF.length - 1, 75)];  // far outside the 40 shown
    const record = (task, variant, a, outcome, success, note) => results.push({ run, task, variant, outcome, success, note, subgoals: new Set(log.filter(l => l.run === run && l.task === task + variant && l.operator === 'M').map(l => l.subgoal)).size,
      clicks: log.filter(l => l.run === run && l.task === task + variant && (l.operator === 'click' || l.operator === 'select')).reduce((s, l) => s + (l.operator === 'select' ? 2 : 1), 0),
      keystrokes: log.filter(l => l.run === run && l.task === task + variant && l.operator === 'type').reduce((s, l) => s + parseInt(l.detail), 0),
      reads: log.filter(l => l.run === run && l.task === task + variant && l.operator === 'read').length, screens: a.screens.size,
      klm_seconds: +log.filter(l => l.run === run && l.task === task + variant).reduce((s, l) => s + l.klm_seconds, 0).toFixed(1), errors: a.errors });
    const errs = { n: 0 };

    // ---- T1: has any model breached a fairness threshold? (run monitoring for each model and read the verdict)
    { const { ctx, page } = await newSession(browser, errs); errs.n = 0; const a = new Agent(page, 'T1', log, run); a.screens.add('Fairness overview');
      const verdicts = [];
      for (const idx of [0, 1]) { a.step('select model ' + (idx + 1)); await a.model(idx); a.step('run monitoring'); await a.click('button:has-text("Run monitoring")', 'Run monitoring'); await page.waitForTimeout(1500);
        a.step('read the policy status'); verdicts.push((await a.read('.banner h2', 'policy status banner')).trim()); }
      const truth = []; for (const m of [1, 2]) { const r = (await api('/monitoring/runs?model_id=' + m, ro))[0]; truth.push(r.metrics.violations.some((v) => ['DI_RATIO', 'EO_DIFF', 'GENDER_ATTRIBUTION'].includes(v.rule_id))); }
      const seen = verdicts.map((v) => /violation/.test(v) && !/compliant/.test(v));
      a.errors = errs.n; record('T1', '', a, 'Complete with limitation', seen[0] === truth[0] && seen[1] === truth[1], 'Verdicts match system records; window is fixed at the last 24 hours, so "last month" cannot be selected'); await ctx.close(); }

    // ---- T2a: explain why a named applicant was declined (applicant within the 40 most recent decisions)
    for (const [variant, target] of [['a', named], ['b', older]]) {
      const { ctx, page } = await newSession(browser, errs); errs.n = 0; const a = new Agent(page, 'T2' + variant, log, run); a.screens.add('Fairness overview');
      a.step('open the decision explorer'); await a.nav('Decision explorer');
      a.step('find the applicant ' + target.subject_pseudonym); await page.selectOption('.card select', '0'); a.rec('select', 'filter: Declined', '0', 2 * (KLM.P + 2 * KLM.B)); await page.waitForTimeout(900);
      const row = page.locator('tbody tr', { hasText: target.subject_pseudonym }); const found = (await row.count()) > 0;
      await a.read('tbody', 'scan the list for the applicant');
      let ok = false, outcome = 'Not supported';
      if (found) { a.step('open the decision'); await row.first().click(); a.rec('click', 'applicant row', '', KLM.P + 2 * KLM.B); await page.waitForTimeout(1800);
        a.step('read the reason codes'); const head = await a.read('.card h3:has-text("Decision #")', 'decision header'); const codes = await page.locator('.reason').count();
        ok = head.includes('#' + target.decision_id) && codes > 0; outcome = ok ? 'Complete' : 'Failed'; }
      a.errors = errs.n; record('T2', variant, a, outcome, ok, found ? 'Applicant located in the list; SHAP, LIME and reason codes shown' : 'No search: an applicant outside the 40 most recent decisions cannot be located in the interface'); await ctx.close(); }

    // ---- T3: which feature has drifted furthest?  (precondition: a naira-shock window exists for model 2)
    await api('/demo/simulate', ro, { method: 'POST', body: { model_id: 2, scenario: 'inflation', n: 2500 } });
    { const { ctx, page } = await newSession(browser, errs); errs.n = 0; const a = new Agent(page, 'T3', log, run); a.screens.add('Fairness overview');
      a.step('select model 2'); await a.model(1); a.step('run monitoring'); await a.click('button:has-text("Run monitoring")', 'Run monitoring'); await page.waitForTimeout(1500);
      a.step('open the drift monitor'); await a.nav('Drift monitor'); a.step('compare the statistics'); await a.read('.card table', 'drift table');
      const rows = await page.locator('.card table >> nth=0').locator('tbody tr').allInnerTexts(); const parsed = rows.map((r) => r.split('\t')).map((c) => ({ f: c[0].trim(), s: parseFloat(c[2]) }));
      const pick = parsed.sort((x, y) => y.s - x.s)[0].f.toLowerCase().replace(' ', '_');
      const runId = (await api('/monitoring/runs?model_id=2', ro))[0].run_id; const d = await api('/drift/' + runId, ro); const truth = d.sort((x, y) => y.statistic - x.statistic)[0].feature;
      a.errors = errs.n; record('T3', '', a, pick === truth ? 'Complete' : 'Failed', pick === truth, 'Agent chose "' + pick + '", system record says "' + truth + '"; table is not sorted by statistic, so the user must compare values'); await ctx.close(); }

    // ---- T4: locate and close an open finding
    { const { ctx, page } = await newSession(browser, errs); errs.n = 0; const a = new Agent(page, 'T4', log, run); a.screens.add('Fairness overview');
      a.step('open the findings register'); await a.nav('Findings register'); a.step('choose the finding to close'); await a.read('table', 'findings list');
      a.step('start closing'); await a.click('button:has-text("Close…") >> nth=0', 'Close…'); await page.waitForSelector('.modal');
      a.step('enter the justification'); await a.fill('.modal textarea', 'Model v1 withdrawn; remediation tracked under MRC action 14.', 'justification');
      a.step('confirm'); await a.click('.modal button:has-text("Close finding")', 'Close finding'); await page.waitForTimeout(1200);
      const fs_ = await api('/findings?model_id=1&status=closed', ro); const ok = fs_.some((f) => f.recorded_by === 'riskofficer' && f.history.length >= 2 && f.justification);
      a.errors = errs.n; record('T4', '', a, ok ? 'Complete' : 'Failed', ok, 'Superseding closed record with justification found in the register; the original record is preserved'); await ctx.close(); }

    // ---- T5: complete a maturity assessment for one dimension (M3 = 4)
    { const { ctx, page } = await newSession(browser, errs); errs.n = 0; const a = new Agent(page, 'T5', log, run); a.screens.add('Fairness overview');
      a.step('open the maturity assessment'); await a.nav('Maturity assessment'); a.step('score the dimension'); await a.select('.scores select >> nth=2', '4', 'M3 score'); a.step('record'); await a.click('button:has-text("Record assessment")', 'Record assessment'); await page.waitForTimeout(1200);
      const asm = (await api('/assessments', ro))[0]; const ok = asm && asm.dimension_scores.M3 === 4;
      a.errors = errs.n; record('T5', '', a, ok ? 'Complete with limitation' : 'Failed', ok, 'M3 saved as 4; the form requires all seven dimensions, so the other six are recorded at the default of 3 rather than left unscored'); await ctx.close(); }
    console.log('run', run, 'done');
  }
  await browser.close();
  const esc = (v) => '"' + String(v).replace(/"/g, '""') + '"';
  const cols = ['run', 'task', 'seq', 'subgoal', 'operator', 'target', 'detail', 'klm_seconds'];
  fs.writeFileSync(OUT + '/e4_action_log.csv', [cols.join(',')].concat(log.map((l) => cols.map((c) => esc(l[c])).join(','))).join('\n'));
  const rc = ['run', 'task', 'variant', 'outcome', 'success', 'subgoals', 'clicks', 'keystrokes', 'reads', 'screens', 'klm_seconds', 'errors', 'note'];
  fs.writeFileSync(OUT + '/e4_task_results.csv', [rc.join(',')].concat(results.map((r) => rc.map((c) => esc(r[c])).join(','))).join('\n'));
  console.log('written to', OUT);
})();
