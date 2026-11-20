"""Stand-alone Model API (port 5001). Knows nothing about monitoring."""
import os, pandas as pd
from xgboost import XGBClassifier
from flask import Flask, request, jsonify

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURES = ["age", "income", "credit_score", "loan_amount", "gender_f"]
app = Flask(__name__)
_models = {}


def get_model(name):
    if name not in _models:
        _models[name] = XGBClassifier(); _models[name].load_model(os.path.join(HERE, "artifacts", name.replace("-", "_") + ".json"))
    return _models[name]


def to_frame(rows):
    df = pd.DataFrame(rows)
    if "gender_f" not in df:
        df["gender_f"] = (df["gender"] == "F").astype(int)
    return df[FEATURES]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict/<name>")
def predict(name):
    body = request.get_json(force=True)
    rows = body["instances"] if "instances" in body else [body]
    score = get_model(name).predict_proba(to_frame(rows))[:, 1]
    out = [{"score": float(s), "prediction": int(s >= 0.5)} for s in score]
    return jsonify(out if "instances" in body else out[0])


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="127.0.0.1", port=5001, threads=8)
