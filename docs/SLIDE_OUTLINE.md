# Slide outline (about 12 slides, 15 to 20 minutes with the live demo)

1. **Title.** EthicsGovern-NG: an explainable AI governance framework and policy enforcement dashboard for Nigerian banks. Name, programme, supervisor.
2. **The problem.** Banks use AI for credit decisions; failures are silent (bias, drift, no reason given). Nigerian expectations: NDPA 2023, GAID 2025, CBN consumer protection and cybersecurity frameworks.
3. **Gap and questions.** What exists is generic or foreign; nothing ties technical monitoring to Nigerian instruments. Restate your research questions and objectives from Chapter 1.
4. **Approach.** Design Science Research: artefacts are a risk taxonomy (28 risks), a maturity model (5 levels, 7 dimensions), and a working dashboard.
5. **Architecture.** Use Figure 3.2. One sentence per box: client, monitoring proxy, model API, policy engine, database, explanation worker. Mention the prototype's lighter equivalents.
6. **Policy as code.** Show the five-line Rego rule (DI_RATIO) next to the written policy. "One threshold, one place."
7. **Live demo** (see `DEMO_SCRIPT.md`). Fairness, explanation, drift, findings.
8. **Screenshot backup** (Figures 4.1 to 4.4) hidden after slide 7, ready if the demo fails.
9. **Evaluation design.** Four experiments: E1 bias detection, E2 explanation quality, E3 latency, E4 usability. Say plainly which are complete.
10. **Results so far.** E1 table and E3 table from Chapter 5 of the project document (or `docs/results/`); 30 tests passing. One observation worth a slide of its own: a hard approval cutoff amplified a 10% bias in the data into a 0.80 ratio in the model's decisions.
11. **Limitations and ethics.** Synthetic data; single machine; SQLite and in-process queue; E2 and E4 need participants and ethical clearance; not production-hardened. Say it first.
12. **Contribution and next steps.** What a Nigerian bank could do with this; pilot with real (de-identified) data under a DPIA; more models; integrate with the bank's model inventory.
13. **Questions.** Keep Figure 3.2 visible.
