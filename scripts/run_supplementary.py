"""Supplementary measurements for Chapter 5 (writes docs/results/supplementary.json).
(a) Sampling noise of the observed disparate impact ratio by window size (bias 0.20, 300 windows each).
(b) False-alarm rate of the unbiased model (loan-scorer-v2) over 200 independent 2,400-decision windows.
(c) Cost of generating one explanation (SHAP on the worker path; LIME on demand).
(d) How often customer-facing reason codes would cite gender for declined applicants (from the E2 table).
(e) SHAP/LIME sign agreement excluding gender; (f) explainer construction cost, fairness computation time on 10,000 rows,
    and the end-to-end time of a monitoring run through the API (needs the app on :8000; skipped if it is not running)."""
import os, sys, json, time, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "data")); sys.path.insert(0, os.path.join(ROOT, "model_api"))
from generate_synthetic import generate
from engine import fairness, explain
from train import prep
res = {}
# (a)
rows = []
for n in (1000, 2400, 5000, 10000, 20000, 40000):
    d = [fairness.compute_metrics(x.decision, x.gender)["di_ratio"] for x in (generate(n, bias=0.20, seed=70000 + s) for s in range(300))]
    rows.append({"n": n, "mean_dir": float(np.mean(d)), "sd_dir": float(np.std(d, ddof=1)), "p05": float(np.percentile(d, 5)), "p95": float(np.percentile(d, 95)),
                 "share_flagged": float(np.mean(np.array(d) < 0.80))})
res["noise_by_window"] = rows
# (b)
m = explain._load("loan_scorer_v2")["model"]; fa = 0; mins = []; eos = []
for s in range(200):
    df = generate(2400, bias=0.0, seed=5000 + s); p = (m.predict_proba(prep(df))[:, 1] >= 0.5).astype(int)
    r = fairness.compute_metrics(p, df.gender.values, df.repaid.values); fa += (r["di_ratio"] < 0.80) or (abs(r["eo_diff"]) > 0.10); mins.append(r["di_ratio"]); eos.append(abs(r["eo_diff"]))
res["false_alarms_clean_model"] = {"windows": 200, "window_size": 2400, "alarms": int(fa), "min_dir": float(min(mins)), "max_abs_eo": float(max(eos)), "sd_eo": float(np.std(eos))}
# (c)
feat = {"age": 35, "income": 3_000_000, "credit_score": 700, "loan_amount": 1_500_000, "gender": "F"}
explain.explain_shap("loan_scorer_v1", feat); explain.explain_lime("loan_scorer_v1", feat)
t = time.perf_counter(); [explain.explain_shap("loan_scorer_v1", feat) for _ in range(200)]; shap_ms = (time.perf_counter() - t) / 200 * 1000
t = time.perf_counter(); [explain.explain_lime("loan_scorer_v1", feat) for _ in range(100)]; lime_ms = (time.perf_counter() - t) / 100 * 1000
res["explanation_cost_ms"] = {"shap_single": shap_ms, "lime_single": lime_ms, "shap_throughput_per_second": 1000 / shap_ms}
# (d)
e2 = pd.read_csv(os.path.join(ROOT, "docs", "results", "e2_explanations.csv")); out = {}
for mod in ("v1", "v2"):
    d = e2[(e2.model == mod) & (e2.prediction == 0)]
    shap_cols = ["shap_age", "shap_income", "shap_credit_score", "shap_loan_amount", "shap_gender_f"]
    adverse3 = d[shap_cols].apply(lambda r: set(r.nsmallest(3).index[r.nsmallest(3) < 0]), axis=1)
    out[mod] = {"declined": int(len(d)), "reason_codes_cite_gender": int(sum("shap_gender_f" in s for s in adverse3)),
                "declined_women": int((d.gender_f == 1).sum()), "declined_women_cited_gender": int(sum(("shap_gender_f" in s) and g == 1 for s, g in zip(adverse3, d.gender_f)))}
res["reason_codes_citing_gender"] = out
# (e)
sa = {}
feats = ["age", "income", "credit_score", "loan_amount"]
for mod in ("v1", "v2"):
    d = e2[e2.model == mod]
    S = np.sign(d[["shap_" + f for f in feats]].values); L = np.sign(d[["lime_" + f for f in feats]].values)
    sa[mod] = float((S == L).mean())
res["sign_agreement_excluding_gender"] = sa
# (f)
import shap
from lime.lime_tabular import LimeTabularExplainer
c = explain._load("loan_scorer_v1")
t = time.perf_counter(); [shap.TreeExplainer(c["model"], c["bg"]) for _ in range(10)]; build = (time.perf_counter() - t) / 10 * 1000
dfm = generate(10000, bias=0.2, seed=1)
t = time.perf_counter(); [fairness.compute_metrics(dfm.decision, dfm.gender, dfm.repaid) for _ in range(200)]; fair_ms = (time.perf_counter() - t) / 200 * 1000
res["other_timings_ms"] = {"shap_explainer_construction": build, "fairness_metrics_10000_rows": fair_ms}
try:
    import requests
    B = "http://127.0.0.1:8000/api/v1"
    tok = requests.post(B + "/auth/login", json={"username": "riskofficer", "password": "Demo@2025"}, timeout=10).json()["token"]
    H = {"Authorization": "Bearer " + tok}; ts = []
    for _ in range(10):
        t = time.perf_counter(); r = requests.post(B + "/monitoring/runs", json={"model_id": 1}, headers=H, timeout=60); ts.append((time.perf_counter() - t) * 1000)
        assert r.status_code in (200, 201), r.text[:200]
    res["other_timings_ms"]["monitoring_run_end_to_end"] = {"runs": 10, "mean": float(np.mean(ts)), "max": float(max(ts))}
except Exception as ex:
    res["other_timings_ms"]["monitoring_run_end_to_end"] = "skipped: %s" % ex
json.dump(res, open(os.path.join(ROOT, "docs", "results", "supplementary.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
