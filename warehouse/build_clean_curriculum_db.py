"""
warehouse/build_clean_curriculum_db.py

Builds a 100% clean, automated pedagogical database matching CORE_SCHEMA.
Integrates Oxford 3000/5000, CEFR A1-B2 syllabus, and verified 35-language translations.
No manual concept arrays: 100% automated data-driven compilation.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from warehouse.config import OUT_DIR
from warehouse.export_sqlite import write_catalog_sqlite
from warehouse.build_pedagogical_core import build_pedagogical_catalog


def build_and_export_clean_database(top_n: int = 12000) -> Path:
    print(f"Building automated pedagogical catalog for top {top_n} concepts...")
    catalog = build_pedagogical_catalog(top_n=top_n)
    
    catalog["count"] = len(catalog["concepts"])
    db_path = OUT_DIR / "lexicon-core.db"
    write_catalog_sqlite(catalog, db_path)
    gz_path = OUT_DIR / "lexicon-core.db.gz"
    gz_path.write_bytes(gzip.compress(db_path.read_bytes(), compresslevel=9))
    print(f"Exported clean SQLite to {db_path} ({catalog['count']} concepts)")

    # Sync to frontend-extension
    frontend_dest = Path("/Users/admin/Documents/Fumihiko/livecode-extension/frontend-extension/public/vocabulary")
    if frontend_dest.exists():
        (frontend_dest / "lexicon-core.db.gz").write_bytes(gz_path.read_bytes())
        (frontend_dest / "lexicon-core.db").write_bytes(db_path.read_bytes())
        print(f"Synced pristine database to {frontend_dest}")

    return db_path


if __name__ == "__main__":
    build_and_export_clean_database()
