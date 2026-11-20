package ethicsgovern.fairness

# Disparate impact ratio below the four-fifths convention (default 0.80)
violation[{"rule_id": "DI_RATIO", "severity": "high", "message": msg}] {
	input.metrics.di_ratio != null
	input.metrics.di_ratio < input.model.thresholds.di_min
	msg := sprintf("Disparate impact ratio %v is below the minimum %v", [round(input.metrics.di_ratio * 100) / 100, input.model.thresholds.di_min])
}

# Equal opportunity difference above tolerance (default 0.10)
violation[{"rule_id": "EO_DIFF", "severity": "medium", "message": msg}] {
	input.metrics.eo_diff != null
	abs(input.metrics.eo_diff) > input.model.thresholds.eo_max
	msg := sprintf("Equal opportunity difference %v exceeds tolerance %v", [round(abs(input.metrics.eo_diff) * 100) / 100, input.model.thresholds.eo_max])
}

# F1: the protected attribute itself carries a material share of the model's explanations
violation[{"rule_id": "GENDER_ATTRIBUTION", "severity": "high", "message": msg}] {
	input.explainability.protected_share != null
	input.explainability.protected_share > input.model.thresholds.protected_share_max
	msg := sprintf("Gender accounts for %v%% of total explanation weight (limit %v%%): the model relies directly on a protected attribute", [round(input.explainability.protected_share * 1000) / 10, round(input.model.thresholds.protected_share_max * 1000) / 10])
}
