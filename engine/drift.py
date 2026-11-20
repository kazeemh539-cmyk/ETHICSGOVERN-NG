"""Drift detection (FR-08, FR-09): KS for continuous, chi-squared for categorical,
Benjamini-Hochberg correction across features, plus prediction (approval-rate) drift."""
import numpy as np
from scipy import stats

CONTINUOUS = ["age", "income", "credit_score", "loan_amount"]
CATEGORICAL = ["gender"]
ALPHA = 0.05


def feature_drift(ref, cur, alpha=ALPHA):
    rows = []
    for f in CONTINUOUS:
        s = stats.ks_2samp(ref[f].values, cur[f].values)
        rows.append({"feature": f, "test": "ks", "statistic": float(s.statistic), "p_value": float(s.pvalue)})
    for f in CATEGORICAL:
        cats = sorted(set(ref[f]) | set(cur[f]))
        table = np.array([[int((ref[f] == c).sum()) for c in cats],
                          [int((cur[f] == c).sum()) for c in cats]])
        chi2, p, _, _ = stats.chi2_contingency(table)
        rows.append({"feature": f, "test": "chi2", "statistic": float(chi2), "p_value": float(p)})
    adj = stats.false_discovery_control([r["p_value"] for r in rows], method="bh")
    for r, a in zip(rows, adj):
        r["p_adjusted"] = float(a)
        r["drifted"] = bool(a < alpha)
    return rows


def prediction_drift(ref_pred, cur_pred, alpha=ALPHA, min_shift=0.05):
    """Two-proportion chi-squared on approval rate; flagged only if significant AND shift >= min_shift."""
    a, b = np.asarray(ref_pred), np.asarray(cur_pred)
    table = np.array([[int(a.sum()), int(len(a) - a.sum())], [int(b.sum()), int(len(b) - b.sum())]])
    chi2, p, _, _ = stats.chi2_contingency(table, correction=False)
    shift = float(b.mean() - a.mean())
    return {"ref_rate": float(a.mean()), "cur_rate": float(b.mean()), "shift": shift,
            "p_value": float(p), "drifted": bool(p < alpha and abs(shift) >= min_shift)}
