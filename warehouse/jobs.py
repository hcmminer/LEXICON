from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone
from typing import Callable

_lock = threading.Lock()
_state: dict[str, object] = {
    "running": False,
    "name": None,
    "log": [],
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def snapshot() -> dict[str, object]:
    with _lock:
        return dict(_state)


def _append(line: str) -> None:
    _state["log"] = (list(_state["log"]) + [line])[-80:]


def start(name: str, fn: Callable[[], None]) -> str | None:
    with _lock:
        if _state["running"]:
            return "A job is already running."
        _state.update(
            {
                "running": True,
                "name": name,
                "log": [f"started {name}"],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "error": None,
            }
        )

    def worker() -> None:
        try:
            fn()
            with _lock:
                _append("done")
                _state["error"] = None
        except Exception as exc:
            with _lock:
                _append(traceback.format_exc())
                _state["error"] = str(exc)
        finally:
            with _lock:
                _state["running"] = False
                _state["finished_at"] = datetime.now(timezone.utc).isoformat()

    threading.Thread(target=worker, daemon=True).start()
    return None
