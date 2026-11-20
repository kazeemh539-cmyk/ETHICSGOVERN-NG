"""Local explanations (FR-05, FR-06): SHAP (TreeExplainer) and LIME for one decision."""
import os, sys, numpy as np, pandas as pd
from xgboost import XGBClassifier
import shap
from lime.lime_tabular import LimeTabularExplainer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "model_api"))
FEATURES = ["age", "income", "credit_score", "loan_amount", "gender_f"]
_cache = {}


def _load(artifact):
    if artifact not in _cache:
        model = XGBClassifier(); model.load_model(os.path.join(ROOT, "model_api", "artifacts", artifact + ".json"))
        bg = pd.read_csv(os.path.join(ROOT, "data", "train_unbiased.csv"))
        bgX = bg[["age", "income", "credit_score", "loan_amount"]].copy()
        bgX["gender_f"] = (bg["gender"] == "F").astype(int)
        bgX = bgX[FEATURES].sample(2000, random_state=1)
        _cache[artifact] = {
            "model": model, "bg": bgX,
            "shap": shap.TreeExplainer(model),
            "lime": LimeTabularExplainer(bgX.values, feature_names=FEATURES, categorical_features=[4],
                                         class_names=["decline", "approve"], discretize_continuous=True, random_state=3),
        }
    return _cache[artifact]


def _row(features):
    r = dict(features)
    r["gender_f"] = int(r.get("gender") == "F") if "gender_f" not in r else r["gender_f"]
    return pd.DataFrame([r])[FEATURES]


def explain_shap(artifact, features):
    c = _load(artifact)
    X = _row(features)
    sv = c["shap"].shap_values(X)[0]
    base = float(np.ravel(c["shap"].expected_value)[0])
    return {"method": "shap", "base_value": base,
            "attributions": {f: float(v) for f, v in zip(FEATURES, sv)}}


def explain_lime(artifact, features):
    c = _load(artifact)
    X = _row(features)
    e = c["lime"].explain_instance(X.values[0], c["model"].predict_proba, num_features=len(FEATURES), num_samples=1500)
    attrs, rules = {}, {}
    for text, w in e.as_list():
        feat = next((f for f in sorted(FEATURES, key=len, reverse=True) if f in text), text)
        attrs[feat], rules[feat] = float(w), text
    return {"method": "lime", "base_value": float(e.intercept[1]), "attributions": attrs, "rules": rules}


def explain(artifact, features, method="shap"):
    return explain_lime(artifact, features) if method == "lime" else explain_shap(artifact, features)


def shap_batch(artifact, df):
    """Vectorised SHAP for many decisions (used when seeding / simulating)."""
    c = _load(artifact)
    X = df.copy()
    if "gender_f" not in X:
        X["gender_f"] = (X["gender"] == "F").astype(int)
    X = X[FEATURES]
    sv = c["shap"].shap_values(X)
    base = float(np.ravel(c["shap"].expected_value)[0])
    return base, [{f: float(v) for f, v in zip(FEATURES, row)} for row in sv]
