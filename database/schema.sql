-- EthicsGovern-NG database schema (SQLite 3)
CREATE TABLE assessments(
  assessment_id INTEGER PRIMARY KEY AUTOINCREMENT, institution TEXT, dimension_scores TEXT,
  weighted_score REAL, level INTEGER, assessed_by TEXT, assessed_at TEXT, capped INTEGER);

CREATE TABLE decisions(
  decision_id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER NOT NULL, features TEXT NOT NULL,
  prediction INTEGER NOT NULL, score REAL, subject_pseudonym TEXT, created_at TEXT NOT NULL,
  outcome INTEGER);

CREATE TABLE drift_results(
  drift_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, feature TEXT, test TEXT,
  statistic REAL, p_value REAL, drifted INTEGER, p_adjusted REAL);

CREATE TABLE explanations(
  explanation_id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id INTEGER NOT NULL, method TEXT NOT NULL,
  attributions TEXT, base_value REAL, generated_at TEXT);

CREATE TABLE findings(
  finding_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, policy_id INTEGER, model_id INTEGER,
  rule_id TEXT, severity TEXT, status TEXT, owner TEXT, message TEXT, justification TEXT,
  raised_at TEXT, closed_at TEXT, supersedes_finding_id INTEGER, recorded_by TEXT);

CREATE TABLE models(
  model_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, owner TEXT, purpose TEXT,
  version TEXT, protected_attributes TEXT, thresholds TEXT, endpoint_url TEXT, review_date TEXT,
  artifact TEXT);

CREATE TABLE monitoring_runs(
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER NOT NULL, window_start TEXT, window_end TEXT,
  metrics TEXT, policy_version INTEGER, created_at TEXT, triggered_by TEXT);

CREATE TABLE policies(
  policy_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, rego_source TEXT NOT NULL,
  version INTEGER NOT NULL, effective_from TEXT, approved_by TEXT);

CREATE TABLE users(
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT, created_at TEXT);

CREATE INDEX ix_dec_model_time ON decisions(model_id, created_at);

CREATE INDEX ix_expl_dec ON explanations(decision_id, method);
