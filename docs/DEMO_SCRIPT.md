# Demo script: 10 minutes

Open the app first, signed out, with `docs\screenshots\` ready in another window as a fallback.
Press **Reset demo data** (Administration, as admin) if it is more than a few hours since the app started.

## 0:00 – 1:00  The problem (no screen)
"A Nigerian bank's credit model can pass its validation and still treat women and men differently, drift when the naira moves, and give a customer no reason for a decline. The CBN, the NDPA and GAID expect the bank to know, and to prove it knew. EthicsGovern-NG is the tool that checks, explains and records."

## 1:00 – 3:30  Fairness overview (sign in as **riskofficer**)
1. The model selector shows `loan-scorer-v1`. Click **Run monitoring**. Takes under a second.
2. Red banner: three policy violations. Point at the **disparate impact ratio** (about 0.45; the four-fifths rule says at least 0.80) and the approval-rate chart: women roughly 22%, men roughly 52%.
3. Point at **Gender share of explanations: 17%**. "Gender is not a side effect here; the model is using it directly."
4. Switch the selector to `loan-scorer-v2`, click **Run monitoring**: green banner. "Same checks, remediated model, no violations."
   *Line to use:* "The rules are not hard-coded in the interface. They are policy files (Rego) evaluated by the Open Policy Agent. Change the file, change the rule."

## 3:30 – 5:30  Explain one decision
1. **Decision explorer**, model `loan-scorer-v1`. Filter to **Declined**, click a woman's application.
2. Read the **customer-facing reason codes**, then the red box: gender moved this decision.
3. Show **SHAP** and **LIME** side by side. "Two independent methods; when they agree we can trust the explanation."
4. Under *Submit a live application*, press **Score application** (the defaults are a 34-year-old woman). It is scored, logged and explained within a second. Change gender to Male, score again and compare the outcome.

## 5:30 – 7:00  Drift (model v2)
1. Fairness overview, `loan-scorer-v2`. Choose **Naira shock: real incomes fall 35%**, click **Inject scenario** (about 3 seconds), then **Run monitoring**.
2. New violations. Open **Drift monitor**: income and loan amount flagged as drifted (the others stable), and the approval rate has fallen by several points.
   *Line to use:* "Nobody changed the model. The economy changed under it. This is the early warning the CBN's risk expectations ask for."

## 7:00 – 8:30  Accountability trail
1. **Findings register**, `loan-scorer-v1`. Each violation became a finding, owned by the model owner.
2. Click **Close…** on one, try to submit with no reason: refused. Enter a justification, close it.
3. Click **History**: two records, nothing overwritten. "Append-only. An auditor can see who closed what, when, and why."
4. Sign out, sign in as **auditor**: the Close buttons are gone. Read-only, plus **Export PDF** on the overview.

## 8:30 – 9:30  Beyond the numbers
1. **Risk taxonomy**: 28 risks in six domains; the dashboard tests 6 live and says plainly that the rest are organisational. Violations show in red.
2. **Maturity assessment**: set one dimension to 1 and the rest to 5: the level is capped. "A bank with brilliant monitoring and no accountability cannot call itself mature."

## 9:30 – 10:00  Close
"Results from the controlled tests: bias detected in 10 of 10 datasets at 30% injection, no false alarms across 30 clean or mildly biased datasets; about 4 ms added latency at the 95th percentile against a 50 ms target; 28 automated tests passing."
(Re-check these numbers against Chapter 5 of the project document and `docs\results\` and re-run E3 on your laptop.)

## If something breaks
* Page blank or login fails: Ctrl+C, run `run.bat reset`, wait 20 seconds, refresh.
* "Only N decisions in the last day": Administration, Reset demo data.
* Anything else: switch to the screenshots in `docs\screenshots\` and narrate. Say "recorded earlier today from the same build".
