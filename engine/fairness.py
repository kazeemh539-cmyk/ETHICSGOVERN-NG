"""Group fairness metrics (FR-04). Unprivileged group F, privileged group M."""
import numpy as np

UNPRIV, PRIV = "F", "M"


def _rate(x):
    x = np.asarray(x)
    return float(x.mean()) if len(x) else float("nan")


def compute_metrics(pred, group, y_true=None):
    """pred: 0/1 decisions; group: array of 'M'/'F'; y_true: optional 0/1 'would repay'."""
    pred = np.asarray(pred).astype(int)
    group = np.asarray(group)
    u, p = group == UNPRIV, group == PRIV
    r_u, r_p = _rate(pred[u]), _rate(pred[p])
    out = {
        "n": int(len(pred)),
        "n_unprivileged": int(u.sum()), "n_privileged": int(p.sum()),
        "approval_rate_overall": _rate(pred),
        "approval_rate_unprivileged": r_u, "approval_rate_privileged": r_p,
        "dpd": r_u - r_p,                                  # demographic parity difference
        "di_ratio": (r_u / r_p) if r_p and r_p > 0 else float("nan"),  # disparate impact ratio
        "eo_diff": None, "tpr_unprivileged": None, "tpr_privileged": None,
    }
    if y_true is not None:
        y = np.asarray(y_true).astype(int)
        qu, qp = u & (y == 1), p & (y == 1)
        if qu.sum() and qp.sum():
            tu, tp = _rate(pred[qu]), _rate(pred[qp])
            out.update({"tpr_unprivileged": tu, "tpr_privileged": tp, "eo_diff": tp - tu})
    return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in out.items()}
