"""EthicsGovern-NG API (Flask). Implements Table 4.3 plus a few supporting endpoints.

Lite-build notes: SQLite instead of PostgreSQL; a background thread + queue instead of
Celery/Redis; scipy instead of Alibi Detect. Behaviour and endpoint contract are unchanged.
"""
import os, io, sys, csv, json, time, queue, hashlib, secrets, threading, datetime as dt
from functools import wraps

import bcrypt, jwt, requests
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory, Response, g

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "data"))
import db
from engine import fairness, drift, explain, policy
from generate_synthetic import generate

MODEL_API = os.environ.get("EGNG_MODEL_API", "http://127.0.0.1:5001")
SECRET_FILE = os.path.join(ROOT, ".jwt_secret")
if not os.path.exists(SECRET_FILE):
    open(SECRET_FILE, "w").write(secrets.token_hex(32))
SECRET = open(SECRET_FILE).read().strip()
EXPLAIN_GRACE_SECONDS = 60
DEFAULT_THRESHOLDS = {"di_min": 0.80, "eo_max": 0.10, "protected_share_max": 0.05}
ROLES = ["admin", "model_owner", "risk_officer", "auditor", "service"]
ANY = ROLES

app = Flask(__name__, static_folder=None)
_http = requests.Session()


# ------------------------------------------------------------------ helpers
def now():
    return dt.datetime.utcnow().replace(microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def err(msg, code=400):
    return jsonify({"error": msg}), code


def auth(*roles):
    allowed = set(roles or ANY)

    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            h = request.headers.get("Authorization", "")
            if not h.startswith("Bearer "):
                return err("Authentication required", 401)
            try:
                g.user = jwt.decode(h[7:], SECRET, algorithms=["HS256"])
            except jwt.PyJWTError:
                return err("Invalid or expired token", 401)
            if g.user["role"] not in allowed:
                return err("Role '%s' is not permitted to do this" % g.user["role"], 403)
            return fn(*a, **kw)
        return wrapper
    return deco


def parse(row, *cols):
    if row:
        for c in cols:
            if row.get(c) is not None:
                row[c] = json.loads(row[c])
    return row


def get_model(mid):
    return parse(db.q("SELECT * FROM models WHERE model_id=?", (mid,), one=True), "thresholds", "protected_attributes")


def pseudonym(features):
    return "APP-" + hashlib.sha1((json.dumps(features, sort_keys=True) + secrets.token_hex(4)).encode()).hexdigest()[:8].upper()


REASON_TEXT = {
    "credit_score": "credit score", "income": "level of income", "loan_amount": "size of the loan requested",
    "age": "age", "gender_f": "gender",
}


# ------------------------------------------------------------------ auth
@app.post("/api/v1/auth/login")
def login():
    b = request.get_json(force=True)
    u = db.q("SELECT * FROM users WHERE username=?", (b.get("username", ""),), one=True)
    if not u or not bcrypt.checkpw(b.get("password", "").encode(), u["password_hash"].encode()):
        return err("Wrong username or password", 401)
    tok = jwt.encode({"sub": u["username"], "role": u["role"], "name": u["display_name"],
                      "exp": dt.datetime.utcnow() + dt.timedelta(hours=8)}, SECRET, algorithm="HS256")
    return {"token": tok, "role": u["role"], "name": u["display_name"], "username": u["username"]}


@app.get("/api/v1/users")
@auth("admin")
def list_users():
    return jsonify(db.q("SELECT user_id, username, role, display_name, created_at FROM users"))


@app.post("/api/v1/users")
@auth("admin")
def create_user():
    b = request.get_json(force=True)
    if b.get("role") not in ROLES:
        return err("Unknown role")
    if len(b.get("password", "")) < 8:
        return err("Password must be at least 8 characters")
    try:
        uid = db.x("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
                   (b["username"], bcrypt.hashpw(b["password"].encode(), bcrypt.gensalt()).decode(), b["role"],
                    b.get("display_name", b["username"]), iso(now())))
    except Exception:
        return err("Username already exists", 409)
    return {"user_id": uid}, 201


# ------------------------------------------------------------------ models
@app.get("/api/v1/models")
@auth()
def list_models():
    rows = db.q("SELECT * FROM models")
    for r in rows:
        parse(r, "thresholds", "protected_attributes")
        r["decision_count"] = db.q("SELECT COUNT(*) n FROM decisions WHERE model_id=?", (r["model_id"],), one=True)["n"]
        last = db.q("SELECT run_id, created_at FROM monitoring_runs WHERE model_id=? ORDER BY run_id DESC LIMIT 1",
                    (r["model_id"],), one=True)
        r["last_run"] = last
        r["open_findings"] = len(open_findings(r["model_id"]))
    return jsonify(rows)


@app.post("/api/v1/models")
@auth("admin", "model_owner")
def register_model():
    b = request.get_json(force=True)
    if not b.get("name"):
        return err("Model name is required")
    th = dict(DEFAULT_THRESHOLDS, **(b.get("thresholds") or {}))
    try:
        mid = db.x("""INSERT INTO models(name,owner,purpose,version,protected_attributes,thresholds,endpoint_url,review_date,artifact)
                      VALUES(?,?,?,?,?,?,?,?,?)""",
                   (b["name"], b.get("owner", ""), b.get("purpose", ""), b.get("version", ""),
                    db.j(b.get("protected_attributes", ["gender"])), db.j(th),
                    b.get("endpoint_url", MODEL_API + "/predict/" + b.get("artifact", b["name"])),
                    b.get("review_date", ""), b.get("artifact", b["name"].replace("-", "_"))))
    except Exception:
        return err("A model with that name already exists", 409)
    return {"model_id": mid}, 201


@app.get("/api/v1/models/<int:mid>")
@auth()
def one_model(mid):
    m = get_model(mid)
    return (jsonify(m), 200) if m else err("Model not found", 404)


# ------------------------------------------------------------------ inference (monitoring proxy)
_expl_q = queue.Queue()
_pending = set()   # decision ids queued for explanation but not yet explained


def enqueue_explanation(did):
    _pending.add(did)
    _expl_q.put(did)


def _explain_worker():
    while True:
        did = _expl_q.get()
        try:
            store_explanation(did, "shap")
        except Exception as e:  # never let the worker die
            print("explanation worker error:", e)
        finally:
            _pending.discard(did)
            _expl_q.task_done()


threading.Thread(target=_explain_worker, daemon=True).start()


def store_explanation(decision_id, method):
    d = db.q("SELECT * FROM decisions WHERE decision_id=?", (decision_id,), one=True)
    if not d:
        return None
    m = get_model(d["model_id"])
    feats = json.loads(d["features"])
    e = explain.explain(m["artifact"], feats, method)
    payload = {"attributions": e["attributions"], **({"rules": e["rules"]} if "rules" in e else {})}
    db.x("INSERT INTO explanations(decision_id,method,attributions,base_value,generated_at) VALUES(?,?,?,?,?)",
         (decision_id, method, db.j(payload), e["base_value"], iso(now())))
    return e


def log_decision(model, feats, pred, score, when=None):
    return db.x("""INSERT INTO decisions(model_id,features,prediction,score,subject_pseudonym,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (model["model_id"], db.j(feats), int(pred), float(score), pseudonym(feats), iso(when or now())))


@app.post("/api/v1/predict/<int:mid>")
@auth("service")
def predict(mid):
    m = get_model(mid)
    if not m:
        return err("Model not found", 404)
    feats = request.get_json(force=True)
    r = _http.post("%s/predict/%s" % (MODEL_API, m["artifact"]), json=feats, timeout=10)
    if r.status_code != 200:
        return err("Model endpoint error", 502)
    out = r.json()
    did = log_decision(m, feats, out["prediction"], out["score"])
    enqueue_explanation(did)
    return {"decision_id": did, "prediction": out["prediction"], "score": out["score"]}


@app.get("/api/v1/decisions")
@auth()
def list_decisions():
    mid = request.args.get("model_id", type=int)
    lim = min(request.args.get("limit", 40, type=int), 200)
    pred = request.args.get("prediction", type=int)
    sql, args = "SELECT * FROM decisions WHERE model_id=?", [mid]
    if pred in (0, 1):
        sql += " AND prediction=?"; args.append(pred)
    sql += " ORDER BY decision_id DESC LIMIT ?"; args.append(lim)
    rows = db.q(sql, tuple(args))
    for r in rows:
        r["features"] = json.loads(r["features"])
    return jsonify(rows)


# ------------------------------------------------------------------ explanations
@app.get("/api/v1/explain/<int:did>")
@auth()
def get_explanation(did):
    method = request.args.get("method", "shap")
    d = db.q("SELECT * FROM decisions WHERE decision_id=?", (did,), one=True)
    if not d:
        return err("Decision not found", 404)
    ex = db.q("SELECT * FROM explanations WHERE decision_id=? AND method=? ORDER BY explanation_id DESC LIMIT 1",
              (did, method), one=True)
    if not ex and method == "shap":
        if did in _pending:  # queued but the worker has not finished yet
            return {"decision_id": did, "status": "pending"}, 202
    if not ex:
        store_explanation(did, method)  # on demand when the worker has not reached it
        ex = db.q("SELECT * FROM explanations WHERE decision_id=? AND method=? ORDER BY explanation_id DESC LIMIT 1",
                  (did, method), one=True)
    payload = json.loads(ex["attributions"])
    attrs = payload["attributions"]
    # plain-language reason codes: the factors that pushed the decision toward decline
    adverse = sorted([(k, v) for k, v in attrs.items() if v < 0], key=lambda kv: kv[1])[:3]
    reasons = [("Your %s counted against this application" % REASON_TEXT.get(k, k)) for k, _ in adverse]
    return {"decision_id": did, "model_id": d["model_id"], "features": json.loads(d["features"]),
            "prediction": d["prediction"], "score": d["score"], "created_at": d["created_at"],
            "method": method, "base_value": ex["base_value"], "attributions": attrs,
            "rules": payload.get("rules"), "reason_codes": reasons if d["prediction"] == 0 else []}


# ------------------------------------------------------------------ monitoring
def _df(rows):
    f = pd.DataFrame([json.loads(r["features"]) for r in rows])
    f["prediction"] = [r["prediction"] for r in rows]
    f["outcome"] = [r["outcome"] for r in rows]
    return f


def latest_policies():
    rows = db.q("SELECT * FROM policies ORDER BY policy_id")
    latest = {}
    for r in rows:
        if r["effective_from"] <= iso(now()):
            latest[r["name"]] = r
    return latest


def open_findings(model_id=None):
    sql = """SELECT f.* FROM findings f WHERE NOT EXISTS (SELECT 1 FROM findings s WHERE s.supersedes_finding_id=f.finding_id)
             AND f.status != 'closed'"""
    args = ()
    if model_id:
        sql += " AND f.model_id=?"; args = (model_id,)
    return db.q(sql, args)


def run_monitoring(model, window_days, user):
    t_end = now()
    t_start = t_end - dt.timedelta(days=window_days)
    cur_rows = db.q("SELECT * FROM decisions WHERE model_id=? AND created_at>=? AND created_at<=?",
                    (model["model_id"], iso(t_start), iso(t_end)))
    ref_rows = db.q("SELECT * FROM decisions WHERE model_id=? AND created_at<? ORDER BY decision_id DESC LIMIT 6000",
                    (model["model_id"], iso(t_start)))
    if len(cur_rows) < 50:
        raise ValueError("Only %d decisions in the last %s day(s); at least 50 are needed" % (len(cur_rows), window_days))
    cur = _df(cur_rows)
    for grp, label in (("F", "women"), ("M", "men")):
        if int((cur["gender"] == grp).sum()) < 30:
            raise ValueError("Fewer than 30 %s applicants in the window; group fairness metrics cannot be computed. Widen the window." % label)
    th = dict(DEFAULT_THRESHOLDS, **(model["thresholds"] or {}))

    # fairness (FR-04)
    obs = cur.dropna(subset=["outcome"])
    fm = fairness.compute_metrics(cur["prediction"], cur["gender"],
                                  y_true=None)
    if len(obs) >= 50:
        fm["eo_diff"] = fairness.compute_metrics(obs["prediction"], obs["gender"], obs["outcome"].astype(int))["eo_diff"]
        fm["tpr_unprivileged"] = fairness.compute_metrics(obs["prediction"], obs["gender"], obs["outcome"].astype(int))["tpr_unprivileged"]
        fm["tpr_privileged"] = fairness.compute_metrics(obs["prediction"], obs["gender"], obs["outcome"].astype(int))["tpr_privileged"]

    # drift (FR-08, FR-09)
    feat_drift, pred_drift = [], {"drifted": False, "shift": 0.0, "ref_rate": None, "cur_rate": None, "p_value": None}
    if len(ref_rows) >= 200:
        ref = _df(ref_rows)
        feat_drift = drift.feature_drift(ref, cur)
        pred_drift = drift.prediction_drift(ref["prediction"].values, cur["prediction"].values)

    # explainability coverage and protected-attribute share
    cutoff = iso(t_end - dt.timedelta(seconds=EXPLAIN_GRACE_SECONDS))
    due_ids = [r["decision_id"] for r in cur_rows if r["created_at"] <= cutoff]
    covered = 0
    shares = []
    if due_ids:
        ph = ",".join("?" * len(due_ids))
        have = db.q("SELECT DISTINCT decision_id FROM explanations WHERE method='shap' AND decision_id IN (%s)" % ph, tuple(due_ids)) \
            if len(due_ids) < 900 else None
        if have is None:  # large windows: count with a join
            covered = db.q("""SELECT COUNT(DISTINCT e.decision_id) n FROM explanations e JOIN decisions d ON d.decision_id=e.decision_id
                              WHERE e.method='shap' AND d.model_id=? AND d.created_at>=? AND d.created_at<=?""",
                           (model["model_id"], iso(t_start), cutoff), one=True)["n"]
        else:
            covered = len(have)
        sample = due_ids[-400:]
        for ex in db.q("SELECT attributions FROM explanations WHERE method='shap' AND decision_id IN (%s)" % ",".join("?" * len(sample)),
                       tuple(sample)):
            a = json.loads(ex["attributions"])["attributions"]
            shares.append(a)
    coverage = (covered / len(due_ids)) if due_ids else 1.0
    protected_share = None
    if shares:
        mean_abs = pd.DataFrame(shares).abs().mean()
        protected_share = float(mean_abs.get("gender_f", 0) / mean_abs.sum()) if mean_abs.sum() else 0.0

    # accountability inputs
    today = iso(now())[:10]
    acc = {"owner": (model["owner"] or "").strip(),
           "review_overdue": bool(model["review_date"]) and model["review_date"] < today,
           "documentation_complete": bool(model["purpose"] and model["version"] and model["protected_attributes"])}

    opa_input = {
        "model": {"id": model["model_id"], "name": model["name"], "thresholds": th},
        "metrics": {"di_ratio": fm["di_ratio"], "eo_diff": fm["eo_diff"], "dpd": fm["dpd"]},
        "drift": {"drifted_features": [r["feature"] for r in feat_drift if r["drifted"]], "prediction": pred_drift},
        "explainability": {"coverage": coverage, "protected_share": protected_share},
        "accountability": acc,
    }
    pols = latest_policies()
    violations = policy.evaluate(opa_input, [(n, p["rego_source"]) for n, p in sorted(pols.items())])
    bundle_version = max(p["policy_id"] for p in pols.values())

    metrics = {"fairness": fm, "prediction_drift": pred_drift, "explainability": {"coverage": coverage, "protected_share": protected_share,
               "decisions_due": len(due_ids)}, "violations": violations, "thresholds": th,
               "n_current": len(cur_rows), "n_reference": len(ref_rows)}
    run_id = db.x("""INSERT INTO monitoring_runs(model_id,window_start,window_end,metrics,policy_version,created_at,triggered_by)
                     VALUES(?,?,?,?,?,?,?)""",
                  (model["model_id"], iso(t_start), iso(t_end), db.j(metrics), bundle_version, iso(now()), user))
    db.many("INSERT INTO drift_results(run_id,feature,test,statistic,p_value,drifted,p_adjusted) VALUES(?,?,?,?,?,?,?)",
            [(run_id, r["feature"], r["test"], r["statistic"], r["p_value"], int(r["drifted"]), r["p_adjusted"]) for r in feat_drift])

    # findings (FR-11): one open finding per model+rule; recurrence after closure raises a new one
    held = {f["rule_id"] for f in open_findings(model["model_id"])}
    pol_id = {"fairness": "fairness", "drift": "drift", "explainability": "explainability", "accountability": "accountability"}
    new = 0
    for v in violations:
        if v["rule_id"] in held:
            continue
        pid = pols.get(pol_id.get(v["package"]), {}).get("policy_id")
        db.x("""INSERT INTO findings(run_id,policy_id,model_id,rule_id,severity,status,owner,message,raised_at,recorded_by)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
             (run_id, pid, model["model_id"], v["rule_id"], v["severity"], "open", model["owner"] or "Unassigned",
              v["message"], iso(now()), "system"))
        new += 1
    return run_id, metrics, new


@app.post("/api/v1/monitoring/runs")
@auth("risk_officer")
def post_run():
    b = request.get_json(force=True)
    m = get_model(b.get("model_id"))
    if not m:
        return err("Model not found", 404)
    t0 = time.time()
    try:
        run_id, metrics, new = run_monitoring(m, float(b.get("window_days", 1)), g.user["sub"])
    except ValueError as e:
        return err(str(e), 422)
    return {"run_id": run_id, "new_findings": new, "seconds": round(time.time() - t0, 2), "metrics": metrics}, 201


@app.get("/api/v1/monitoring/runs")
@auth()
def list_runs():
    mid = request.args.get("model_id", type=int)
    rows = db.q("SELECT * FROM monitoring_runs WHERE model_id=? ORDER BY run_id DESC LIMIT 30", (mid,))
    return jsonify([parse(r, "metrics") for r in rows])


@app.get("/api/v1/monitoring/runs/<int:rid>")
@auth()
def get_run(rid):
    r = parse(db.q("SELECT * FROM monitoring_runs WHERE run_id=?", (rid,), one=True), "metrics")
    return (jsonify(r), 200) if r else err("Run not found", 404)


@app.get("/api/v1/drift/<int:rid>")
@auth()
def get_drift(rid):
    return jsonify(db.q("SELECT * FROM drift_results WHERE run_id=?", (rid,)))


# ------------------------------------------------------------------ findings
def finding_view(f):
    chain, cur = [], f
    all_f = {r["finding_id"]: r for r in db.q("SELECT * FROM findings WHERE model_id=?", (f["model_id"],))}
    while cur:
        chain.append(cur)
        cur = all_f.get(cur["supersedes_finding_id"])
    f = dict(f)
    f["first_raised_at"] = chain[-1]["raised_at"]
    f["history"] = [{k: c[k] for k in ("finding_id", "status", "justification", "recorded_by", "raised_at", "owner")} for c in reversed(chain)]
    return f


@app.get("/api/v1/findings")
@auth()
def list_findings():
    mid = request.args.get("model_id", type=int)
    status = request.args.get("status")
    sql = """SELECT f.* FROM findings f WHERE NOT EXISTS (SELECT 1 FROM findings s WHERE s.supersedes_finding_id=f.finding_id)"""
    args = []
    if mid:
        sql += " AND f.model_id=?"; args.append(mid)
    if status:
        sql += " AND f.status=?"; args.append(status)
    sql += " ORDER BY CASE f.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, f.finding_id DESC"
    return jsonify([finding_view(f) for f in db.q(sql, tuple(args))])


@app.patch("/api/v1/findings/<int:fid>")
@auth("risk_officer")
def patch_finding(fid):
    b = request.get_json(force=True)
    f = db.q("SELECT * FROM findings WHERE finding_id=?", (fid,), one=True)
    if not f:
        return err("Finding not found", 404)
    if db.q("SELECT 1 FROM findings WHERE supersedes_finding_id=?", (fid,), one=True):
        return err("This record has been superseded; act on the latest record", 409)
    status = b.get("status", f["status"])
    if status not in ("open", "acknowledged", "closed"):
        return err("Status must be open, acknowledged or closed")
    if status == "closed" and len((b.get("justification") or "").strip()) < 10:
        return err("A justification of at least 10 characters is required to close a finding")
    nid = db.x("""INSERT INTO findings(run_id,policy_id,model_id,rule_id,severity,status,owner,message,justification,
                  raised_at,closed_at,supersedes_finding_id,recorded_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (f["run_id"], f["policy_id"], f["model_id"], f["rule_id"], f["severity"], status,
                b.get("owner", f["owner"]), f["message"], b.get("justification"), iso(now()),
                iso(now()) if status == "closed" else None, fid, g.user["sub"]))
    return {"finding_id": nid, "supersedes": fid}


# ------------------------------------------------------------------ policies
@app.get("/api/v1/policies")
@auth()
def list_policies():
    return jsonify(db.q("SELECT * FROM policies ORDER BY policy_id DESC"))


@app.post("/api/v1/policies")
@auth("admin")
def post_policy():
    b = request.get_json(force=True)
    name, src = (b.get("name") or "").strip(), b.get("rego_source", "")
    if not name or not src.strip():
        return err("Policy name and Rego source are required")
    bundle = dict(latest_policies())
    test = [(n, p["rego_source"]) for n, p in bundle.items() if n != name] + [(name, src)]
    try:  # validate: the bundle must compile and evaluate
        policy.evaluate({"model": {"thresholds": DEFAULT_THRESHOLDS}, "metrics": {"di_ratio": 1, "eo_diff": None},
                         "drift": {"drifted_features": [], "prediction": {"drifted": False, "shift": 0}},
                         "explainability": {"coverage": 1, "protected_share": 0},
                         "accountability": {"owner": "x", "review_overdue": False, "documentation_complete": True}}, test)
    except Exception as e:
        return err("Policy rejected: " + str(e)[:300], 422)
    ver = (db.q("SELECT MAX(version) v FROM policies WHERE name=?", (name,), one=True)["v"] or 0) + 1
    pid = db.x("INSERT INTO policies(name,rego_source,version,effective_from,approved_by) VALUES(?,?,?,?,?)",
               (name, src, ver, iso(now()), g.user["sub"]))
    return {"policy_id": pid, "version": ver}, 201


# ------------------------------------------------------------------ maturity assessment
DIMENSIONS = [("M1", "Governance structure and accountability", 0.20), ("M2", "Model inventory and documentation", 0.15),
              ("M3", "Fairness assessment capability", 0.20), ("M4", "Explainability capability", 0.15),
              ("M5", "Monitoring and drift management", 0.15), ("M6", "Data protection alignment", 0.10),
              ("M7", "Third-party and vendor assurance", 0.05)]
LEVELS = {1: "Ad hoc", 2: "Aware", 3: "Defined", 4: "Managed", 5: "Optimising"}


def score_maturity(scores):
    weighted = sum(w * scores[k] for k, _, w in DIMENSIONS)
    raw = min(5, max(1, int(weighted + 0.5)))                 # weighted mean, rounded half-up
    cap = min(scores[k] for k, _, _ in DIMENSIONS) + 1        # no higher than lowest dimension + 1
    return round(weighted, 2), min(raw, cap), raw > cap


@app.get("/api/v1/assessments")
@auth()
def list_assessments():
    rows = db.q("SELECT * FROM assessments ORDER BY assessment_id DESC")
    for r in rows:
        parse(r, "dimension_scores")
        r["level_name"] = LEVELS[r["level"]]
    return jsonify(rows)


@app.get("/api/v1/assessments/framework")
@auth()
def framework():
    return jsonify({"dimensions": [{"id": k, "name": n, "weight": w} for k, n, w in DIMENSIONS], "levels": LEVELS})


@app.post("/api/v1/assessments")
@auth("risk_officer")
def post_assessment():
    b = request.get_json(force=True)
    try:
        scores = {k: int(b["scores"][k]) for k, _, _ in DIMENSIONS}
    except Exception:
        return err("Provide an integer score for every dimension M1 to M7")
    if any(s < 1 or s > 5 for s in scores.values()):
        return err("Scores must be between 1 and 5")
    ws, level, capped = score_maturity(scores)
    aid = db.x("INSERT INTO assessments(institution,dimension_scores,weighted_score,level,assessed_by,assessed_at,capped) VALUES(?,?,?,?,?,?,?)",
               (b.get("institution", "Unnamed institution"), db.j(scores), ws, level, g.user["sub"], iso(now()), int(capped)))
    return {"assessment_id": aid, "weighted_score": ws, "level": level, "level_name": LEVELS[level], "capped": capped}, 201


@app.get("/api/v1/taxonomy")
@auth()
def taxonomy():
    with open(os.path.join(ROOT, "data", "risk_taxonomy.json"), encoding="utf-8") as fh:
        return jsonify(json.load(fh))


# ------------------------------------------------------------------ reports
def report_payload(rid):
    r = parse(db.q("SELECT * FROM monitoring_runs WHERE run_id=?", (rid,), one=True), "metrics")
    if not r:
        return None
    m = get_model(r["model_id"])
    return {"run": r, "model": m, "drift": db.q("SELECT * FROM drift_results WHERE run_id=?", (rid,)),
            "findings": [finding_view(f) for f in db.q("SELECT * FROM findings WHERE run_id=?", (rid,))]}


@app.get("/api/v1/reports/<int:rid>")
@auth()
def report(rid):
    p = report_payload(rid)
    if not p:
        return err("Run not found", 404)
    fmt = request.args.get("format", "json")
    if fmt == "json":
        return jsonify(p)
    r, m, fm = p["run"], p["model"], p["run"]["metrics"]["fairness"]
    if fmt == "csv":
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(["EthicsGovern-NG governance report"]); w.writerow(["Model", m["name"], "Run", rid, "Policy bundle", r["policy_version"]])
        w.writerow(["Window", r["window_start"], r["window_end"]]); w.writerow([])
        w.writerow(["Metric", "Value"])
        for k in ("approval_rate_unprivileged", "approval_rate_privileged", "di_ratio", "dpd", "eo_diff"):
            w.writerow([k, fm.get(k)])
        w.writerow([]); w.writerow(["Violation", "Severity", "Message"])
        for v in r["metrics"]["violations"]:
            w.writerow([v["rule_id"], v["severity"], v["message"]])
        w.writerow([]); w.writerow(["Feature", "Test", "Statistic", "Adjusted p", "Drifted"])
        for d in p["drift"]:
            w.writerow([d["feature"], d["test"], round(d["statistic"], 4), round(d["p_adjusted"], 4), bool(d["drifted"])])
        return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=report_run%d.csv" % rid})
    if fmt == "pdf":
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        ss = getSampleStyleSheet(); buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, title="Governance report", leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        el = [Paragraph("EthicsGovern-NG: Model Governance Report", ss["Title"]),
              Paragraph("Model: <b>%s</b> (v%s) &nbsp; Owner: %s" % (m["name"], m["version"], m["owner"] or "<font color=red>NONE</font>"), ss["Normal"]),
              Paragraph("Monitoring run %d &nbsp; window %s to %s UTC &nbsp; policy bundle #%s" % (rid, r["window_start"], r["window_end"], r["policy_version"]), ss["Normal"]),
              Spacer(1, 12)]

        def tbl(rows, widths=None):
            t = Table(rows, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                   ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            return t
        f2 = lambda v: "n/a" if v is None else "%.3f" % v
        el += [Paragraph("Fairness", ss["Heading2"]),
               tbl([["Metric", "Value", "Threshold"],
                    ["Approval rate, women", f2(fm["approval_rate_unprivileged"]), ""],
                    ["Approval rate, men", f2(fm["approval_rate_privileged"]), ""],
                    ["Disparate impact ratio", f2(fm["di_ratio"]), ">= %.2f" % r["metrics"]["thresholds"]["di_min"]],
                    ["Equal opportunity difference", f2(fm["eo_diff"]), "<= %.2f" % r["metrics"]["thresholds"]["eo_max"]]], [200, 80, 100]),
               Paragraph("Policy violations", ss["Heading2"])]
        vs = r["metrics"]["violations"]
        el.append(tbl([["Rule", "Severity", "Message"]] + [[v["rule_id"], v["severity"], Paragraph(v["message"], ss["BodyText"])] for v in vs], [110, 60, 340])
                  if vs else Paragraph("No violations in this run.", ss["Normal"]))
        el += [Paragraph("Drift (Benjamini-Hochberg adjusted)", ss["Heading2"]),
               tbl([["Feature", "Test", "Statistic", "Adj. p", "Drifted"]] + [[d["feature"], d["test"], "%.3f" % d["statistic"], "%.4f" % d["p_adjusted"], "yes" if d["drifted"] else "no"] for d in p["drift"]]),
               Spacer(1, 10), Paragraph("Generated %s UTC. Synthetic data; prototype for academic demonstration." % iso(now()), ss["Italic"])]
        doc.build(el)
        return Response(buf.getvalue(), mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=report_run%d.pdf" % rid})
    return err("format must be json, csv or pdf")


# ------------------------------------------------------------------ demo tooling (not part of Table 4.3)
SCENARIOS = {
    "normal": {"label": "Normal business", "income_shock": 0.0, "new_to_bank": 0.0},
    "inflation": {"label": "Naira shock: real incomes fall 35%", "income_shock": 0.35, "new_to_bank": 0.0},
    "new_to_bank": {"label": "New-to-bank wave: 60% thin-file applicants", "income_shock": 0.0, "new_to_bank": 0.60},
}


def simulate(model, scenario, n, start_hours_ago, end_hours_ago, seed, explain_all=True):
    sc = SCENARIOS[scenario]
    df = generate(n=n, bias=0.0, seed=seed, income_shock=sc["income_shock"], new_to_bank=sc["new_to_bank"])
    feats = df[["age", "income", "credit_score", "loan_amount", "gender"]].to_dict("records")
    preds = []
    for i in range(0, n, 2000):
        r = _http.post("%s/predict/%s" % (MODEL_API, model["artifact"]), json={"instances": feats[i:i + 2000]}, timeout=60)
        r.raise_for_status(); preds += r.json()
    rng = np.random.default_rng(seed)
    t0 = now()
    stamps = sorted(rng.uniform(end_hours_ago, start_hours_ago, size=n), reverse=True)
    rows = [(model["model_id"], db.j(f), p["prediction"], p["score"], pseudonym(f), iso(t0 - dt.timedelta(hours=h)), int(o))
            for f, p, h, o in zip(feats, preds, stamps, df["repaid"])]
    with db._lock, db.conn() as c:
        first = c.execute("SELECT COALESCE(MAX(decision_id),0) FROM decisions").fetchone()[0] + 1
        c.executemany("INSERT INTO decisions(model_id,features,prediction,score,subject_pseudonym,created_at,outcome) VALUES(?,?,?,?,?,?,?)", rows)
    if explain_all:
        base, attrs = explain.shap_batch(model["artifact"], df[["age", "income", "credit_score", "loan_amount", "gender"]])
        stamp = iso(now())
        db.many("INSERT INTO explanations(decision_id,method,attributions,base_value,generated_at) VALUES(?,?,?,?,?)",
                [(first + i, "shap", db.j({"attributions": a}), base, stamp) for i, a in enumerate(attrs)])
    return n


@app.get("/api/v1/demo/scenarios")
@auth()
def scenarios():
    return jsonify({k: v["label"] for k, v in SCENARIOS.items()})


@app.post("/api/v1/demo/simulate")
@auth("admin", "risk_officer", "model_owner")
def demo_simulate():
    b = request.get_json(force=True)
    m = get_model(b.get("model_id"))
    if not m or b.get("scenario") not in SCENARIOS:
        return err("Unknown model or scenario")
    n = min(int(b.get("n", 2500)), 6000)
    simulate(m, b["scenario"], n, 23.5, 0.05, seed=int(time.time()) % 100000, explain_all=b.get("explain", True))
    return {"added": n, "scenario": b["scenario"]}, 201


@app.post("/api/v1/demo/apply")
@auth("admin", "risk_officer", "model_owner")
def demo_apply():
    """Client-application simulator: sends one live application through the monitoring proxy path."""
    b = request.get_json(force=True)
    m = get_model(b.get("model_id"))
    if not m:
        return err("Model not found", 404)
    feats = {k: b[k] for k in ("age", "income", "credit_score", "loan_amount", "gender")}
    t0 = time.perf_counter()
    r = _http.post("%s/predict/%s" % (MODEL_API, m["artifact"]), json=feats, timeout=10).json()
    did = log_decision(m, feats, r["prediction"], r["score"])
    enqueue_explanation(did)
    return {"decision_id": did, "prediction": r["prediction"], "score": r["score"], "ms": round((time.perf_counter() - t0) * 1000, 1)}


def reset_demo():
    with db._lock, db.conn() as c:
        for t in ("explanations", "drift_results", "findings", "monitoring_runs", "decisions", "assessments", "models", "policies", "users"):
            c.execute("DELETE FROM " + t)
        c.execute("DELETE FROM sqlite_sequence")
    seed(force=True)


@app.post("/api/v1/demo/reset")
@auth("admin")
def demo_reset():
    reset_demo()
    return {"status": "demo data reset"}


def is_stale():
    """True when the baseline window has aged out (the monitoring window is the last 24 hours)."""
    if not db.q("SELECT 1 FROM models LIMIT 1", one=True):
        return False
    cut = iso(now() - dt.timedelta(hours=24))
    return db.q("SELECT COUNT(*) n FROM decisions WHERE model_id=1 AND created_at>=?", (cut,), one=True)["n"] < 800


def seed(force=False):
    db.init()
    if db.q("SELECT 1 FROM users LIMIT 1", one=True) and not force:
        return
    pw = bcrypt.hashpw(b"Demo@2025", bcrypt.gensalt()).decode()
    for u, role, name in [("admin", "admin", "System Administrator"), ("owner", "model_owner", "Model Owner (Retail Credit)"),
                          ("riskofficer", "risk_officer", "Risk Officer (2nd line)"), ("auditor", "auditor", "Internal Auditor (3rd line)"),
                          ("service", "service", "Client application (service account)")]:
        db.x("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)", (u, pw, role, name, iso(now())))
    for fn, src in policy.load_default_policies():
        db.x("INSERT INTO policies(name,rego_source,version,effective_from,approved_by) VALUES(?,?,?,?,?)", (fn, src, 1, "2000-01-01T00:00:00", "admin"))
    review = iso(now() + dt.timedelta(days=90))[:10]
    models = [("loan-scorer-v1", "Head of Retail Scoring", "Personal loan approval scoring (current production model)", "1.0", "loan_scorer_v1"),
              ("loan-scorer-v2", "Head of Retail Scoring", "Personal loan approval scoring (remediated candidate)", "2.0", "loan_scorer_v2")]
    for name, owner, purpose, ver, art in models:
        mid = db.x("""INSERT INTO models(name,owner,purpose,version,protected_attributes,thresholds,endpoint_url,review_date,artifact)
                      VALUES(?,?,?,?,?,?,?,?,?)""",
                   (name, owner, purpose, ver, db.j(["gender"]), db.j(DEFAULT_THRESHOLDS), "%s/predict/%s" % (MODEL_API, art), review, art))
        m = get_model(mid)
        simulate(m, "normal", 3000, 24 * 55, 24 * 3, seed=11 + mid)       # reference history
        simulate(m, "normal", 2400, 23.5, 0.05, seed=77 + mid)            # today's baseline
    print("Seeded demo data.")


# ------------------------------------------------------------------ SPA
DIST = os.path.join(ROOT, "frontend", "dist")


@app.get("/")
@app.get("/<path:path>")
def spa(path="index.html"):
    if path.startswith("api/"):
        return err("Not found", 404)
    full = os.path.join(DIST, path)
    if not os.path.isfile(full):
        path = "index.html"
    return send_from_directory(DIST, path)


if __name__ == "__main__":
    seed()
    from waitress import serve
    print("EthicsGovern-NG on http://127.0.0.1:8000")
    serve(app, host="127.0.0.1", port=8000, threads=8)
