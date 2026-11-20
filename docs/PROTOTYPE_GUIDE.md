# EthicsGovern-NG prototype

A working prototype of the governance dashboard described in the project report
*EthicsGovern-NG: An Explainable AI Governance Framework and Policy Enforcement Dashboard for Nigerian Banks*.
It monitors two demonstration loan-approval models for **fairness**, **explainability**, **drift** and **policy compliance**,
and records findings in an audit-ready register. All data is synthetic.

## Start it (Windows)

1. Install **Python 3.12** from https://www.python.org/downloads/windows/ (tick **Add python.exe to PATH**). Python 3.10 and 3.11 also work.
2. Unzip this folder somewhere simple, for example `C:\EthicsGovern-NG`.
3. Double-click **`run.bat`**.
   - The first run needs internet. It installs the components (3 to 8 minutes) and downloads the policy engine (about 90 MB), then prepares the demo data.
   - Later runs start in about 15 seconds and work offline.
4. Your browser opens at **http://127.0.0.1:8000**. Sign in as `riskofficer` / `Demo@2025`.

Stop it with **Ctrl+C** in the black window (or just close the window).

| Username | Role | What it can do |
|---|---|---|
| `riskofficer` | Risk Officer (2nd line) | Run monitoring, close findings, record maturity assessments, inject scenarios |
| `owner` | Model Owner (1st line) | Register models, inject scenarios, view everything |
| `auditor` | Internal Auditor (3rd line) | Read-only, export reports |
| `admin` | Administrator | Upload policies, manage users, reset demo data |

Password for all: `Demo@2025`. Demo accounts only: change them before using this anywhere real.

## Before the presentation

* **Start the app on the day, shortly before you present.** Monitoring looks at the last 24 hours of decisions, and the demo history is generated relative to "now". If it has aged out, `run.bat` detects this and regenerates it automatically. You can also do it any time from *Administration, Reset demo data* (admin), or by running `run.bat reset`.
* Do a full rehearsal on the laptop you will present from, on the same network setup (the first-run download needs internet, the demo itself does not).
* Have `docs\screenshots\` open as a fallback in case anything misbehaves.

## What is in the folder

| Path | What it is |
|---|---|
| `run.bat`, `launcher.py` | One-command start |
| `app.py`, `db.py` | API (Flask), role-based access, database |
| `engine/` | Fairness metrics, drift tests, SHAP and LIME, policy engine wrapper |
| `policies/` | The Rego policy bundle (`*.rego`) and its unit tests (`policy_test.rego`): Appendix B |
| `model_api/` | The separate Model API and the two trained models |
| `data/generate_synthetic.py` | Synthetic Nigerian loan data with controlled bias: Appendix A |
| `frontend/` | The dashboard (React). `dist/` is pre-built, so Node.js is **not** needed |
| `tests/`, `run_tests.bat` | 30 automated tests, including the 12 cases of Table 5.1 |
| `scripts/run_e1.py`, `run_e3.py` | Experiments E1 (bias detection) and E3 (latency) |
| `docs/` | Demo script, slide outline, Chapter 4 and 5 alignment notes, results, screenshots |

## Troubleshooting

* *"Python was not found"*: install Python as in step 1 and tick the PATH box, then run `run.bat` again.
* *Download of the policy engine fails* (common on bank or university networks): open the link the program prints in your browser and save the file as `bin\opa.exe`, then run again.
* *"Port 8000 is already in use"*: another copy is running. Close it, or restart the laptop.
* *Antivirus or firewall prompt*: allow Python on private networks. Nothing leaves your machine; the app listens on 127.0.0.1 only.
* *Anything else*: delete the `.venv` folder and `ethicsgovern.db`, then run `run.bat` again.

## Limits (say these before anyone asks)

Synthetic data only. SQLite instead of PostgreSQL, an in-process queue instead of Celery and Redis, SciPy tests instead of Alibi Detect,
and `run.bat` instead of Docker Compose, so that it runs on one Windows laptop with no technical setup. Not hardened for production (no HTTPS, demo passwords).
