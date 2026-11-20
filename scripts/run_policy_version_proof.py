"""Evidence for the claim that every monitoring run records the policy bundle that evaluated it (section 3.4.5).
Procedure: run monitoring on the biased model (run A), upload a new version of the fairness policy that adds a
stricter rule, run monitoring again (run B), then show that (1) each run still names the bundle it used,
(2) the earlier policy version is still stored unchanged, (3) the two runs produced different findings, and
(4) the report for run A, regenerated after the upload, still names the old bundle."""
import os, sys, json, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EGNG_DB"] = os.path.join(tempfile.mkdtemp(), "proof.db")
import app as A
A.seed()
C = A.app.test_client()
def tok(u): return {"Authorization": "Bearer " + C.post("/api/v1/auth/login", json={"username": u, "password": "Demo@2025"}).json["token"]}
ro, ad = tok("riskofficer"), tok("admin")
pol0 = {p["policy_id"]: p for p in C.get("/api/v1/policies", headers=ad).json}
fair0 = [p for p in pol0.values() if p["name"] == "fairness"][0]
runA = C.post("/api/v1/monitoring/runs", json={"model_id": 1, "window_days": 1}, headers=ro).json
newsrc = fair0["rego_source"] + '''
# Added in version 2: demographic parity gap rule, which version 1 of the bundle did not have
violation[{"rule_id": "DPD_GAP", "severity": "medium", "message": msg}] {
    input.metrics.dpd != null
    input.metrics.dpd < -0.10
    msg := sprintf("Demographic parity difference %v is more than 0.10 below parity", [round(input.metrics.dpd * 100) / 100])}
'''
up = C.post("/api/v1/policies", json={"name": "fairness", "rego_source": newsrc}, headers=ad)
runB = C.post("/api/v1/monitoring/runs", json={"model_id": 1, "window_days": 1}, headers=ro).json
# a clean model under the new bundle, to show the new rule is live
runC = C.post("/api/v1/monitoring/runs", json={"model_id": 2, "window_days": 1}, headers=ro).json
pol1 = {p["policy_id"]: p for p in C.get("/api/v1/policies", headers=ad).json}
repA = C.get("/api/v1/reports/%d?format=json" % runA["run_id"], headers=ro).json
def rules(r): return sorted(v["rule_id"] for v in r["metrics"]["violations"])
out = {
  "upload_status": up.status_code, "upload": up.json,
  "policy_rows_before": len(pol0), "policy_rows_after": len(pol1),
  "old_fairness_version_unchanged": pol1[fair0["policy_id"]]["rego_source"] == fair0["rego_source"],
  "runA": {"run_id": runA["run_id"], "policy_version": C.get("/api/v1/monitoring/runs/%d" % runA["run_id"], headers=ro).json["policy_version"], "rules": rules(runA)},
  "runB": {"run_id": runB["run_id"], "policy_version": C.get("/api/v1/monitoring/runs/%d" % runB["run_id"], headers=ro).json["policy_version"], "rules": rules(runB)},
  "runC_clean_model": {"run_id": runC["run_id"], "policy_version": C.get("/api/v1/monitoring/runs/%d" % runC["run_id"], headers=ro).json["policy_version"], "rules": rules(runC)},
  "report_for_runA_after_upload_names_bundle": (repA.get("policy_bundle") or repA.get("run", {}).get("policy_version") or json.dumps(repA)[:300]),
}
json.dump(out, open(os.path.join(ROOT, "docs", "results", "policy_version_proof.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
