import json
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8787"
KINDS = [("gloss-6000", "Glosses top 6000"), ("gloss-9000", "Glosses top 9000"), ("gloss-12000", "Glosses top 12000")]


def api(path, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(BASE + path, data=body, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def all_jobs():
    return api("/jobs/api")["jobs"]


def any_running():
    return any(j["status"] in ("running", "queued", "cancelling") for j in all_jobs())


def latest_done_name():
    return next((j["name"] for j in all_jobs() if j["status"] == "done"), None)


i = 0
while i < len(KINDS):
    kind, label = KINDS[i]
    if any_running():
        time.sleep(20)
        continue
    done = latest_done_name()
    if done == label:
        print(f"[chain] {label} done ✓", flush=True)
        i += 1
        continue
    api("/jobs/start", {"kind": kind})
    print(f"[chain] started {label}", flush=True)
    time.sleep(20)

print("[chain] ALL DONE", flush=True)
