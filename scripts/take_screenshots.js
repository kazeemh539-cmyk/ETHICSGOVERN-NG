// Drives the real application and saves the figures used in Chapter 4 / Appendix H.
const { chromium } = require('playwright');
const OUT = process.argv[2] || 'docs/screenshots';
const S = (p, name) => p.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
const nav = async (p, label) => { await p.click('.nav >> text=' + label); await p.waitForTimeout(1500); };
const model = async (p, name) => { await p.selectOption('.top select', { label: new RegExp(name).source ? undefined : undefined }).catch(()=>{}); };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  await p.goto('http://127.0.0.1:8000/'); await p.waitForSelector('.login'); await S(p, 'A0_Login');
  await p.click('button:has-text("Sign in")'); await p.waitForSelector('.nav'); await p.waitForTimeout(1200);
  const run = async () => { await p.click('button:has-text("Run monitoring")'); await p.waitForTimeout(2500); };
  const pick = async (idx) => { await p.selectOption('.top select', { index: idx }); await p.waitForTimeout(1200); };

  // v1 (biased): two runs, Figure 4.1
  await run(); await run(); await S(p, 'Figure_4.1_Fairness_overview_biased_model');
  // v2 (remediated) for contrast
  await pick(1); await run(); await S(p, 'Figure_4.1b_Fairness_overview_remediated_model');
  // Figure 4.2: SHAP panel for a declined woman on v1
  await pick(0); await nav(p, 'Decision explorer');
  await p.selectOption('.card select', '0'); await p.waitForTimeout(1200);
  const rows = await p.$$('tbody tr'); for (const r of rows) { if ((await r.innerText()).includes('\tF\t')) { await r.click(); break; } }
  await p.waitForTimeout(2500); await S(p, 'Figure_4.2_SHAP_explanation_panel');
  // Figure 4.3: drift under naira shock on v2
  await pick(1); await nav(p, 'Fairness overview');
  await p.selectOption('.card select', 'inflation'); await p.click('button:has-text("Inject scenario")'); await p.waitForTimeout(3500);
  await run(); await S(p, 'A1_Overview_after_naira_shock');
  await nav(p, 'Drift monitor'); await S(p, 'Figure_4.3_Drift_monitoring_screen');
  // Figure 4.4: findings register on v1 with one finding closed (append-only history)
  await nav(p, 'Findings register'); await pick(0); await p.waitForTimeout(800);
  const closeBtns = await p.$$('button:has-text("Close…")'); await closeBtns[closeBtns.length - 1].click();
  await p.fill('.modal textarea', 'Accepted for 30 days: remediation tracked under MRC action 14; v2 retraining excludes the protected attribute.');
  await p.click('.modal button:has-text("Close finding")'); await p.waitForTimeout(1500);
  const hist = await p.$$('button:has-text("History")'); if (hist.length) await hist[0].click(); await p.waitForTimeout(800);
  await S(p, 'Figure_4.4_Policy_violation_register');
  await nav(p, 'Maturity assessment');
  const sels = await p.$$('.scores select'); const vals = ['2','3','2','2','3','2','1']; for (let i = 0; i < sels.length; i++) await sels[i].selectOption(vals[i]);
  await p.fill('.card input', 'Demo Bank Plc'); await p.click('button:has-text("Record assessment")'); await p.waitForTimeout(1500); await S(p, 'A2_Maturity_assessment');
  await nav(p, 'Risk taxonomy'); await S(p, 'A3_Risk_taxonomy');
  await nav(p, 'Administration'); await p.click('button:has-text("Sign out")'); await p.waitForSelector('.login');
  await p.click('.chip >> text=Administrator'); await p.click('button:has-text("Sign in")'); await p.waitForSelector('.nav'); await nav(p, 'Administration'); await S(p, 'A4_Administration_policies_and_users');
  await b.close(); console.log('screenshots saved to', OUT);
})();
