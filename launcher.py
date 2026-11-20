"""One-command start: prepares data, models and OPA on first run, then starts both services."""
import os, sys, time, atexit, subprocess, urllib.request, socket, webbrowser, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
OPA_VERSION = "v0.65.0"
OPA_URL = f"https://github.com/open-policy-agent/opa/releases/download/{OPA_VERSION}/opa_windows_amd64.exe"


def say(msg):
    print("[EthicsGovern-NG] " + msg, flush=True)


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def ensure_opa():
    if not sys.platform.startswith("win"):
        return
    target = os.path.join(ROOT, "bin", "opa.exe")
    if os.path.exists(target) and os.path.getsize(target) > 20_000_000:
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    say("Downloading the Open Policy Agent engine (one time, about 90 MB)...")
    try:
        with urllib.request.urlopen(OPA_URL, timeout=60) as r, open(target + ".part", "wb") as out:
            shutil.copyfileobj(r, out)
        os.replace(target + ".part", target)
    except Exception as e:
        say("Could not download OPA automatically: %s" % e)
        say("Download this file in your browser and save it as  bin\\opa.exe  inside this folder:")
        say("   " + OPA_URL)
        sys.exit(1)


def ensure_models():
    need = [os.path.join("data", "train_biased.csv"), os.path.join("data", "train_unbiased.csv"),
            os.path.join("model_api", "artifacts", "loan_scorer_v1.json"), os.path.join("model_api", "artifacts", "loan_scorer_v2.json")]
    if all(os.path.exists(p) for p in need):
        return
    say("Preparing synthetic data and training the two demonstration models...")
    subprocess.check_call([sys.executable, os.path.join("data", "generate_synthetic.py"), "data"])
    subprocess.check_call([sys.executable, os.path.join("model_api", "train.py")])


def main():
    reset = "--reset" in sys.argv
    for port, name in ((5001, "Model API"), (8000, "dashboard")):
        if not port_free(port):
            say("Port %d (%s) is already in use. Close any other copy of this program and try again." % (port, name))
            sys.exit(1)
    ensure_opa()
    ensure_models()
    say("Starting the Model API...")
    flags = 0x08000000 if sys.platform.startswith("win") else 0
    model = subprocess.Popen([sys.executable, os.path.join("model_api", "serve.py")], creationflags=flags)
    atexit.register(lambda: model.terminate())
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:5001/health", timeout=1); break
        except Exception:
            time.sleep(0.5)
    else:
        say("The Model API did not start."); sys.exit(1)

    import app as A
    A.db.init()
    if reset:
        say("Resetting demo data..."); A.reset_demo()
    elif not A.db.q("SELECT 1 FROM users LIMIT 1", one=True):
        say("First run: generating the demo history (a few seconds)..."); A.seed()
    elif A.is_stale():
        say("The 24-hour demo window has aged out, so the demo data is being refreshed..."); A.reset_demo()
    from waitress import serve
    say("")
    say("Ready.  Open  http://127.0.0.1:8000  in your browser.")
    say("Sign in as  riskofficer / Demo@2025  (other roles: admin, owner, auditor)")
    say("Press Ctrl+C in this window to stop.")
    try:
        webbrowser.open("http://127.0.0.1:8000")
    except Exception:
        pass
    serve(A.app, host="127.0.0.1", port=8000, threads=8)


if __name__ == "__main__":
    main()
