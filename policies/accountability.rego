package ethicsgovern.accountability

violation[{"rule_id": "NO_OWNER", "severity": "high", "message": "Model has no named owner"}] {
	input.accountability.owner == ""
}

violation[{"rule_id": "REVIEW_OVERDUE", "severity": "medium", "message": "Scheduled model review date has passed"}] {
	input.accountability.review_overdue == true
}

violation[{"rule_id": "DOC_INCOMPLETE", "severity": "low", "message": "Model documentation (purpose, version, protected attributes) is incomplete"}] {
	input.accountability.documentation_complete == false
}
