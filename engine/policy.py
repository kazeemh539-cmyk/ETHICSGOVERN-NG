"""Policy-as-code evaluation (FR-10). Calls the Open Policy Agent binary (`opa eval`)."""
import os, sys, json, hashlib, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_DIR = os.path.join(ROOT, "policies")


def opa_binary():
    cand = ["opa.exe"] if sys.platform.startswith("win") else ["opa_linux", "opa"]
    for c in cand:
        p = os.path.join(ROOT, "bin", c)
        if os.path.exists(p):
            return p
    return "opa"


_dirs = {}


def _materialise(policies):
    """policies: list of (name, rego_source). Cached on disk by content hash."""
    key = hashlib.sha1("".join(n + s for n, s in policies).encode()).hexdigest()[:12]
    if key not in _dirs:
        d = os.path.join(tempfile.gettempdir(), "egng_policies_" + key)
        os.makedirs(d, exist_ok=True)
        for name, src in policies:
            with open(os.path.join(d, name + ".rego"), "w", encoding="utf-8") as fh:
                fh.write(src)
        _dirs[key] = d
    return _dirs[key]


def load_default_policies():
    out = []
    for fn in sorted(os.listdir(POLICY_DIR)):
        if fn.endswith(".rego") and not fn.endswith("_test.rego"):
            with open(os.path.join(POLICY_DIR, fn), encoding="utf-8") as fh:
                out.append((fn[:-5], fh.read()))
    return out


def evaluate(opa_input, policies=None):
    """Return the list of violations raised by the policy bundle for this input."""
    d = _materialise(policies or load_default_policies())
    proc = subprocess.run([opa_binary(), "eval", "-d", d, "-I", "--format", "json", "data.ethicsgovern"],
                          input=json.dumps(opa_input), capture_output=True, text=True, timeout=30,
                          creationflags=0x08000000 if sys.platform.startswith("win") else 0)
    if proc.returncode != 0:
        raise RuntimeError("OPA error: " + proc.stderr.strip()[:500])
    result = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
    out = []
    for pkg, rules in result.items():
        for v in rules.get("violation", []):
            v = dict(v); v["package"] = pkg
            out.append(v)
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda v: (order.get(v["severity"], 3), v["rule_id"]))
