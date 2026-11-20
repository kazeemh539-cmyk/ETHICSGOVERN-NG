"""Experiment E2 (computational form): explanation quality measured on synthetic decisions.

No human raters are involved. For 500 synthetic applicants scored by each model we measure:
  faithfulness  - SHAP additivity error; LIME surrogate R^2; deletion test (does removing the feature the
                  explanation names change the score more than removing an arbitrary feature?)
  agreement     - SHAP vs LIME top-3 overlap, top-1 match, sign agreement
  stability     - rank correlation of attributions under small input perturbations (SHAP) and under a different
                  random seed (LIME)
  concision     - share of total attribution carried by the top three features
  exposure      - how often, and how strongly, the explanation exposes use of the protected attribute
  reason codes  - share of declined decisions for which three customer-facing adverse reasons can be produced
Baselines for the deletion test: random feature, and a single global-importance feature applied to every decision.
"""
import os, sys, json, time
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from lime.lime_tabular import LimeTabularExplainer
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "data")); sys.path.insert(0, os.path.join(ROOT, "model_api"))
from generate_synthetic import generate
from engine import explain
from engine.explain import FEATURES

N = 500
rng = np.random.default_rng(2025)
pool = generate(n=2000, bias=0.0, seed=31337)
app = pool.iloc[:N].reset_index(drop=True)
X = app[["age", "income", "credit_score", "loan_amount"]].copy(); X["gender_f"] = (app.gender == "F").astype(int); X = X[FEATURES]


def boot_ci(v, n=2000):
    v = np.asarray(v, float); v = v[~np.isnan(v)]
    m = np.array([rng.choice(v, len(v)).mean() for _ in range(n)])
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def rank_corr(a, b):
    r = spearmanr(a, b).correlation
    return np.nan if r is None else float(r)


def top3(vec):
    return set(np.argsort(-np.abs(vec))[:3])


