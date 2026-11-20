import { useState, useEffect, Fragment } from "react";
import { api, download } from "./api";
import { ApprovalChart, DirTrend, AttributionChart, ChartCanvas, COLORS } from "./charts.jsx";

const pct = (v) => (v == null ? "n/a" : (v * 100).toFixed(1) + "%");
const f2 = (v) => (v == null ? "n/a" : Number(v).toFixed(2));
const sev = (s) => <span className={"badge b-" + s}>{s}</span>;
const when = (s) => (s ? s.replace("T", " ").slice(0, 16) + " UTC" : "");
const naira = (v) => "₦" + Math.round(v).toLocaleString();

function useLoad(fn, deps) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { let live = true; setError(""); fn().then((d) => live && setData(d)).catch((e) => live && setError(e.message)); return () => { live = false; }; }, deps);
  return [data, error, setData];
}

/* ------------------------------------------------------------------ Overview */
export function Overview({ model, role, reload, tick, goto }) {
  const [runs, e1] = useLoad(() => api("/monitoring/runs?model_id=" + model.model_id), [model.model_id, tick]);
  const [scen] = useLoad(() => api("/demo/scenarios"), []);
  const [busy, setBusy] = useState(""), [msg, setMsg] = useState(""), [err, setErr] = useState("");
  const [scenario, setScenario] = useState("inflation");
  const [showReg, setShowReg] = useState(false);
  const latest = runs && runs[0];
  const m = latest && latest.metrics;
  const th = (m && m.thresholds) || model.thresholds;

  const act = async (label, fn) => {
    setBusy(label); setErr(""); setMsg("");
    try { setMsg(await fn()); reload(); } catch (e) { setErr(e.message); } finally { setBusy(""); }
  };
  const run = () => act("run", async () => {
    const r = await api("/monitoring/runs", { method: "POST", body: { model_id: model.model_id, window_days: 1 } });
    return `Run #${r.run_id} complete in ${r.seconds}s: ${r.metrics.violations.length} violation(s), ${r.new_findings} new finding(s).`;
  });
  const sim = () => act("sim", async () => {
    const r = await api("/demo/simulate", { method: "POST", body: { model_id: model.model_id, scenario, n: 2500 } });
    return `${r.added} applications logged under scenario "${scen[scenario]}". Now run monitoring.`;
  });
  const canRun = role === "risk_officer", canSim = ["admin", "risk_officer", "model_owner"].includes(role);

  return (
    <>
      {!latest ? (
        <div className="banner grey"><h2>No monitoring run yet for this model</h2>
          <div className="muted">{canRun ? "Press “Run monitoring” to evaluate the last 24 hours of decisions against the policy bundle." : "A Risk Officer needs to run monitoring first."}</div></div>
      ) : m.violations.length ? (
        <div className="banner red"><h2>Policy status: {m.violations.length} violation{m.violations.length > 1 ? "s" : ""} (run #{latest.run_id}, policy bundle #{latest.policy_version})</h2>
          {m.violations.map((v) => <div key={v.rule_id} className="viol">{sev(v.severity)}<code>{v.rule_id}</code><span>{v.message}</span></div>)}
          <div style={{ marginTop: 10 }}><button className="btn sm ghost" onClick={() => goto("findings")}>Open findings register →</button></div></div>
      ) : (
        <div className="banner green"><h2>Policy status: compliant (run #{latest.run_id}, policy bundle #{latest.policy_version})</h2>
          <div className="muted">All active policies passed over {m.n_current.toLocaleString()} decisions in the window ({when(latest.window_start)} to {when(latest.window_end)}).</div></div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          {canRun && <button className="btn" disabled={!!busy} onClick={run}>{busy === "run" ? "Running…" : "Run monitoring"}</button>}
          {canSim && <>
            <span className="muted small" style={{ marginLeft: canRun ? 14 : 0 }}>Simulate incoming applications:</span>
            <select className="sel" value={scenario} onChange={(e) => setScenario(e.target.value)}>{scen && Object.entries(scen).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <button className="btn ghost" disabled={!!busy} onClick={sim}>{busy === "sim" ? "Generating…" : "Inject scenario"}</button></>}
          {latest && <span style={{ marginLeft: "auto" }} className="row">
            <button className="btn ghost sm" onClick={() => download(`/reports/${latest.run_id}?format=pdf`, `governance_report_run${latest.run_id}.pdf`)}>Export PDF</button>
            <button className="btn ghost sm" onClick={() => download(`/reports/${latest.run_id}?format=csv`, `governance_report_run${latest.run_id}.csv`)}>Export CSV</button></span>}
        </div>
        {msg && <div className="ok">{msg}</div>}{(err || e1) && <div className="err">{err || e1}</div>}
      </div>

      {latest && <>
        <div className="grid g4" style={{ marginBottom: 16 }}>
          <div className={"card kpi " + (m.fairness.di_ratio < th.di_min ? "bad" : "good")}><div className="lbl">Disparate impact ratio</div><div className="val">{f2(m.fairness.di_ratio)}</div><div className="sub">minimum {th.di_min.toFixed(2)} (four-fifths rule)</div></div>
          <div className={"card kpi " + (m.fairness.eo_diff != null && Math.abs(m.fairness.eo_diff) > th.eo_max ? "bad" : "good")}><div className="lbl">Equal opportunity difference</div><div className="val">{f2(m.fairness.eo_diff)}</div><div className="sub">tolerance {th.eo_max.toFixed(2)}</div></div>
          <div className={"card kpi " + (m.explainability.protected_share > th.protected_share_max ? "bad" : "good")}><div className="lbl">Gender share of explanations</div><div className="val">{pct(m.explainability.protected_share)}</div><div className="sub">limit {pct(th.protected_share_max)}</div></div>
          <div className={"card kpi " + (m.explainability.coverage < 1 ? "bad" : "good")}><div className="lbl">Explanation coverage</div><div className="val">{pct(m.explainability.coverage)}</div><div className="sub">of {m.explainability.decisions_due.toLocaleString()} decisions</div></div>
        </div>
        <div className="grid g2">
          <div className="card"><h3>Approval rate by gender</h3><div className="hint">Latest window, {m.n_current.toLocaleString()} decisions</div>
            <ApprovalChart women={m.fairness.approval_rate_unprivileged} men={m.fairness.approval_rate_privileged} /></div>
          <div className="card"><h3>Disparate impact ratio over time</h3><div className="hint">One point per monitoring run</div>
            <DirTrend runs={runs} threshold={th.di_min} /></div>
        </div>
      </>}

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Model record</h3>
        <table><tbody>
          <tr><td className="muted" style={{ width: 170 }}>Purpose</td><td>{model.purpose || <span className="badge b-high">missing</span>}</td></tr>
          <tr><td className="muted">Owner (first line)</td><td>{model.owner || <span className="badge b-high">no named owner</span>}</td></tr>
          <tr><td className="muted">Next review date</td><td>{model.review_date || "—"}</td></tr>
          <tr><td className="muted">Protected attributes</td><td>{(model.protected_attributes || []).join(", ")}</td></tr>
          <tr><td className="muted">Decisions logged</td><td>{model.decision_count.toLocaleString()}</td></tr>
        </tbody></table>
        {["admin", "model_owner"].includes(role) && <div style={{ marginTop: 12 }}>
          <button className="btn ghost sm" onClick={() => setShowReg(!showReg)}>{showReg ? "Cancel" : "Register another model"}</button>
          {showReg && <RegisterModel done={() => { setShowReg(false); reload(); }} />}</div>}
      </div>
    </>
  );
}

function RegisterModel({ done }) {
  const [f, setF] = useState({ name: "", owner: "", purpose: "", version: "1.0", artifact: "loan_scorer_v1", review_date: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async () => { try { await api("/models", { method: "POST", body: f }); done(); } catch (e) { setErr(e.message); } };
  return <div style={{ marginTop: 12, maxWidth: 520 }}>
    <label className="f">Model name<input value={f.name} onChange={set("name")} placeholder="e.g. sme-loan-scorer-v1" /></label>
    <label className="f">Owner (leave blank to see the accountability policy fire)<input value={f.owner} onChange={set("owner")} /></label>
    <label className="f">Purpose<input value={f.purpose} onChange={set("purpose")} /></label>
    <div className="row"><label className="f" style={{ flex: 1 }}>Version<input value={f.version} onChange={set("version")} /></label>
      <label className="f" style={{ flex: 1 }}>Review date<input type="date" value={f.review_date} onChange={set("review_date")} /></label></div>
    <label className="f">Model artefact behind the endpoint<select value={f.artifact} onChange={set("artifact")}><option value="loan_scorer_v1">loan_scorer_v1</option><option value="loan_scorer_v2">loan_scorer_v2</option></select></label>
    {err && <div className="err">{err}</div>}<button className="btn" onClick={submit}>Register model</button></div>;
}

/* ------------------------------------------------------------------ Decision explorer */
export function Decisions({ model, role, tick }) {
  const [filter, setFilter] = useState("");
  const [n, setN] = useState(0);
  const [rows] = useLoad(() => api(`/decisions?model_id=${model.model_id}&limit=40` + (filter ? "&prediction=" + filter : "")), [model.model_id, filter, n, tick]);
  const [sel, setSel] = useState(null);
  const canApply = ["admin", "risk_officer", "model_owner"].includes(role);
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(380px,1fr) 1.3fr", alignItems: "start" }}>
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}><h3 style={{ margin: 0, flex: 1 }}>Recent decisions</h3>
          <select className="sel" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">All</option><option value="1">Approved</option><option value="0">Declined</option></select></div>
        <div style={{ maxHeight: 430, overflow: "auto", border: "1px solid var(--line)", borderRadius: 8 }}><table><thead style={{ position: "sticky", top: 0, background: "#fff" }}><tr><th>ID</th><th>Applicant</th><th>Gender</th><th>Income</th><th>Score</th><th>Outcome</th></tr></thead>
          <tbody>{(rows || []).map((r) => <tr key={r.decision_id} className={"click" + (sel === r.decision_id ? " sel" : "")} onClick={() => setSel(r.decision_id)}>
            <td>{r.decision_id}</td><td className="small">{r.subject_pseudonym}</td><td>{r.features.gender}</td><td>{naira(r.features.income)}</td><td>{r.features.credit_score}</td>
            <td>{r.prediction ? <span className="badge b-ok">Approved</span> : <span className="badge b-high">Declined</span>}</td></tr>)}</tbody></table></div>
        {canApply && <NewApplication model={model} onDone={(id) => { setN(n + 1); setSel(id); }} />}
      </div>
      <div style={{ position: "sticky", top: 12 }}>{sel ? <Explanation id={sel} /> : <div className="card muted">Select a decision on the left to see why the model decided as it did.</div>}</div>
    </div>
  );
}

function NewApplication({ model, onDone }) {
  const [f, setF] = useState({ age: 34, income: 2400000, credit_score: 600, loan_amount: 1800000, gender: "F" });
  const [res, setRes] = useState(null), [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: k === "gender" ? e.target.value : +e.target.value });
  const go = async () => {
    setErr("");
    try { const r = await api("/demo/apply", { method: "POST", body: { model_id: model.model_id, ...f } }); setRes(r); onDone(r.decision_id); } catch (e) { setErr(e.message); }
  };
  return <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--line)" }}>
    <h3>Submit a live application</h3><div className="hint">Acts as the client application: goes through the monitoring proxy, is logged, and explained.</div>
    <div className="grid g2" style={{ gap: "0 12px" }}>
      <label className="f">Age<input type="number" value={f.age} onChange={set("age")} /></label>
      <label className="f">Gender<select value={f.gender} onChange={set("gender")}><option value="F">Female</option><option value="M">Male</option></select></label>
      <label className="f">Annual income (₦)<input type="number" value={f.income} onChange={set("income")} /></label>
      <label className="f">Credit score<input type="number" value={f.credit_score} onChange={set("credit_score")} /></label>
      <label className="f">Loan amount (₦)<input type="number" value={f.loan_amount} onChange={set("loan_amount")} /></label></div>
    <button className="btn" onClick={go}>Score application</button>
    {res && <span className="small muted" style={{ marginLeft: 12 }}>Decision #{res.decision_id}: {res.prediction ? "approved" : "declined"} (score {res.score.toFixed(2)}) in {res.ms} ms</span>}
    {err && <div className="err">{err}</div>}</div>;
}

function Explanation({ id }) {
  const [n, setN] = useState(0);
  const [shap, e1] = useLoad(() => api("/explain/" + id + "?method=shap"), [id, n]);
  useEffect(() => { if (shap && shap.status === "pending") { const t = setTimeout(() => setN(n + 1), 500); return () => clearTimeout(t); } }, [shap]);
  const [lime] = useLoad(() => api("/explain/" + id + "?method=lime"), [id]);
  if (e1) return <div className="card err">{e1}</div>;
  if (!shap || shap.status === "pending") return <div className="card muted">Explanation is being generated in the background…</div>;
  const gender = shap.attributions.gender_f;
  return (
    <div className="grid">
      <div className="card">
        <div className="row"><h3 style={{ margin: 0, flex: 1 }}>Decision #{shap.decision_id}</h3>
          {shap.prediction ? <span className="badge b-ok">Approved</span> : <span className="badge b-high">Declined</span>}<span className="muted small">score {shap.score.toFixed(3)} · {when(shap.created_at)}</span></div>
        {shap.reason_codes.length > 0 && <div className="reason"><b>Customer-facing reason codes</b>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{shap.reason_codes.map((r) => <li key={r}>{r}</li>)}</ul></div>}
        {Math.abs(gender) > 0.15 && <div className="banner red" style={{ marginTop: 10, marginBottom: 0 }}><b>Protected attribute in use:</b> gender moved this decision by {gender > 0 ? "+" : ""}{gender.toFixed(2)} (log-odds). This is what policy rule <code>GENDER_ATTRIBUTION</code> detects across the portfolio.</div>}
      </div>
      <div className="card"><h3>SHAP attributions</h3><div className="hint">Contribution of each input to this decision, in log-odds units (base value {shap.base_value.toFixed(2)}).</div>
        <AttributionChart attributions={shap.attributions} features={shap.features} unit="log-odds" /></div>
      <div className="card"><h3>LIME attributions</h3><div className="hint">Independent local linear approximation, in probability units. Agreement between SHAP and LIME builds confidence in the explanation.</div>
        {lime ? <><AttributionChart attributions={lime.attributions} features={lime.features} unit="probability" />
          {lime.rules && <div className="small muted" style={{ marginTop: 8 }}>{Object.values(lime.rules).join(" · ")}</div>}</> : <div className="muted">Computing…</div>}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ Drift */
export function DriftPage({ model, tick }) {
  const [runs] = useLoad(() => api("/monitoring/runs?model_id=" + model.model_id), [model.model_id, tick]);
  const latest = runs && runs[0];
  const [d] = useLoad(() => (latest ? api("/drift/" + latest.run_id) : Promise.resolve([])), [latest && latest.run_id]);
  if (!runs) return <div className="muted">Loading…</div>;
  if (!latest) return <div className="card muted">No monitoring run yet. Run monitoring from the Fairness overview.</div>;
  const pd = latest.metrics.prediction_drift;
  const nice = { age: "Age", income: "Income", credit_score: "Credit score", loan_amount: "Loan amount", gender: "Gender" };
  return (
    <>
      <div className="grid g2">
        <div className="card"><h3>Input drift by feature (run #{latest.run_id})</h3>
          <div className="hint">Current window ({latest.metrics.n_current.toLocaleString()} decisions) against the reference history ({latest.metrics.n_reference.toLocaleString()}). KS test for numeric features, chi-squared for categorical; p-values adjusted across features by Benjamini–Hochberg.</div>
          <table><thead><tr><th>Feature</th><th>Test</th><th>Statistic</th><th>Adjusted p</th><th>Result</th></tr></thead>
            <tbody>{(d || []).map((r) => <tr key={r.drift_id}><td>{nice[r.feature] || r.feature}</td><td>{r.test.toUpperCase()}</td><td>{r.statistic.toFixed(3)}</td><td>{r.p_adjusted < 0.0001 ? "< 0.0001" : r.p_adjusted.toFixed(4)}</td>
              <td>{r.drifted ? <span className="badge b-high">Drifted</span> : <span className="badge b-ok">Stable</span>}</td></tr>)}</tbody></table>
          {d && d.length === 0 && <div className="muted small" style={{ marginTop: 8 }}>Not enough reference history to test drift.</div>}</div>
        <div className="card"><h3>Prediction drift: approval rate</h3><div className="hint">A shift of 5 points or more that is also statistically significant raises <code>DRIFT_PREDICTION</code>.</div>
          {pd.ref_rate != null ? <>
            <ChartCanvas height={200} config={{ type: "bar", data: { labels: ["Reference", "Current window"], datasets: [{ data: [pd.ref_rate * 100, pd.cur_rate * 100], backgroundColor: [COLORS.grey, pd.drifted ? COLORS.red : COLORS.navy], borderRadius: 4, barThickness: 60 }] },
              options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "Approval rate (%)" }, grid: { color: "#E6EBF2" } }, x: { grid: { display: false } } } } }} />
            <div style={{ marginTop: 8 }}>Shift <b>{(pd.shift * 100).toFixed(1)} points</b> · p = {pd.p_value < 0.0001 ? "< 0.0001" : pd.p_value.toFixed(4)} · {pd.drifted ? <span className="badge b-high">Drifted</span> : <span className="badge b-ok">Stable</span>}</div></> : <div className="muted">Not enough history.</div>}</div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ Findings */
export function Findings({ model, role, tick, reload }) {
  const [status, setStatus] = useState("");
  const [rows, err] = useLoad(() => api(`/findings?model_id=${model.model_id}` + (status ? "&status=" + status : "")), [model.model_id, status, tick]);
  const [act, setAct] = useState(null);
  const [open, setOpen] = useState(null);
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}><h3 style={{ margin: 0, flex: 1 }}>Findings for {model.name}</h3>
        <select className="sel" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="closed">Closed</option></select></div>
      <div className="hint">Append-only register: closing a finding adds a new record that supersedes the old one, so the full history is preserved for audit.</div>
      {err && <div className="err">{err}</div>}
      <table><thead><tr><th>#</th><th>Severity</th><th>Rule</th><th>Finding</th><th>Status</th><th>Owner</th><th>First raised</th><th></th></tr></thead>
        <tbody>{(rows || []).map((f) => <Fragment key={f.finding_id}>
          <tr><td>{f.finding_id}</td><td>{sev(f.severity)}</td><td><code>{f.rule_id}</code></td><td>{f.message}{f.justification && <div className="small muted">Justification: {f.justification}</div>}</td>
            <td><span className={"badge " + (f.status === "closed" ? "b-ok" : f.status === "acknowledged" ? "b-medium" : "b-high")}>{f.status}</span></td><td className="small">{f.owner}</td><td className="small">{when(f.first_raised_at)}</td>
            <td style={{ whiteSpace: "nowrap" }}>{role === "risk_officer" && f.status !== "closed" && <>
              {f.status === "open" && <button className="btn sm ghost" onClick={() => api("/findings/" + f.finding_id, { method: "PATCH", body: { status: "acknowledged" } }).then(reload)}>Acknowledge</button>} <button className="btn sm" onClick={() => setAct(f)}>Close…</button></>}
              {f.history.length > 1 && <button className="btn sm ghost" style={{ marginLeft: 6 }} onClick={() => setOpen(open === f.finding_id ? null : f.finding_id)}>History</button>}</td></tr>
          {open === f.finding_id && <tr key={"h" + f.finding_id}><td></td><td colSpan={7}><table className="hist"><thead><tr><th>Record</th><th>Status</th><th>By</th><th>At</th><th>Justification</th></tr></thead>
            <tbody>{f.history.map((h) => <tr key={h.finding_id}><td>{h.finding_id}</td><td>{h.status}</td><td>{h.recorded_by}</td><td>{when(h.raised_at)}</td><td>{h.justification || ""}</td></tr>)}</tbody></table></td></tr>}
        </Fragment>)}</tbody></table>
      {rows && rows.length === 0 && <div className="muted" style={{ padding: 14 }}>No findings.</div>}
      {act && <CloseModal f={act} onClose={() => setAct(null)} done={() => { setAct(null); reload(); }} />}
    </div>
  );
}

function CloseModal({ f, onClose, done }) {
  const [j, setJ] = useState(""), [err, setErr] = useState("");
  const go = async () => { try { await api("/findings/" + f.finding_id, { method: "PATCH", body: { status: "closed", justification: j } }); done(); } catch (e) { setErr(e.message); } };
  return <div className="modal" onClick={onClose}><div className="box" onClick={(e) => e.stopPropagation()}>
    <h3>Close finding #{f.finding_id} <code>{f.rule_id}</code></h3><div className="muted small" style={{ marginBottom: 10 }}>{f.message}</div>
    <label className="f">Justification (required, kept permanently in the register)<textarea rows={4} value={j} onChange={(e) => setJ(e.target.value)} placeholder="e.g. Model v1 withdrawn from production on 12 Nov; v2 promoted after remediation sign-off by the Model Risk Committee." /></label>
    {err && <div className="err">{err}</div>}<div className="row"><button className="btn" onClick={go}>Close finding</button><button className="btn ghost" onClick={onClose}>Cancel</button></div></div></div>;
}

/* ------------------------------------------------------------------ Maturity */
function preview(scores, dims) {
  const w = dims.reduce((s, d) => s + d.weight * scores[d.id], 0);
  const raw = Math.min(5, Math.max(1, Math.floor(w + 0.5)));
  const cap = Math.min(...dims.map((d) => scores[d.id])) + 1;
  return { w, level: Math.min(raw, cap), capped: raw > cap, raw };
}

export function Maturity({ role, tick, reload }) {
  const [fw] = useLoad(() => api("/assessments/framework"), []);
  const [hist] = useLoad(() => api("/assessments"), [tick]);
  const [inst, setInst] = useState("Demo Bank Plc");
  const [scores, setScores] = useState({ M1: 3, M2: 3, M3: 3, M4: 3, M5: 3, M6: 3, M7: 3 });
  const [msg, setMsg] = useState(""), [err, setErr] = useState("");
  if (!fw) return <div className="muted">Loading…</div>;
  const p = preview(scores, fw.dimensions);
  const submit = async () => { setErr(""); try { const r = await api("/assessments", { method: "POST", body: { institution: inst, scores } }); setMsg(`Saved: level ${r.level} (${r.level_name}), weighted score ${r.weighted_score}${r.capped ? ", capped by the lowest-dimension rule" : ""}.`); reload(); } catch (e) { setErr(e.message); } };
  const can = role === "risk_officer";
  return (
    <div className="grid g2" style={{ alignItems: "start" }}>
      <div className="card"><h3>Score the institution (1 to 5 per dimension)</h3>
        <label className="f">Institution<input value={inst} onChange={(e) => setInst(e.target.value)} disabled={!can} /></label>
        <div className="scores">{fw.dimensions.map((d) => <Fragment key={d.id}><div><b>{d.id}</b> {d.name} <span className="muted small">(weight {d.weight.toFixed(2)})</span></div>
          <select disabled={!can} value={scores[d.id]} onChange={(e) => setScores({ ...scores, [d.id]: +e.target.value })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} · {fw.levels[n]}</option>)}</select></Fragment>)}</div>
        {!can && <div className="muted small" style={{ marginTop: 10 }}>Only a Risk Officer can record an assessment. The calculator above still works as a preview.</div>}
        {can && <div style={{ marginTop: 14 }}><button className="btn" onClick={submit}>Record assessment</button></div>}
        {msg && <div className="ok">{msg}</div>}{err && <div className="err">{err}</div>}</div>
      <div>
        <div className="card"><h3>Result</h3>
          <div className="row" style={{ gap: 24 }}><div><div className="muted small">Weighted score</div><div className="level">{p.w.toFixed(2)}</div></div>
            <div><div className="muted small">Maturity level</div><div className="level">{p.level} <span style={{ fontSize: 20 }}>{fw.levels[p.level]}</span></div></div></div>
          {p.capped && <div className="banner red" style={{ marginTop: 12, marginBottom: 0 }}>The weighted score alone would give level {p.raw}, but no institution may be assessed above its lowest-scoring dimension plus one. Raise the weakest dimension to move up.</div>}</div>
        <div className="card" style={{ marginTop: 16 }}><h3>Assessment history</h3>
          <table className="hist"><thead><tr><th>Institution</th><th>Score</th><th>Level</th><th>By</th><th>When</th></tr></thead>
            <tbody>{(hist || []).map((a) => <tr key={a.assessment_id}><td>{a.institution}</td><td>{a.weighted_score.toFixed(2)}</td><td>{a.level} {a.level_name}{a.capped ? " (capped)" : ""}</td><td>{a.assessed_by}</td><td>{when(a.assessed_at)}</td></tr>)}</tbody></table>
          {hist && !hist.length && <div className="muted small">None yet.</div>}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Taxonomy */
export function Taxonomy({ models }) {
  const [tax] = useLoad(() => api("/taxonomy"), []);
  const [mid, setMid] = useState(models[0] && models[0].model_id);
  const [runs] = useLoad(() => (mid ? api("/monitoring/runs?model_id=" + mid) : Promise.resolve([])), [mid]);
  if (!tax) return <div className="muted">Loading…</div>;
  const viol = new Set(((runs && runs[0] && runs[0].metrics.violations) || []).map((v) => v.rule_id));
  const hasRun = runs && runs.length > 0;
  const domains = [...new Set(tax.map((r) => r.domain))];
  const testable = tax.filter((r) => r.testable === "yes").length, live = tax.filter((r) => r.live_rules.length).length;
  const tag = { yes: ["Machine-testable", "b-info"], partial: ["Partly testable", "b-low"], no: ["Organisational", "b-low"], assessment: ["Assessment only", "b-low"] };
  return (
    <>
      <div className="card" style={{ marginBottom: 6 }}><div className="row"><div style={{ flex: 1 }}><b>{tax.length} risks in {domains.length} domains.</b> {testable} are fully machine-testable in principle; this prototype tests <b>{live}</b> of them live. The rest need evidence from people and documents, which is what the maturity assessment captures.</div>
        <span className="muted small">Status for</span><select className="sel" value={mid} onChange={(e) => setMid(+e.target.value)}>{models.map((m) => <option key={m.model_id} value={m.model_id}>{m.name}</option>)}</select></div></div>
      {domains.map((d) => <div key={d} className="dom"><h4>{d} · {tax.find((r) => r.domain === d).domain_name} <span className="muted small" style={{ fontWeight: 400 }}>— {tax.find((r) => r.domain === d).anchor}</span></h4>
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(250px,1fr))" }}>{tax.filter((r) => r.domain === d).map((r) => {
          const isLive = r.live_rules.length > 0, bad = r.live_rules.some((x) => viol.has(x));
          return <div className="risk" key={r.id} style={bad ? { borderColor: "#E8B4AE", background: "var(--redbg)" } : {}}>
            <div className="row"><span className="id">{r.id}</span>{isLive && hasRun && (bad ? <span className="badge b-high">Violation now</span> : <span className="badge b-ok">Passing</span>)}{isLive && !hasRun && <span className="badge b-info">Live test</span>}</div>
            <div style={{ margin: "4px 0 6px" }}>{r.name}</div><span className={"badge " + tag[r.testable][1]}>{tag[r.testable][0]}</span>
            {isLive && <div className="small muted" style={{ marginTop: 6 }}>Rule: {r.live_rules.join(", ")}</div>}</div>; })}</div></div>)}
    </>
  );
}

