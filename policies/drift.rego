package ethicsgovern.drift

violation[{"rule_id": "DRIFT_FEATURE", "severity": "medium", "message": msg}] {
	count(input.drift.drifted_features) > 0
	msg := sprintf("Input drift detected in: %v", [concat(", ", input.drift.drifted_features)])
}

violation[{"rule_id": "DRIFT_PREDICTION", "severity": "high", "message": msg}] {
	input.drift.prediction.drifted == true
	shift := round(input.drift.prediction.shift * 1000) / 10
	msg := sprintf("Approval rate has shifted by %v percentage points against the reference window", [shift])
}
