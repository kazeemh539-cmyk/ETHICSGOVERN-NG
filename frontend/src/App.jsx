import { useState, useEffect, useCallback } from "react";
import { api, setToken, hasToken } from "./api";
import { Overview, Decisions, DriftPage, Findings, Maturity, Taxonomy, Admin } from "./pages.jsx";

const DEMO = [["admin", "Administrator"], ["owner", "Model Owner"], ["riskofficer", "Risk Officer"], ["auditor", "Auditor"]];

function Login({ onLogin }) {
  const [u, setU] = useState("riskofficer"), [p, setP] = useState("Demo@2025"), [e, setE] = useState("");
  const go = async (ev) => {
    ev && ev.preventDefault();
    try { const r = await api("/auth/login", { method: "POST", body: { username: u, password: p } }); setToken(r.token); onLogin(r); }
    catch (x) { setE(x.message); }
  };
  return (
    <form className="login" onSubmit={go}>
      <h1>EthicsGovern-NG</h1>
      <p>Explainable AI governance for Nigerian banks</p>
      <label className="f">Username<input value={u} onChange={(x) => setU(x.target.value)} autoFocus /></label>
      <label className="f">Password<input type="password" value={p} onChange={(x) => setP(x.target.value)} /></label>
      {e && <div className="err">{e}</div>}
      <button className="btn" style={{ width: "100%" }}>Sign in</button>
      <div className="small muted" style={{ marginTop: 16 }}>Demo accounts (password <b>Demo@2025</b>). Pick a role:</div>
      <div className="chips">{DEMO.map(([k, l]) => <span key={k} className="chip" onClick={() => { setU(k); setP("Demo@2025"); }}>{l}</span>)}</div>
    </form>
  );
}

const PAGES = [
  ["overview", "Fairness overview"], ["decisions", "Decision explorer"], ["drift", "Drift monitor"],
  ["findings", "Findings register"], ["maturity", "Maturity assessment"], ["taxonomy", "Risk taxonomy"], ["admin", "Administration"],
];

export default function App() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState("overview");
  const [models, setModels] = useState([]);
  const [modelId, setModelId] = useState(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {  // resume a session after a page refresh
    if (hasToken() && !user) {
      api("/models").then(() => { try { setUser(JSON.parse(sessionStorage.getItem("egng_user"))); } catch (e) {} }).catch(() => setToken(null));
    }
  }, []);
  useEffect(() => {
    if (!user) return;
    api("/models").then((m) => { setModels(m); if (!modelId && m.length) setModelId(m[0].model_id); });
  }, [user, tick]);

  if (!user) return <Login onLogin={(r) => { try { sessionStorage.setItem("egng_user", JSON.stringify(r)); } catch (e) {} setUser(r); }} />;
  const model = models.find((m) => m.model_id === modelId);
  const ctx = { user, role: user.role, models, model, modelId, reload, tick, goto: setPage };
  const Page = { overview: Overview, decisions: Decisions, drift: DriftPage, findings: Findings, maturity: Maturity, taxonomy: Taxonomy, admin: Admin }[page];
  const scoped = !["maturity", "taxonomy", "admin"].includes(page);

  return (
    <div className="app">
      <aside className="side">
        <div className="brand"><b>EthicsGovern-NG</b><span>AI governance dashboard</span></div>
        <nav className="nav">{PAGES.map(([k, l]) => <button key={k} className={page === k ? "on" : ""} onClick={() => setPage(k)}>{l}</button>)}</nav>
        <div className="who"><b>{user.name}</b><div className="role">{user.role.replace("_", " ")}</div>
          <button onClick={() => { setToken(null); try { sessionStorage.removeItem("egng_user"); } catch (e) {} setUser(null); }}>Sign out</button></div>
      </aside>
      <main className="main">
        <div className="top">
          <h1>{PAGES.find((p) => p[0] === page)[1]}</h1>
          {scoped && <select className="sel" value={modelId || ""} onChange={(e) => setModelId(+e.target.value)}>
            {models.map((m) => <option key={m.model_id} value={m.model_id}>{m.name} (v{m.version})</option>)}</select>}
        </div>
        {model || !scoped ? <Page {...ctx} /> : <div className="muted">Loading…</div>}
      </main>
    </div>
  );
}
