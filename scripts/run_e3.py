"""Experiment E3: latency overhead of the monitoring proxy (NFR-01: < 50 ms at p95).
1000 requests straight to the Model API and 1000 through the monitoring proxy
(auth + forward + decision log + enqueue explanation), interleaved, one client, warm connections."""
import os, sys, json, time, platform, numpy as np, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "data"))
from generate_synthetic import generate

API, MODEL = "http://127.0.0.1:8000/api/v1", "http://127.0.0.1:5001"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
s = requests.Session()
tok = s.post(API + "/auth/login", json={"username": "service", "password": "Demo@2025"}).json()["token"]
H = {"Authorization": "Bearer " + tok}
df = generate(n=N + 100, seed=424242)
reqs = df[["age", "income", "credit_score", "loan_amount", "gender"]].to_dict("records")
direct, proxy = [], []
for i, r in enumerate(reqs):
    t = time.perf_counter(); s.post(MODEL + "/predict/loan_scorer_v1", json=r).raise_for_status(); d = (time.perf_counter() - t) * 1000
    t = time.perf_counter(); s.post(API + "/predict/1", json=r, headers=H).raise_for_status(); p = (time.perf_counter() - t) * 1000
    if i >= 100:  # first 100 are warm-up
        direct.append(d); proxy.append(p)
direct, proxy = np.array(direct), np.array(proxy)
import pandas as pd
pd.DataFrame({"request": range(1, len(direct) + 1), "direct_ms": direct, "proxy_ms": proxy}).to_csv(os.path.join(ROOT, "docs", "results", "e3_raw_latency.csv"), index=False)
pc = lambda a, q: float(np.percentile(a, q))
res = {"n": N, "platform": platform.platform(), "python": platform.python_version(),
       "direct_ms": {"mean": direct.mean(), "p50": pc(direct, 50), "p95": pc(direct, 95), "p99": pc(direct, 99)},
       "proxy_ms": {"mean": proxy.mean(), "p50": pc(proxy, 50), "p95": pc(proxy, 95), "p99": pc(proxy, 99)},
       "overhead_ms": {"mean": float((proxy - direct).mean()), "p50": float(np.percentile(proxy - direct, 50)),
                       "p95_of_paired_difference": float(np.percentile(proxy - direct, 95)), "p95_minus_p95": pc(proxy, 95) - pc(direct, 95)}}
res["nfr01_met"] = res["overhead_ms"]["p95_minus_p95"] < 50
json.dump(res, open(os.path.join(ROOT, "docs", "results", "e3_latency.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
