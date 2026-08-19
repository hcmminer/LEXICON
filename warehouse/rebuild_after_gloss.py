"""Wait for the gloss chain to finish, then rebuild export + extension seed."""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8787"
BIGDATA = "/Users/admin/Documents/big-data"
FE = "/Users/admin/Documents/Fumihiko/livecode-extension/frontend-extension"
PY = "/Users/admin/Documents/big-data/.venv/bin/python"


def api(path):
    req = urllib.request.Request(BASE + path)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


# 1) wait until no job is running and 'Glosses top 12000' is done
while True:
    try:
        jobs = api("/jobs/api")["jobs"]
    except Exception:
        time.sleep(20)
        continue
    running = any(j["status"] in ("running", "queued", "cancelling") for j in jobs)
    finished_12000 = any(j["name"] == "Glosses top 12000" and j["status"] == "done" for j in jobs)
    if not running and finished_12000:
        log("gloss chain finished; starting rebuild")
        break
    cur = next((j for j in jobs if j["status"] == "running"), None)
    log(f"waiting… {'running' if cur else 'idle'} {cur['progress'] if cur else ''}")
    time.sleep(45)

# 2) rebuild export (union 12000 + 140 packs) with full gloss cache
log("step 1/2: export_pedagogical_assets()")
r = subprocess.run([PY, "-c", "from warehouse.build_pedagogical_core import export_pedagogical_assets; export_pedagogical_assets()"],
                   cwd=BIGDATA, capture_output=True, text=True, timeout=3600)
print(r.stdout[-3000:] or r.stderr[-3000:], flush=True)
if r.returncode != 0:
    log(f"FATAL export failed: {r.stderr[-2000:]}"); sys.exit(1)
log("export OK")

# 3) rebuild extension seed sqlite
log("step 2/2: json-to-lexicon-sqlite.py")
r2 = subprocess.run([PY, "scripts/json-to-lexicon-sqlite.py",
                     f"{BIGDATA}/out/core_vocabulary.json.gz",
                     "public/vocabulary/lexicon-core.db"],
                    cwd=FE, capture_output=True, text=True, timeout=600)
print(r2.stdout[-2000:] or r2.stderr[-2000:], flush=True)
if r2.returncode != 0:
    log(f"FATAL seed failed: {r2.stderr[-2000:]}"); sys.exit(1)
log("SEED REBUILT — verify with typecheck/tests next")
