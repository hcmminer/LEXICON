from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
CACHE = ROOT / ".cache"
OUT_DIR = ROOT / "out"

DEFAULT_DATABASE_URL = "postgresql:///dictionary?host=/tmp"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
