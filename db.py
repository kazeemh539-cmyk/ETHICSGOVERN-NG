"""SQLite persistence (stand-in for PostgreSQL). Tables follow Table 3.7, plus users."""
import os, sqlite3, json, threading

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("EGNG_DB", os.path.join(ROOT, "ethicsgovern.db"))
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS models(
  model_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, owner TEXT, purpose TEXT,
  version TEXT, protected_attributes TEXT, thresholds TEXT, endpoint_url TEXT, review_date TEXT,
  artifact TEXT);
CREATE TABLE IF NOT EXISTS decisions(
  decision_id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER NOT NULL, features TEXT NOT NULL,
  prediction INTEGER NOT NULL, score REAL, subject_pseudonym TEXT, created_at TEXT NOT NULL,
  outcome INTEGER);
CREATE INDEX IF NOT EXISTS ix_dec_model_time ON decisions(model_id, created_at);
CREATE TABLE IF NOT EXISTS policies(
  policy_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, rego_source TEXT NOT NULL,
  version INTEGER NOT NULL, effective_from TEXT, approved_by TEXT);
CREATE TABLE IF NOT EXISTS monitoring_runs(
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER NOT NULL, window_start TEXT, window_end TEXT,
  metrics TEXT, policy_version INTEGER, created_at TEXT, triggered_by TEXT);
CREATE TABLE IF NOT EXISTS explanations(
  explanation_id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id INTEGER NOT NULL, method TEXT NOT NULL,
  attributions TEXT, base_value REAL, generated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_expl_dec ON explanations(decision_id, method);
CREATE TABLE IF NOT EXISTS drift_results(
  drift_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, feature TEXT, test TEXT,
  statistic REAL, p_value REAL, drifted INTEGER, p_adjusted REAL);
CREATE TABLE IF NOT EXISTS findings(
  finding_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, policy_id INTEGER, model_id INTEGER,
  rule_id TEXT, severity TEXT, status TEXT, owner TEXT, message TEXT, justification TEXT,
  raised_at TEXT, closed_at TEXT, supersedes_finding_id INTEGER, recorded_by TEXT);
CREATE TABLE IF NOT EXISTS assessments(
  assessment_id INTEGER PRIMARY KEY AUTOINCREMENT, institution TEXT, dimension_scores TEXT,
  weighted_score REAL, level INTEGER, assessed_by TEXT, assessed_at TEXT, capped INTEGER);
"""


def conn():
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with _lock, conn() as c:
        c.executescript(SCHEMA)


def q(sql, args=(), one=False):
    with _lock, conn() as c:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    with _lock, conn() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def many(sql, rows):
    with _lock, conn() as c:
        c.executemany(sql, rows)


def j(v):
    return json.dumps(v)
