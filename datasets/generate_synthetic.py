"""Synthetic Nigerian loan-application generator with controlled, known bias.

The intercept of the latent score is +1.0, which gives an approval rate near
50 per cent (an intercept of -3.4 approves only about 1.6 per cent of applicants).

Columns: age, income (NGN), credit_score, loan_amount (NGN), gender,
decision (historical outcome, carries the injected bias),
repaid (would the applicant actually repay - drawn from the unbiased
probability, used as ground truth for equal-opportunity checks),
p_true (unbiased probability, withheld from model and monitoring engine).
"""
import numpy as np
import pandas as pd

INTERCEPT = 1.0


def generate(n=10000, bias=0.0, seed=42, income_shock=0.0, new_to_bank=0.0):
    """income_shock: fractional fall in real income (naira shock scenario).
    new_to_bank: share of applicants with thin credit files (low, narrow scores)."""
    rng = np.random.default_rng(seed)
    gender = rng.choice(["M", "F"], size=n, p=[0.55, 0.45])
    age = rng.integers(21, 65, size=n)
    income = np.exp(rng.normal(np.log(3_200_000 * (1 - income_shock)), 0.65, size=n))
    credit_score = np.clip(rng.normal(640, 90, size=n), 300, 850)
    if new_to_bank > 0:
        thin = rng.random(n) < new_to_bank
        credit_score = np.where(thin, np.clip(rng.normal(560, 40, size=n), 300, 850), credit_score)
        age = np.where(thin, rng.integers(21, 32, size=n), age)
    credit_score = credit_score.astype(int)
    loan_amount = np.clip(income * rng.uniform(0.20, 1.40, size=n), 50_000, 20_000_000)
    dti = loan_amount / income

    z = (INTERCEPT
         + 0.0060 * (credit_score - 640)
         + 0.55 * np.log(income / 3_200_000)
         - 1.30 * dti
         + 0.012 * (age - 40))
    p_true = 1 / (1 + np.exp(-z))

    p_biased = np.where(gender == "F", p_true * (1 - bias), p_true)
    decision = rng.binomial(1, np.clip(p_biased, 0, 1))
    repaid = rng.binomial(1, np.clip(p_true, 0, 1))

    return pd.DataFrame({
        "age": age, "income": income.round(2), "credit_score": credit_score,
        "loan_amount": loan_amount.round(2), "gender": gender,
        "decision": decision, "repaid": repaid, "p_true": p_true.round(4),
    })


if __name__ == "__main__":
    import sys, os
    out = sys.argv[1] if len(sys.argv) > 1 else "data"
    os.makedirs(out, exist_ok=True)
    generate(n=20000, bias=0.0, seed=1).to_csv(f"{out}/train_unbiased.csv", index=False)
    generate(n=20000, bias=0.25, seed=2).to_csv(f"{out}/train_biased.csv", index=False)
    print("wrote training sets to", out)