/* ------------------------------------------------------------------ Admin */
export function Admin({ role, tick, reload }) {
  const isAdmin = role === "admin";
  const [pols] = useLoad(() => api("/policies"), [tick]);
  const [users] = useLoad(() => (isAdmin ? api("/users") : Promise.resolve([])), [tick]);
  const [view, setView] = useState(null);
  const [form, setForm] = useState({ name: "fairness", rego_source: "" });
  const [msg, setMsg] = useState(""), [err, setErr] = useState("");
  const [nu, setNu] = useState({ username: "", password: "", role: "auditor", display_name: "" });
  const latest = {};
  (pols || []).slice().reverse().forEach((p) => { latest[p.name] = p; });
  const load = (name) => setForm({ name, rego_source: latest[name] ? latest[name].rego_source : "" });
  const upload = async () => { setErr(""); setMsg(""); try { const r = await api("/policies", { method: "POST", body: form }); setMsg(`Policy "${form.name}" saved as version ${r.version}. Takes effect on the next monitoring run.`); reload(); } catch (e) { setErr(e.message); } };
  const mk = async () => { setErr(""); setMsg(""); try { await api("/users", { method: "POST", body: nu }); setMsg("User created."); setNu({ ...nu, username: "", password: "" }); reload(); } catch (e) { setErr(e.message); } };
  return (
    <div className="grid g2" style={{ alignItems: "start" }}>
      <div className="card"><h3>Policy bundle (Rego)</h3><div className="hint">Each upload is validated by Open Policy Agent and stored as a new version; earlier versions are kept so any past run can be tied to the rules in force.</div>
        <table><thead><tr><th>Policy</th><th>Ver.</th><th>Approved by</th><th>Effective</th><th></th></tr></thead>
          <tbody>{(pols || []).map((p) => <tr key={p.policy_id}><td>{p.name}</td><td>{p.version}</td><td>{p.approved_by}</td><td className="small">{when(p.effective_from)}</td><td><button className="btn sm ghost" onClick={() => setView(p)}>View</button></td></tr>)}</tbody></table>
        {isAdmin && <div style={{ marginTop: 16 }}><h3>Upload a new policy version</h3>
          <label className="f">Policy<select value={form.name} onChange={(e) => load(e.target.value)}>{Object.keys(latest).map((n) => <option key={n}>{n}</option>)}</select></label>
          <div className="row" style={{ marginBottom: 8 }}><button className="btn sm ghost" onClick={() => load(form.name)}>Load current source</button></div>
          <label className="f"><textarea rows={10} style={{ fontFamily: "Consolas,monospace", fontSize: 12 }} value={form.rego_source} onChange={(e) => setForm({ ...form, rego_source: e.target.value })} /></label>
          <button className="btn" onClick={upload}>Validate and save</button></div>}
        {!isAdmin && <div className="muted small" style={{ marginTop: 12 }}>Only an Administrator can upload policies. The person who writes a policy is deliberately not the person who can close findings.</div>}
        {msg && <div className="ok">{msg}</div>}{err && <div className="err">{err}</div>}</div>
      <div className="card"><h3>Users and roles</h3>
        {isAdmin ? <><table><thead><tr><th>User</th><th>Role</th><th>Name</th></tr></thead><tbody>{(users || []).map((u) => <tr key={u.user_id}><td>{u.username}</td><td>{u.role}</td><td>{u.display_name}</td></tr>)}</tbody></table>
          <div style={{ marginTop: 16 }}><h3>Add a user</h3>
            <div className="grid g2" style={{ gap: "0 12px" }}><label className="f">Username<input value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} /></label>
              <label className="f">Password (8+ characters)<input type="password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} /></label>
              <label className="f">Display name<input value={nu.display_name} onChange={(e) => setNu({ ...nu, display_name: e.target.value })} /></label>
              <label className="f">Role<select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}>{["admin", "model_owner", "risk_officer", "auditor", "service"].map((r) => <option key={r}>{r}</option>)}</select></label></div>
            <button className="btn" onClick={mk}>Create user</button></div></> : <div className="muted">User management is restricted to the Administrator role.</div>}</div>
      {isAdmin && <div className="card"><h3>Demo data</h3><div className="hint">Clears all decisions, runs, findings and assessments and regenerates the demo history. Use before a presentation so the 24-hour monitoring window is full.</div>
        <button className="btn red" onClick={async () => { if (window.confirm("Reset all demo data?")) { await api("/demo/reset", { method: "POST" }); setMsg("Demo data reset."); reload(); } }}>Reset demo data</button></div>}
      {view && <div className="modal" onClick={() => setView(null)}><div className="box" style={{ width: "min(720px,94vw)" }} onClick={(e) => e.stopPropagation()}><h3>{view.name} · version {view.version}</h3><div className="mono">{view.rego_source}</div><div style={{ marginTop: 12 }}><button className="btn" onClick={() => setView(null)}>Close</button></div></div></div>}
    </div>
  );
}
