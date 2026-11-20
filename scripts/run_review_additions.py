"""Additional analyses added after supervisor review (all computed from files already in the dataset package or from the engine):
  1. E1: confusion matrix with TN, precision, recall, F1 and 95% intervals per injection level (Clopper-Pearson; bootstrap for F1);
     failure analysis of the four errors.
  2. E3: paired bootstrap intervals for the added overhead, Wilcoxon signed-rank test, sequential single-client throughput.
  3. Drift: false-alarm rate of uncorrected versus Benjamini-Hochberg-corrected tests on stable windows.
  4. Maturity model: sensitivity of the assigned level to the weights and to the lowest-dimension cap.
Run:  python scripts/run_review_additions.py   (writes docs/results/review_additions.json)"""
import os, sys, json
import numpy as np, pandas as pd
from scipy import stats
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "data"))
RES = os.path.join(ROOT, "docs", "results")
out = {}
rng = np.random.default_rng(7)

def clopper(k, n, a=0.05):
    if n == 0: return [None, None]
    lo = 0.0 if k == 0 else float(stats.beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - a / 2, k + 1, n - k))
    return [lo, hi]

# 1. E1
e1 = pd.read_csv(os.path.join(RES, "e1_raw.csv"))
def conf(d):
    return (int((d.flag_di & d.truth_biased).sum()), int((d.flag_di & ~d.truth_biased).sum()),
            int((~d.flag_di & d.truth_biased).sum()), int((~d.flag_di & ~d.truth_biased).sum()))
rows = {}
for name, d in [("overall", e1)] + [("%g" % l, e1[e1.level.round(2) == l]) for l in (0.0, 0.05, 0.1, 0.2, 0.3)]:
    tp, fp, fn, tn = conf(d)
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None
    boots = []
    for _ in range(4000):
        b = d.iloc[rng.integers(0, len(d), len(d))]; a, b_, c, _t = conf(b)
        if 2 * a + b_ + c > 0: boots.append(2 * a / (2 * a + b_ + c))
    rows[name] = dict(n=len(d), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=(tp / (tp + fp)) if tp + fp else None, precision_ci=clopper(tp, tp + fp),
        recall=(tp / (tp + fn)) if tp + fn else None, recall_ci=clopper(tp, tp + fn),
        specificity=(tn / (tn + fp)) if tn + fp else None, specificity_ci=clopper(tn, tn + fp),
        accuracy=(tp + tn) / len(d), accuracy_ci=clopper(tp + tn, len(d)),
        f1=f1, f1_ci=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))] if boots else None)
err = e1[e1.flag_di != e1.truth_biased]
out["e1"] = dict(by_level=rows, errors=[dict(level=float(r.level), run=int(r.run), true_ratio=float(r.dir_true), observed_ratio=float(r.dir_observed),
                 truly_biased=bool(r.truth_biased), flagged=bool(r.flag_di)) for r in err.itertuples()],
                 max_distance_of_true_ratio_from_threshold=float((err.dir_true - 0.8).abs().max()),
                 max_distance_of_observed_ratio_from_threshold=float((err.dir_observed - 0.8).abs().max()))
# 2. E3
r = pd.read_csv(os.path.join(RES, "..", "..", "docs", "results", "e3_raw_latency.csv"))
d, p = r.direct_ms.values, r.proxy_ms.values; diff = p - d
bm, bp, bpd = [], [], []
for _ in range(4000):
    i = rng.integers(0, len(r), len(r))
    bm.append(diff[i].mean()); bp.append(np.percentile(p[i], 95) - np.percentile(d[i], 95)); bpd.append(np.percentile(diff[i], 95))
out["e3"] = dict(mean_overhead_ci=[float(x) for x in np.percentile(bm, [2.5, 97.5])],
                 p95_minus_p95_ci=[float(x) for x in np.percentile(bp, [2.5, 97.5])],
                 p95_paired_diff_ci=[float(x) for x in np.percentile(bpd, [2.5, 97.5])],
                 wilcoxon_p=float(stats.wilcoxon(diff).pvalue),
                 sequential_throughput_direct_rps=float(1000 / d.mean()), sequential_throughput_proxy_rps=float(1000 / p.mean()),
                 max_direct_ms=float(d.max()), max_proxy_ms=float(p.max()), requests_over_50ms_proxy=int((p > 50).sum()))
# 3. drift correction
from generate_synthetic import generate
from engine import drift
pool = generate(200000, bias=0.0, seed=777)
raw = bh = 0; N = 500
for _ in range(N):
    idx = rng.permutation(len(pool)); ref = pool.iloc[idx[:6000]]; cur = pool.iloc[idx[6000:8400]]
    rows_ = drift.feature_drift(ref, cur)
    raw += any(x["p_value"] < 0.05 for x in rows_); bh += any(x["drifted"] for x in rows_)
sim_raw = sim_bh = 0
for _ in range(2000):
    pv = rng.uniform(size=20); sim_raw += (pv < 0.05).any(); sim_bh += (stats.false_discovery_control(pv, method="bh") < 0.05).any()
out["drift_correction"] = dict(windows=N, features=5, reference=6000, current=2400, uncorrected_any_flag=raw / N, bh_any_flag=bh / N,
                               analytic_uncorrected_5=1 - 0.95 ** 5, analytic_uncorrected_20=1 - 0.95 ** 20,
                               simulated_20_uncorrected=sim_raw / 2000, simulated_20_bh=sim_bh / 2000)
# 4. maturity sensitivity
W = np.array([.20, .15, .20, .15, .15, .10, .05])
def level(S, w):
    ws = (S * w).sum(1); raw_ = np.clip((ws + 0.5).astype(int), 1, 5); cap = S.min(1) + 1
    return np.minimum(raw_, cap), raw_
N = 200000
U = rng.integers(1, 6, size=(N, 7)); b = rng.integers(1, 6, size=(N, 1)); C = np.clip(b + rng.integers(-1, 2, size=(N, 7)), 1, 5)
mat = {}
for name, S in (("uniform_random_profiles", U), ("correlated_profiles", C)):
    L0, raw0 = level(S, W)
    pert = []
    for _ in range(200):
        w = np.clip(W + rng.uniform(-.05, .05, 7), 0.01, None); pert.append(w / w.sum())
    ag = [(level(S[:20000], w)[0] == L0[:20000]).mean() for w in pert]
    Le = level(S, np.ones(7) / 7)[0]
    mat[name] = dict(equal_weights_same_level=float((Le == L0).mean()), perturbed_weights_mean_agreement=float(np.mean(ag)),
                     perturbed_weights_min_agreement=float(np.min(ag)), equal_weights_within_one_level=float((abs(Le - L0) <= 1).mean()),
                     cap_lowers_level=float((raw0 > L0).mean()))
out["maturity_sensitivity"] = dict(n_profiles=N, **mat)
json.dump(out, open(os.path.join(RES, "review_additions.json"), "w"), indent=1)
print(json.dumps({k: (v if k != "e1" else "see file") for k, v in out.items()}, indent=1))
