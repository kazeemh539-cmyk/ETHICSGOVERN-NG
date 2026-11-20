> **Update.** This note was written before E2 and E4 were redesigned. No human participants took part, so E2 is now a computed explanation-quality study and E4 a scripted task study with Keystroke-Level Model times (`scripts/run_e2.py`, `scripts/run_e4.js`). Chapters 5 and 6 of `EthicsGovern-NG_Project_v2.docx` are rewritten accordingly; read `CHANGE_LOG` delivered with it. Numbers below that conflict with Chapter 5 are superseded by Chapter 5 (for example the clean-model false-alarm check is now reproducible: `scripts/run_supplementary.py`, equal-opportunity SD 0.017).

# Aligning the report with the prototype

Read this before you edit Chapters 4 and 5. A report that describes a system different from the one you demonstrate is the quickest way to lose marks. Everything below is either a place where the build differs from the draft, a number that is now real, or something only you can supply.

## 1. What is real now, and what still needs people

| Item | Status |
|---|---|
| Working prototype (fairness, SHAP, LIME, drift, OPA policy, findings, reports, maturity, taxonomy) | Built and running. 30 automated tests pass in a clean install |
| **E1** bias detection (Table 5.2) | **Run for real**: 50 datasets, results in `docs/results/` |
| **E3** latency (Table 5.4) | **Run for real on a 2-core Linux VM**. **Re-run on your laptop** (`python scripts\run_e3.py` with the app running) and quote *those* figures, with your machine's specification |
| Table 5.1 outcomes | All 12 cases implemented and passing (`tests/test_table_5_1.py`, test names carry the TC ids) |
| Figures 4.1 to 4.4, Appendix H | Real screenshots in `docs/screenshots/`. Numbers on your laptop may differ slightly from mine; if you retake them, use the same steps as `docs/DEMO_SCRIPT.md` |
| **E2** (explainability rating, five compliance officers) and **E4** (usability and SUS, five risk managers) | **Cannot be produced by software.** They need real participants, ethical clearance (Appendix I) and your own data. Do not fill Tables 5.3 and 5.5 with invented or "expected" values |
| Figures 5.1 and 5.2 | Not drawn yet. The data is in `docs/results/e1_raw.csv` and `e3_latency.json`; I can generate them if you ask |

## 2. Where the build differs from Chapter 4: disclose these

Add a short subsection to 4.1, "Implementation scope of the evaluated prototype", and say the architecture in Chapter 3 is the target design while the evaluated build used lighter equivalents. Examiners accept this when it is stated; they do not when it is discovered.

| Report says | Build does | Why (one line for the report) |
|---|---|---|
| PostgreSQL 16 in Docker, JSONB | SQLite; JSON stored as text | Runs on one Windows laptop with no installation. Same eight entities (Table 3.7) |
| Celery workers and Redis | One background thread with an in-process queue | Same asynchronous pattern; explanation stays outside the request path. Behaviour of TC-12 (HTTP 202 pending) is identical |
| Alibi Detect for drift | SciPy `ks_2samp`, `chi2_contingency`, `false_discovery_control` | The tests named in 3.4 and Table 4.2 are the same ones; only the wrapper library differs |
| OPA container on port 8181 (REST API) | OPA binary v0.65.0 invoked per monitoring run with `opa eval` | Same Rego, same engine, no sidecar to run on a laptop |
| Docker Compose, "five containers" | `run.bat` starts two processes (dashboard/API and Model API) | One-command start retained as the requirement |
| Flask blueprints, `engine/explainers.py`, `engine/reporting.py` | One `app.py`; `engine/explain.py`; reporting inside `app.py` | Compact code base. Update the tree in 4.2.1 to match the folder you submit |
| Postman collection | Not produced | Table 4.3 is covered by `tests/test_api.py` and the named TC tests. Export a collection yourself if the template requires it |
| Subgroup performance (Table 4.2, risk R3) | **Not implemented** | Say so, and mark R3 as "not tested live in the prototype". The dashboard marks it that way |

### Additions beyond Table 3.7 and Table 4.3 (update the ER diagram and the table)
* **findings**: `supersedes_finding_id`, `rule_id`, `model_id`, `message`, `justification`, `recorded_by`. This is what makes "append-only" real: closing a finding inserts a new row pointing at the old one. Update Figure 3.3 and Table 3.7 accordingly.
* **decisions**: `outcome` (observed repayment, which in a real bank arrives weeks later; needed for equal opportunity). Also `models.artifact`, `monitoring_runs.triggered_by`, `drift_results.p_adjusted`, `assessments.capped`, and a `users` table.
* **Extra endpoints**: `POST /auth/login`, `GET/POST /users` (FR-15 and the use-case diagram, missing from Table 4.3), `GET /decisions`, `GET /monitoring/runs`, `GET /policies`, `GET /assessments` and `/assessments/framework`, `GET /taxonomy`, `explain?method=shap|lime`, and demo-only `POST /demo/simulate`, `/demo/apply`, `/demo/reset`. State that the `/demo/*` endpoints exist only for presentation.
* **Decisions the report left open, now fixed in code** (put them in 4.2): disparate impact minimum 0.80; equal opportunity tolerance 0.10; gender may carry at most 5% of total explanation weight (rule `GENDER_ATTRIBUTION`, covers risk F1); prediction drift flagged at a shift of 5 percentage points or more that is also significant; explanations count towards coverage after a 60-second grace period; fairness is not computed with fewer than 30 applicants in a group (TC-04); maturity level is the weighted mean rounded half-up, then capped at the lowest dimension plus one (TC-11).

