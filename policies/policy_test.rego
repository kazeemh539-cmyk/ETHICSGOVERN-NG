package ethicsgovern

import data.ethicsgovern.fairness
import data.ethicsgovern.drift
import data.ethicsgovern.explainability
import data.ethicsgovern.accountability

th := {"di_min": 0.8, "eo_max": 0.1, "protected_share_max": 0.05}

test_di_ratio_flags_below_threshold {
	count(fairness.violation) == 1 with input as {"model": {"thresholds": th}, "metrics": {"di_ratio": 0.62, "eo_diff": null}}
}

test_di_ratio_passes_at_threshold {
	count(fairness.violation) == 0 with input as {"model": {"thresholds": th}, "metrics": {"di_ratio": 0.80, "eo_diff": 0.05}}
}

test_eo_diff_flags_above_tolerance {
	v := fairness.violation with input as {"model": {"thresholds": th}, "metrics": {"di_ratio": 0.95, "eo_diff": 0.21}}
	v[_].rule_id == "EO_DIFF"
}

test_drift_feature_flag {
	count(drift.violation) == 1 with input as {"drift": {"drifted_features": ["income"], "prediction": {"drifted": false}}}
}

test_no_drift_no_flag {
	count(drift.violation) == 0 with input as {"drift": {"drifted_features": [], "prediction": {"drifted": false}}}
}

test_explain_coverage_flag {
	count(explainability.violation) == 1 with input as {"explainability": {"coverage": 0.9}}
}

test_explain_full_coverage_passes {
	count(explainability.violation) == 0 with input as {"explainability": {"coverage": 1.0}}
}

test_missing_owner_flag {
	v := accountability.violation with input as {"accountability": {"owner": "", "review_overdue": false, "documentation_complete": true}}
	v[_].rule_id == "NO_OWNER"
}

test_protected_attribution_flag {
	v := fairness.violation with input as {"model": {"thresholds": th}, "metrics": {"di_ratio": 0.95, "eo_diff": null}, "explainability": {"protected_share": 0.2}}
	v[_].rule_id == "GENDER_ATTRIBUTION"
}

test_protected_attribution_ok {
	count(fairness.violation) == 0 with input as {"model": {"thresholds": th}, "metrics": {"di_ratio": 0.95, "eo_diff": null}, "explainability": {"protected_share": 0.01}}
}
