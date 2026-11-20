import os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "data"))
from engine import fairness, drift, explain, policy
from generate_synthetic import generate


def test_fairness_known_values():
    pred = np.array([1, 1, 1, 0, 1, 0, 0, 0])
    grp = np.array(["M", "M", "M", "M", "F", "F", "F", "F"])
    m = fairness.compute_metrics(pred, grp)
    assert abs(m["approval_rate_privileged"] - 0.75) < 1e-9
    assert abs(m["approval_rate_unprivileged"] - 0.25) < 1e-9
    assert abs(m["di_ratio"] - 1 / 3) < 1e-9
    assert abs(m["dpd"] + 0.5) < 1e-9


def test_equal_opportunity():
    pred = np.array([1, 1, 0, 0, 1, 0, 0, 0])
    y = np.array([1, 1, 1, 1, 1, 1, 1, 1])
    grp = np.array(["M"] * 4 + ["F"] * 4)
    m = fairness.compute_metrics(pred, grp, y)
    assert abs(m["eo_diff"] - (0.5 - 0.25)) < 1e-9


def test_no_drift_on_same_distribution():
    a, b = generate(5000, seed=1), generate(5000, seed=2)
    assert not any(r["drifted"] for r in drift.feature_drift(a, b))


def test_drift_detected_under_income_shock():
    a, b = generate(5000, seed=1), generate(5000, seed=3, income_shock=0.35)
    flagged = {r["feature"] for r in drift.feature_drift(a, b) if r["drifted"]}
    assert "income" in flagged


def test_prediction_drift():
    ref, cur = np.r_[np.ones(500), np.zeros(500)], np.r_[np.ones(300), np.zeros(700)]
    assert drift.prediction_drift(ref, cur)["drifted"]
    assert not drift.prediction_drift(ref, ref)["drifted"]


def test_shap_additivity():
    f = {"age": 35, "income": 3_000_000, "credit_score": 700, "loan_amount": 1_500_000, "gender": "F"}
    e = explain.explain_shap("loan_scorer_v1", f)
    assert set(e["attributions"]) == set(explain.FEATURES)
    import numpy as _np
    c = explain._load("loan_scorer_v1")
    raw = float(c["model"].predict(explain._row(f), output_margin=True)[0])
    assert abs(e["base_value"] + sum(e["attributions"].values()) - raw) < 1e-3


def test_v1_uses_gender_v2_does_not():
    f = {"age": 35, "income": 3_000_000, "credit_score": 700, "loan_amount": 1_500_000, "gender": "F"}
    g1 = abs(explain.explain_shap("loan_scorer_v1", f)["attributions"]["gender_f"])
    g2 = abs(explain.explain_shap("loan_scorer_v2", f)["attributions"]["gender_f"])
    assert g1 > 5 * g2


def test_policy_roundtrip():
    inp = {"model": {"thresholds": {"di_min": 0.8, "eo_max": 0.1}}, "metrics": {"di_ratio": 0.5, "eo_diff": None},
           "drift": {"drifted_features": [], "prediction": {"drifted": False}},
           "explainability": {"coverage": 1.0},
           "accountability": {"owner": "x", "review_overdue": False, "documentation_complete": True}}
    ids = [v["rule_id"] for v in policy.evaluate(inp)]
    assert ids == ["DI_RATIO"]


def test_group_with_zero_favourable_outcomes():
    pred = np.array([1, 1, 0, 1, 0, 0, 0, 0])
    grp = np.array(["M"] * 4 + ["F"] * 4)
    m = fairness.compute_metrics(pred, grp)
    assert m["approval_rate_unprivileged"] == 0.0 and m["di_ratio"] == 0.0
    # privileged group with no approvals: ratio is undefined and reported as None, not a crash
    m2 = fairness.compute_metrics(np.array([0, 0, 0, 0, 1, 1, 0, 0]), grp)
    assert m2["di_ratio"] is None


def test_missing_protected_attribute_values_are_excluded():
    pred = np.array([1, 1, 0, 0, 1, 0, 0, 0, 1, 1])
    grp = np.array(["M", "M", "M", "M", "F", "F", "F", "F", None, None], dtype=object)
    m = fairness.compute_metrics(pred, grp)
    assert m["n_privileged"] == 4 and m["n_unprivileged"] == 4
    assert abs(m["approval_rate_privileged"] - 0.5) < 1e-9
