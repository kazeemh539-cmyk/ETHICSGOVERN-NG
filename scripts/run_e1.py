"""Experiment E1: bias detection accuracy (Appendix A protocol: 5 bias levels x 10 datasets).

Ground truth: a dataset is 'biased' if the realised expected-approval ratio
  DIR_true = mean(p_biased | F) / mean(p_biased | M)   is below 0.80.
This is computed from the withheld latent probabilities, never shown to the monitor.
Detector: the real engine. Fairness metrics on the observed decisions, evaluated by OPA
against the production policy bundle; a dataset is 'flagged' if rule DI_RATIO fires.
"""
import os, sys, json, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "data")); sys.path.insert(0, os.path.join(ROOT, "model_api"))
from generate_synthetic import generate
from engine import fairness, policy
import joblib
from train import prep, FEATURES
from xgboost import XGBClassifier

LEVELS = [0.0, 0.05, 0.10, 0.20, 0.30]
TH = {"di_min": 0.80, "eo_max": 0.10, "protected_share_max": 0.05}
rows = []
for lvl in LEVELS:
    for run in range(10):
        df = generate(n=10000, bias=lvl, seed=1000 + run)
        F, M = df.gender == "F", df.gender == "M"
        pb = np.where(F, df.p_true * (1 - lvl), df.p_true)
        dir_true = pb[F].mean() / pb[M].mean()
        fm = fairness.compute_metrics(df.decision, df.gender, df.repaid)
        viol = policy.evaluate({"model": {"thresholds": TH}, "metrics": {"di_ratio": fm["di_ratio"], "eo_diff": fm["eo_diff"]},
                                "drift": {"drifted_features": [], "prediction": {"drifted": False}},
                                "explainability": {"coverage": 1.0, "protected_share": None},
                                "accountability": {"owner": "x", "review_overdue": False, "documentation_complete": True}})
        ids = {v["rule_id"] for v in viol}
        # supplementary arm: train a model on this dataset, monitor its predictions on fresh applicants
        m = XGBClassifier(n_estimators=120, max_depth=4, learning_rate=0.12, subsample=0.9, eval_metric="logloss", random_state=7, n_jobs=2)
        m.fit(prep(df), df.decision)
        fresh = generate(n=10000, bias=0.0, seed=9000 + run)
        pred = (m.predict_proba(prep(fresh))[:, 1] >= 0.5).astype(int)
        mm = fairness.compute_metrics(pred, fresh.gender.values)
        rows.append({"level": lvl, "run": run, "dir_true": dir_true, "truth_biased": bool(dir_true < 0.80),
                     "dir_observed": fm["di_ratio"], "flag_di": "DI_RATIO" in ids, "flag_eo": "EO_DIFF" in ids,
                     "model_dir": mm["di_ratio"], "model_flag": bool(mm["di_ratio"] < 0.80)})
df = pd.DataFrame(rows)
df.to_csv(os.path.join(ROOT, "docs", "results", "e1_raw.csv"), index=False)

tp = int(((df.truth_biased) & (df.flag_di)).sum()); fp = int(((~df.truth_biased) & (df.flag_di)).sum())
fn = int(((df.truth_biased) & (~df.flag_di)).sum()); tn = int(((~df.truth_biased) & (~df.flag_di)).sum())
prec = tp / (tp + fp) if tp + fp else float("nan"); rec = tp / (tp + fn) if tp + fn else float("nan")
f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
summary = {"n_datasets": len(df), "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec, "f1": f1,
           "false_positive_rate": fp / (fp + tn) if fp + tn else None, "accuracy": (tp + tn) / len(df)}
by = df.groupby("level").agg(dir_true_mean=("dir_true", "mean"), dir_obs_mean=("dir_observed", "mean"), dir_obs_sd=("dir_observed", "std"),
                             truth_biased=("truth_biased", "sum"), flagged=("flag_di", "sum"), eo_flagged=("flag_eo", "sum"),
                             model_dir_mean=("model_dir", "mean"), model_flagged=("model_flag", "sum")).reset_index()
json.dump({"summary": summary, "by_level": by.to_dict("records")}, open(os.path.join(ROOT, "docs", "results", "e1_summary.json"), "w"), indent=1)
print(by.round(3).to_string(index=False)); print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in summary.items()}))
