"""Train the two demonstration credit models.
loan-scorer-v1 : trained on historically biased decisions (learns the bias)
loan-scorer-v2 : trained on unbiased decisions (the remediated model)
"""
import os, sys
import pandas as pd
from xgboost import XGBClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "data"))
FEATURES = ["age", "income", "credit_score", "loan_amount", "gender_f"]


def prep(df):
    X = df[["age", "income", "credit_score", "loan_amount"]].copy()
    X["gender_f"] = (df["gender"] == "F").astype(int)
    return X[FEATURES]


def train(csv, out):
    df = pd.read_csv(csv)
    m = XGBClassifier(n_estimators=120, max_depth=4, learning_rate=0.12, subsample=0.9,
                      eval_metric="logloss", random_state=7, n_jobs=2)
    m.fit(prep(df), df["decision"])
    m.save_model(out)   # native JSON: stable across xgboost versions
    print("saved", out, "train approval rate %.3f" % df["decision"].mean())


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "model_api", "artifacts"), exist_ok=True)
    train(os.path.join(ROOT, "data", "train_biased.csv"), os.path.join(HERE, "artifacts", "loan_scorer_v1.json"))
    train(os.path.join(ROOT, "data", "train_unbiased.csv"), os.path.join(HERE, "artifacts", "loan_scorer_v2.json"))
