"""Synthetic (invented) consumer credit applications.

Every row is generated from random numbers. No real person is described here.

The data is built so that it behaves like a real loan book:
- income, debts and past defaults drive who repays;
- gender and age have NO direct effect on repayment, but they are correlated
  with income and job tenure, so a model can still treat groups differently
  (indirect bias). That is exactly what Balanza has to detect.
"""
from __future__ import annotations

import csv
import io

import numpy as np

# Columns the demo model is allowed to use.
FEATURES = [
    "income",
    "employment_years",
    "debt_to_income",
    "credit_utilization",
    "prior_defaults",
    "loan_amount",
    "loan_term_months",
]

# Columns a lender must NOT use to decide, but must check for bias.
PROTECTED = ["gender", "age_band"]


def age_band(age: np.ndarray) -> np.ndarray:
    """Group ages into the bands used in the fairness checks."""
    bands = np.full(age.shape, "40-59", dtype=object)
    bands[age < 25] = "18-24"
    bands[(age >= 25) & (age < 40)] = "25-39"
    bands[age >= 60] = "60+"
    return bands


def generate(n: int = 6000, seed: int = 7, drift: float = 0.0, concept: float = 0.0) -> dict:
    """Create `n` invented loan applications.

    drift:   0 = same population as when the model was built.
             Higher = applicants carry more debt (the population has changed).
    concept: 0 = repayment follows the same rules as before.
             Higher = repayment depends more on things the model cannot see.
    """
    rng = np.random.default_rng(seed)

    gender = rng.choice(np.array(["F", "M"], dtype=object), size=n)
    age = np.clip(rng.normal(41, 13, n), 18, 78).round()

    # Job tenure grows with age. Invented pattern: women have shorter tenure.
    employment_years = (age - 18) * rng.beta(2, 3, n)
    employment_years = np.where(gender == "F", employment_years * 0.85, employment_years)

    # Monthly income in euros. Invented pattern: a pay gap between genders.
    income = np.exp(rng.normal(7.75, 0.42, n)) * (1 + 0.012 * np.minimum(employment_years, 25))
    income = np.where(gender == "F", income * 0.88, income)

    debt_to_income = np.clip(rng.beta(2.2, 4.5, n) + 0.10 * drift, 0.01, 0.95)
    credit_utilization = np.clip(rng.beta(2, 3, n) + 0.12 * drift, 0.0, 1.0)
    prior_defaults = rng.choice([0, 1, 2, 3], size=n, p=[0.78, 0.14, 0.06, 0.02])
    loan_amount = np.exp(rng.normal(9.3, 0.6, n))
    loan_term_months = rng.choice([12, 24, 36, 48, 60, 72], size=n)

    # The "true" rule that decides who fails to repay.
    # Note that gender and age do not appear in it.
    signal = (
        -2.35
        - 0.90 * (np.log(income) - 7.9)
        - 0.055 * np.minimum(employment_years, 20)
        + 3.00 * (debt_to_income - 0.33)
        + 1.70 * (credit_utilization - 0.40)
        + 0.75 * prior_defaults
        + 0.35 * (np.log(loan_amount) - 9.3)
        + 0.006 * (loan_term_months - 36)
    )
    hidden = rng.normal(0.0, 1.0, n)  # things the model cannot see
    z = signal + 0.25 * drift + concept * 2.2 * hidden
    probability = 1.0 / (1.0 + np.exp(-z))
    default = (rng.random(n) < probability).astype(int)

    return {
        "applicant_id": np.array([f"A{seed:02d}-{i:05d}" for i in range(n)], dtype=object),
        "gender": gender,
        "age": age.astype(int),
        "age_band": age_band(age),
        "income": income.round(0),
        "employment_years": employment_years.round(1),
        "debt_to_income": debt_to_income.round(3),
        "credit_utilization": credit_utilization.round(3),
        "prior_defaults": prior_defaults.astype(int),
        "loan_amount": loan_amount.round(0),
        "loan_term_months": loan_term_months.astype(int),
        "default": default,
    }


def to_csv(table: dict) -> str:
    """Turn a table (dict of columns) into CSV text."""
    names = list(table.keys())
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(names)
    for row in zip(*(table[name] for name in names)):
        writer.writerow(row)
    return out.getvalue()
