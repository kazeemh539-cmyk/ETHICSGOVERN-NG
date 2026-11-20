"""End-to-end API tests. Needs the Model API running on :5001 (run.bat / launcher does this)."""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EGNG_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import pytest
import app as A

A.seed()
C = A.app.test_client()


def tok(u):
    return {"Authorization": "Bearer " + C.post("/api/v1/auth/login", json={"username": u, "password": "Demo@2025"}).json["token"]}


def test_login_and_rbac():
    assert C.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    assert C.get("/api/v1/models").status_code == 401
    assert C.get("/api/v1/models", headers=tok("auditor")).status_code == 200
    # Table 4.3 role rules
    assert C.post("/api/v1/monitoring/runs", json={"model_id": 1}, headers=tok("auditor")).status_code == 403
    assert C.post("/api/v1/policies", json={"name": "x", "rego_source": "package x"}, headers=tok("risk_officer" if False else "riskofficer")).status_code == 403
    assert C.post("/api/v1/predict/1", json={}, headers=tok("riskofficer")).status_code == 403
    assert C.patch("/api/v1/findings/1", json={"status": "closed"}, headers=tok("owner")).status_code == 403


def test_biased_model_is_flagged_and_clean_model_is_not():
    r1 = C.post("/api/v1/monitoring/runs", json={"model_id": 1, "window_days": 1}, headers=tok("riskofficer")).json
    r2 = C.post("/api/v1/monitoring/runs", json={"model_id": 2, "window_days": 1}, headers=tok("riskofficer")).json
    ids1 = {v["rule_id"] for v in r1["metrics"]["violations"]}
    ids2 = {v["rule_id"] for v in r2["metrics"]["violations"]}
    assert {"DI_RATIO", "GENDER_ATTRIBUTION"} <= ids1
    assert ids2 == set(), ids2


def test_scenario_triggers_drift():
    assert C.post("/api/v1/demo/simulate", json={"model_id": 2, "scenario": "inflation", "n": 2500}, headers=tok("riskofficer")).status_code == 201
    r = C.post("/api/v1/monitoring/runs", json={"model_id": 2, "window_days": 1}, headers=tok("riskofficer")).json
    ids = {v["rule_id"] for v in r["metrics"]["violations"]}
    assert "DRIFT_FEATURE" in ids and "DRIFT_PREDICTION" in ids


def test_findings_are_append_only():
    fs = C.get("/api/v1/findings?model_id=1", headers=tok("auditor")).json
    f = next(x for x in fs if x["rule_id"] == "DI_RATIO")
    assert C.patch("/api/v1/findings/%d" % f["finding_id"], json={"status": "closed", "justification": "short"}, headers=tok("riskofficer")).status_code == 400
    ok = C.patch("/api/v1/findings/%d" % f["finding_id"], json={"status": "closed", "justification": "Model v1 withdrawn; v2 promoted."}, headers=tok("riskofficer"))
    assert ok.status_code == 200
    assert C.patch("/api/v1/findings/%d" % f["finding_id"], json={"status": "open"}, headers=tok("riskofficer")).status_code == 409
    after = C.get("/api/v1/findings?model_id=1", headers=tok("auditor")).json
    head = next(x for x in after if x["rule_id"] == "DI_RATIO" or x["finding_id"] == ok.json["finding_id"])
    assert head["status"] == "closed" and len(head["history"]) == 2


def test_predict_logs_and_explains():
    r = C.post("/api/v1/predict/1", json={"age": 30, "income": 2500000, "credit_score": 610, "loan_amount": 2000000, "gender": "F"}, headers=tok("service")).json
    e = C.get("/api/v1/explain/%d" % r["decision_id"], headers=tok("auditor")).json
    assert e["method"] == "shap" and "credit_score" in e["attributions"]
    l = C.get("/api/v1/explain/%d?method=lime" % r["decision_id"], headers=tok("auditor")).json
    assert l["method"] == "lime"


def test_policy_upload_validated_and_versioned():
    bad = C.post("/api/v1/policies", json={"name": "fairness", "rego_source": "package ethicsgovern.fairness\nviolation[x] {{{"}, headers=tok("admin"))
    assert bad.status_code == 422
    good = C.post("/api/v1/policies", json={"name": "fairness", "rego_source": open(os.path.join(ROOT, "policies", "fairness.rego")).read()}, headers=tok("admin"))
    assert good.status_code == 201 and good.json["version"] == 2


def test_maturity_cap_rule():
    r = C.post("/api/v1/assessments", json={"institution": "Test Bank", "scores": {"M1": 1, "M2": 5, "M3": 5, "M4": 5, "M5": 5, "M6": 5, "M7": 5}}, headers=tok("riskofficer")).json
    assert r["capped"] and r["level"] == 2   # lowest dimension 1, so no higher than level 2


def test_report_formats():
    for fmt, mt in [("csv", "text/csv"), ("pdf", "application/pdf"), ("json", "application/json")]:
        rr = C.get("/api/v1/reports/1?format=" + fmt, headers=tok("auditor"))
        assert rr.status_code == 200 and mt in rr.content_type