rows, summary = [], {}
t0 = time.time()
for art, label in (("loan_scorer_v1", "v1"), ("loan_scorer_v2", "v2")):
    c = explain._load(art); model = c["model"]; bg = c["bg"]
    score = model.predict_proba(X)[:, 1]; pred = (score >= 0.5).astype(int)
    # ---- SHAP (batch) and additivity
    sv = c["shap"].shap_values(X); base = float(np.ravel(c["shap"].expected_value)[0])
    margin = model.predict(X, output_margin=True)
    add_err = np.abs(base + sv.sum(1) - margin)
    # ---- LIME per decision, two seeds
    lime2 = LimeTabularExplainer(bg.values, feature_names=FEATURES, categorical_features=[4], discretize_continuous=True, random_state=99)
    L1, L2, R2 = np.zeros((N, 5)), np.zeros((N, 5)), np.zeros(N)
    for i in range(N):
        for expl, out in ((c["lime"], L1), (lime2, L2)):
            e = expl.explain_instance(X.values[i], model.predict_proba, num_features=5, num_samples=1500)
            for text, w in e.as_list():
                f = next(f for f in sorted(FEATURES, key=len, reverse=True) if f in text); out[i, FEATURES.index(f)] = w
            if out is L1: R2[i] = e.score
    # ---- SHAP stability under small perturbations
    Xp = X.copy().astype(float)
    Xp["income"] *= rng.choice([0.99, 1.01], N); Xp["loan_amount"] *= rng.choice([0.99, 1.01], N)
    Xp["credit_score"] += rng.choice([-3, 3], N); Xp["age"] += rng.choice([-1, 1], N)
    svp = c["shap"].shap_values(Xp)
    flip = (model.predict_proba(Xp)[:, 1] >= 0.5).astype(int) != pred
    # ---- deletion test via marginalisation over 50 background rows
    B = bg.sample(50, random_state=5).values
    glob = np.abs(sv).mean(0).argmax()
    d_shap, d_lime, d_rand, d_glob = [], [], [], []
    for i in range(N):
        deltas = np.zeros(5)
        for j in range(5):
            Z = np.tile(X.values[i], (50, 1)).astype(float); Z[:, j] = B[:, j]
            deltas[j] = abs(score[i] - model.predict_proba(pd.DataFrame(Z, columns=FEATURES))[:, 1].mean())
        d_shap.append(deltas[np.argmax(np.abs(sv[i]))]); d_lime.append(deltas[np.argmax(np.abs(L1[i]))])
        d_rand.append(deltas.mean()); d_glob.append(deltas[glob])
    # ---- per-decision metrics
    for i in range(N):
        t_s, t_l = top3(sv[i]), top3(L1[i])
        rows.append({"model": label, "applicant_id": i, **{f: X.iloc[i][f] for f in FEATURES}, "score": score[i], "prediction": int(pred[i]),
                     **{"shap_" + f: sv[i, k] for k, f in enumerate(FEATURES)}, **{"lime_" + f: L1[i, k] for k, f in enumerate(FEATURES)},
                     "shap_additivity_error": add_err[i], "lime_surrogate_r2": R2[i],
                     "top3_overlap": len(t_s & t_l) / 3, "top1_match": int(np.argmax(np.abs(sv[i])) == np.argmax(np.abs(L1[i]))),
                     "sign_agreement": float(np.mean(np.sign(sv[i]) == np.sign(L1[i]))), "rank_corr_shap_lime": rank_corr(sv[i], L1[i]),
                     "shap_stability_rank_corr": rank_corr(sv[i], svp[i]), "shap_top3_stable": len(t_s & top3(svp[i])) / 3,
                     "lime_stability_rank_corr": rank_corr(L1[i], L2[i]), "lime_top3_stable": len(t_l & top3(L2[i])) / 3,
                     "decision_flipped_by_perturbation": int(flip[i]),
                     "shap_top3_share": np.sort(np.abs(sv[i]))[::-1][:3].sum() / max(np.abs(sv[i]).sum(), 1e-12),
                     "gender_in_shap_top3": int(4 in t_s), "gender_in_lime_top3": int(4 in t_l),
                     "gender_share_shap": abs(sv[i, 4]) / max(np.abs(sv[i]).sum(), 1e-12),
                     "n_adverse_factors_shap": int((sv[i] < 0).sum()),
                     "delta_remove_top_shap": d_shap[i], "delta_remove_top_lime": d_lime[i], "delta_remove_random": d_rand[i], "delta_remove_global_top": d_glob[i]})
    df = pd.DataFrame([r for r in rows if r["model"] == label]); dec = df[df.prediction == 0]
    m = lambda col, d=df: boot_ci(d[col])
    summary[label] = {
        "n": N, "approval_rate": float(pred.mean()), "n_declined": int(len(dec)),
        "shap_additivity_error_max": float(add_err.max()), "lime_surrogate_r2": m("lime_surrogate_r2"),
        "top3_overlap": m("top3_overlap"), "top1_match": m("top1_match"), "sign_agreement": m("sign_agreement"), "rank_corr_shap_lime": m("rank_corr_shap_lime"),
        "shap_stability_rank_corr": m("shap_stability_rank_corr"), "shap_top3_stable": m("shap_top3_stable"),
        "lime_stability_rank_corr": m("lime_stability_rank_corr"), "lime_top3_stable": m("lime_top3_stable"),
        "decision_flip_rate_under_perturbation": float(flip.mean()),
        "shap_top3_share": m("shap_top3_share"),
        "gender_in_shap_top3_rate": float(df.gender_in_shap_top3.mean()), "gender_in_lime_top3_rate": float(df.gender_in_lime_top3.mean()), "gender_share_shap": m("gender_share_shap"),
        "declined_with_3_adverse_factors": float((dec.n_adverse_factors_shap >= 3).mean()) if len(dec) else None,
        "declined_with_at_least_1_adverse_factor": float((dec.n_adverse_factors_shap >= 1).mean()) if len(dec) else None,
        "deletion": {k: m("delta_remove_" + k) for k in ("top_shap", "top_lime", "random", "global_top")},
        "global_top_feature": FEATURES[int(glob)],
        "deletion_shap_beats_random_rate": float((df.delta_remove_top_shap > df.delta_remove_random).mean()),
        "deletion_shap_beats_global_rate": float((df.delta_remove_top_shap >= df.delta_remove_global_top).mean()),
    }
    print(label, "done", round(time.time() - t0), "s", flush=True)

out = pd.DataFrame(rows)
out.to_csv(os.path.join(ROOT, "docs", "results", "e2_explanations.csv"), index=False)
app.assign(**{}).to_csv(os.path.join(ROOT, "docs", "results", "e2_applicants.csv"), index=False)
# worked example: a declined woman on v1 whose explanation exposes gender
v1 = out[(out.model == "v1") & (out.prediction == 0) & (out.gender_f == 1)].sort_values("shap_gender_f").iloc[len(out[(out.model == "v1")]) // 20]
summary["worked_example"] = {k: (float(v) if isinstance(v, (np.floating, float)) else (int(v) if isinstance(v, (np.integer,)) else v)) for k, v in v1.items()}
# the same applicant under v2
v2 = out[(out.model == "v2") & (out.applicant_id == v1.applicant_id)].iloc[0]
summary["worked_example_v2"] = {k: (float(v) if isinstance(v, (np.floating, float)) else (int(v) if isinstance(v, (np.integer,)) else v)) for k, v in v2.items()}
json.dump(summary, open(os.path.join(ROOT, "docs", "results", "e2_summary.json"), "w"), indent=1)
print(json.dumps({k: summary[k] for k in ("v1", "v2")}, indent=1, default=str)[:6000])