## 3. Where the numbers force a change in Chapter 5 or Appendix A

1. **Appendix A's generator approves almost nobody.** As printed (intercept −3.4) the mean approval probability is 1.6%, too few approvals to train or test anything. The build uses an intercept of **+1.0** (about 50% approval), all other coefficients unchanged. Edit the code in Appendix A and add one sentence saying the intercept was calibrated for a realistic approval rate. The generator also gained a `repaid` column (drawn from the unbiased probability) used as ground truth for equal opportunity, and two scenario switches for the demonstration.
2. **The 20% injection level sits exactly on the threshold.** Scaling female approval probability by 0.80 gives a true ratio of 0.80, the pass mark itself. Results at that level are a coin toss by construction (3 of 5 truly-biased datasets caught, 2 false alarms, 2 misses). Report it as the *boundary case*, not as a failure. Outside it, detection was perfect: 10 of 10 at 30%, and no false alarms in the 30 datasets at 0, 5 and 10 per cent.
3. **The draft predicts degradation at 5%.** What the data shows is different and better to explain: at 5% injection the *true* ratio is about 0.95, which is above the 0.80 line, so there is nothing to detect under the four-fifths rule. Sampling noise (standard deviation of the observed ratio about 0.013 to 0.023 at 10,000 rows) only becomes a problem within roughly 0.04 of the threshold. That is your sensitivity floor and the basis for a minimum-window recommendation. Rewrite the expectation paragraph under Table 5.2 accordingly.
4. **Thresholds amplify bias** (new finding worth a paragraph in Chapter 6): in the supplementary table, 10% bias in the training data produced a model whose decisions had a ratio of about 0.80, and 20% produced about 0.54. A hard 0.5 approval cutoff magnifies a small shift in probability. This supports the argument for monitoring decisions, not just training data.
5. **Clean-model false-alarm rate:** 0 of 200 simulated monitoring windows of the unbiased model (2,400 decisions each) raised a fairness violation (DIR minimum 0.91; equal-opportunity difference standard deviation 0.028). Quote it as a specificity result and state the window size.
6. E1 definition to put in 5.2.1: a dataset is "truly biased" if the ratio of expected approval rates (from the withheld latent probabilities) is below 0.80; it is "flagged" if the dashboard's `DI_RATIO` rule fires on the observed decisions. The equal-opportunity rule fired in 9 of 10 datasets at 20% and 10 of 10 at 30%, and in none below.

## 4. Inconsistencies inside the current draft (fix in the document)

* **28 risks, not 24.** Table 3.4 lists 28 identifiers (F1–F5, T1–T4, P1–P5, R1–R5, A1–A4, S1–S5). 3.4.1 and Appendix F say "twenty-four". The prototype uses 28. Change the text (or cut four risks, but then the table changes).
* **"Five services/containers"** (3.3, 2.3, 4.1, 5.3, 6.1): Table 4.1 itself lists api, worker, model-api, opa, db and redis. Pick one count and use it everywhere.
* **"Three actors"** in 3.4.4 versus four human roles plus the client application in Figure 3.4 and in the build.
* **Table 4.3 has no users endpoint** although FR-15 and Figure 3.4 include "Manage users and roles".
* **Appendix F** asks for description, likelihood, impact, control owner and evidence for each risk. The build holds only domain, name, anchor and testability. That content is yours to write (and is the more academically valuable part).
* Version numbers in 3.x/4.1 must match the environment actually used. The prototype's `requirements.txt` uses minimum versions; if the examiner reproduces the build, pin the versions installed on *your* laptop (`.venv\Scripts\pip freeze`).

## 5. Being able to defend it

You will be asked about code you did not write line by line. Prepare by running the demo yourself several times and understanding these five ideas well enough to explain them without notes:

1. **Disparate impact ratio**: approval rate of women divided by approval rate of men. Below 0.80 triggers the rule.
2. **SHAP** gives each input's push on one decision, adding up exactly to the model's output (test TC-07). **LIME** is an independent approximation; agreement between them builds trust.
3. **Drift**: compare today's inputs to history feature by feature (KS test), correct for testing several features at once (Benjamini–Hochberg), and compare the approval rate separately.
4. **Policy as code**: the thresholds live in `.rego` files, not in the application. Open `policies/fairness.rego` during the viva and read the DI rule aloud.
5. **Append-only findings**: closing adds a record; nothing is overwritten.

Likely questions: *Why synthetic data?* (NDPA: using real customer data needs a DPIA and a lawful basis; synthetic data lets bias be injected at a known level, which is what makes E1 measurable.) *Why is gender a model input at all?* (To have a model with a known defect; v2 shows the remediated case.) *Does 3.5 ms generalise?* (No: one machine, no network, no bank-scale load; it shows the proxy design is not the bottleneck.) *Why no E2 and E4 results?* (State the plan, the ethical clearance status, and the timeline.) *How do you know the explanations are right?* (SHAP additivity test; cross-check with LIME; model v2 shows gender attribution near zero.)

## 6. Responsible use of AI assistance

This prototype and the report draft were produced with AI assistance. **Check Miva Open University's current policy on AI assistance in project work and disclose it in the way the policy requires** (usually an acknowledgement or declaration page). Be ready to explain every part in your own words; the examiners are assessing your understanding of the work, and your name is on it.
