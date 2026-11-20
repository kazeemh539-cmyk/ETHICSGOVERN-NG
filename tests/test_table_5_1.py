"""Table 5.1 test cases TC-01 .. TC-12 (each test name carries its ID). Needs the Model API on :5001."""
import os, sys, tempfile, io
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "data"))
os.environ["EGNG_DB"] = os.path.join(tempfile.mkdtemp(), "tc.db")
import app as A
from engine import fairness, drift, explain
from generate_synthetic import generate

A.seed()
C = A.app.test_client()
tok = lambda u: {"Authorization": "Bearer " + C.post("/api/v1/auth/login", json={"username": u, "password": "Demo@2025"}).json["token"]}


def test_TC01_demographic_parity_balanced_window():
    df = generate(n=200000, bias=0.0, seed=5)
    m = fairness.compute_metrics(df.decision, df.gender)
    assert abs(m["dpd"]) < 0.01


def test_TC02_disparate_impact_with_30pct_bias():
    df = generate(n=10000, bias=0.30, seed=1000)
    assert fairness.compute_metrics(df.decision, df.gender)["di_ratio"] < 0.80


def test_TC03_equal_opportunity_matches_hand_calculation():
    pred = np.array([1, 1, 0, 1, 1, 0, 0, 0]); y = np.ones(8, dtype=int); g = np.array(["M"] * 4 + ["F"] * 4)
    assert abs(fairness.compute_metrics(pred, g, y)["eo_diff"] - (3 / 4 - 1 / 4)) < 1e-12


def test_TC04_single_group_window_is_a_handled_error():
    mid = C.post("/api/v1/models", json={"name": "single-group-test", "owner": "x", "purpose": "p", "version": "1", "artifact": "loan_scorer_v1"}, headers=tok("owner")).json["model_id"]
    m = A.get_model(mid)
    for f in generate(n=120, seed=3).query("gender=='M'").head(100)[["age", "income", "credit_score", "loan_amount", "gender"]].to_dict("records"):
        A.log_decision(m, f, 1, 0.9)
    r = C.post("/api/v1/monitoring/runs", json={"model_id": mid, "window_days": 1}, headers=tok("riskofficer"))
    assert r.status_code == 422 and "cannot be computed" in r.json["error"]


def test_TC05_ks_unshifted_feature_not_flagged():
    flagged = 0
    for s in range(20):
        a, b = generate(5000, seed=100 + s), generate(5000, seed=200 + s)
        flagged += any(r["drifted"] for r in drift.feature_drift(a, b))
    assert flagged <= 2   # family-wise error held near alpha=0.05 across 20 trials


def test_TC06_ks_feature_shifted_by_one_sd_flagged():
    a, b = generate(5000, seed=1), generate(5000, seed=2)
    b["credit_score"] = b["credit_score"] + 90   # one standard deviation of the generator
    assert {r["feature"]: r["drifted"] for r in drift.feature_drift(a, b)}["credit_score"]


def test_TC07_shap_additivity():
    f = {"age": 41, "income": 4_100_000, "credit_score": 580, "loan_amount": 3_000_000, "gender": "M"}
    e = explain.explain_shap("loan_scorer_v1", f)
    raw = float(explain._load("loan_scorer_v1")["model"].predict(explain._row(f), output_margin=True)[0])
    assert abs(e["base_value"] + sum(e["attributions"].values()) - raw) < 1e-3


def test_TC08_violation_creates_assigned_finding_with_correct_severity():
    C.post("/api/v1/monitoring/runs", json={"model_id": 1, "window_days": 1}, headers=tok("riskofficer"))
    fs = C.get("/api/v1/findings?model_id=1", headers=tok("auditor")).json
    di = next(f for f in fs if f["rule_id"] == "DI_RATIO")
    assert di["severity"] == "high" and di["owner"] and di["status"] == "open"


def test_TC09_auditor_cannot_close_finding():
    fid = C.get("/api/v1/findings?model_id=1", headers=tok("auditor")).json[0]["finding_id"]
    assert C.patch("/api/v1/findings/%d" % fid, json={"status": "closed", "justification": "attempt by auditor"}, headers=tok("auditor")).status_code == 403


def test_TC10_report_pdf_contains_metrics_findings_and_policy_version():
    from pypdf import PdfReader
    run = C.get("/api/v1/monitoring/runs?model_id=1", headers=tok("auditor")).json[0]
    pdf = C.get("/api/v1/reports/%d?format=pdf" % run["run_id"], headers=tok("auditor")).data
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Disparate impact ratio" in text and "DI_RATIO" in text and ("policy bundle #%s" % run["policy_version"]) in text


def test_TC11_maturity_level_capped_at_lowest_dimension_plus_one():
    r = C.post("/api/v1/assessments", json={"institution": "t", "scores": {"M1": 2, "M2": 5, "M3": 5, "M4": 5, "M5": 5, "M6": 5, "M7": 5}}, headers=tok("riskofficer")).json
    assert r["level"] == 3 and r["capped"]


def test_TC12_explanation_before_task_completion_returns_202_pending():
    did = C.get("/api/v1/decisions?model_id=1&limit=1", headers=tok("auditor")).json[0]["decision_id"]
    A.db.x("DELETE FROM explanations WHERE decision_id=?", (did,))
    A._pending.add(did)
    r = C.get("/api/v1/explain/%d" % did, headers=tok("auditor"))
    A._pending.discard(did)
    assert r.status_code == 202 and r.json["status"] == "pending"
