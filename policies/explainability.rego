package ethicsgovern.explainability

# Every decision must have an explanation on file (coverage must be 100%)
violation[{"rule_id": "EXPLAIN_REQUIRED", "severity": "high", "message": msg}] {
	input.explainability.coverage < 1.0
	msg := sprintf("Explanation coverage is %v%%; every decision must be explainable", [round(input.explainability.coverage * 1000) / 10])
}
