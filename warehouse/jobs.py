"""
warehouse/jobs.py

A small but production-shaped async job registry for the Lexicon console:

  * jobs run in a daemon thread (never block the FastAPI event loop)
  * every job reports {id, name, status, progress{done,total}, log[], error}
  * clients poll the registry (web UI auto-refreshes)
  * jobs can be cancelled cooperatively
  * a single running-job cap avoids thrashing the Postgres / LLM

Big-Tech shape: job queue + status API + live log, instead of a fire-and-forget
sync form POST that blocks the request.
"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

MAX_LOG_LINES = 200
_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_seq = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobContext:
    """Handle a running job uses to report progress, log lines and cancel."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self._cancelled = threading.Event()

    def log(self, line: str) -> None:
        append_log(self.job_id, line)

    def progress(self, done: int, total: int) -> None:
        set_progress(self.job_id, done, total)

    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()


def create_job(name: str) -> str:
    global _seq
    with _lock:
        _seq += 1
        job_id = f"{int(time.time())}-{_seq}"
        _jobs[job_id] = {
            "id": job_id,
            "name": name,
            "status": "queued",
            "progress": {"done": 0, "total": 0},
            "log": [f"queued {name}"],
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        return job_id


def _mark_running(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "running"
            job["started_at"] = _now()


def append_log(job_id: str, line: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["log"] = (job["log"] + [line])[-MAX_LOG_LINES:]


def set_progress(job_id: str, done: int, total: int) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["progress"] = {"done": int(done), "total": int(total)}


def cancel_job(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["status"] not in ("queued", "running"):
            return False
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["finished_at"] = _now()
        else:
            job["status"] = "cancelling"
        return True


def _finish(job_id: str, error: str | None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "error" if error else ("cancelled" if job["status"] == "cancelling" else "done")
            job["error"] = error
            job["finished_at"] = _now()
            if error:
                job["log"] = (job["log"] + [error])[-MAX_LOG_LINES:]


def run_job(name: str, fn: Callable[[JobContext], None]) -> str:
    """Queue `fn` (which receives a JobContext) and return its id."""
    job_id = create_job(name)

    def worker() -> None:
        ctx = JobContext(job_id)
        _mark_running(job_id)
        try:
            fn(ctx)
            if ctx.cancelled():
                append_log(job_id, "cancelled")
                _finish(job_id, None)
            else:
                append_log(job_id, "done")
                _finish(job_id, None)
        except Exception as exc:  # noqa: BLE001
            _finish(job_id, f"{exc}\n{traceback.format_exc()}")

    threading.Thread(target=worker, daemon=True).start()
    return job_id


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["id"], reverse=True)[:limit]
        return [dict(j) for j in jobs]


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def is_any_running() -> bool:
    with _lock:
        return any(j["status"] in ("queued", "running", "cancelling") for j in _jobs.values())


# ── Backward-compatible legacy ops helpers (used by /ops) ─────────────────────
_legacy_state: dict[str, Any] = {"running": False, "name": None, "log": [], "error": None}
_legacy_lock = threading.Lock()


def snapshot() -> dict[str, Any]:
    with _legacy_lock:
        return dict(_legacy_state)


def start(name: str, fn: Callable[[], None]) -> str | None:
    with _legacy_lock:
        if _legacy_state["running"]:
            return "A job is already running."
        _legacy_state.update({"running": True, "name": name, "log": [f"started {name}"], "error": None})

    def worker() -> None:
        try:
            fn()
            with _legacy_lock:
                _legacy_state["log"] = (_legacy_state["log"] + ["done"])[-MAX_LOG_LINES:]
        except Exception as exc:  # noqa: BLE001
            with _legacy_lock:
                _legacy_state["log"] = (_legacy_state["log"] + [traceback.format_exc()])[-MAX_LOG_LINES:]
                _legacy_state["error"] = str(exc)
        finally:
            with _legacy_lock:
                _legacy_state["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return None
