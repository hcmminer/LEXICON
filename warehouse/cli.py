from __future__ import annotations

import argparse
from pathlib import Path

from warehouse.config import OUT_DIR
from warehouse.db import migrate
from warehouse.export_json import export_json
from warehouse.export_sqlite import export_sqlite
from warehouse.ingest.readings import ingest_readings
from warehouse.ingest.seed import seed_reference_data
from warehouse.ingest.wiktionary import ingest_wiktionary
from warehouse.ingest.wordfreq import ingest_wordfreq
from warehouse.ingest.wordnet_omw import ingest_omw, ingest_wordnet
from warehouse.rank import compute_ranks


def main() -> int:
    parser = argparse.ArgumentParser(description="Core vocabulary warehouse")
    sub = parser.add_subparsers(dest="cmd", required=True)

    app_cmd = sub.add_parser("app", help="open the local B2B console")
    app_cmd.add_argument("--host", default="127.0.0.1")
    app_cmd.add_argument("--port", type=int, default=8787)

    sub.add_parser("migrate", help="create schema")

    ingest = sub.add_parser("ingest", help="load dumps into Postgres")
    ingest.add_argument("--limit", type=int, help="cap wordfreq list and wiktionary entries (smoke)")
    ingest.add_argument("--skip-wiktionary", action="store_true")
    ingest.add_argument("--skip-readings", action="store_true")
    ingest.add_argument("--wordnet-only", action="store_true")
    ingest.add_argument(
        "--only",
        choices=("wordfreq", "wordnet", "omw", "wiktionary", "readings"),
        help="run a single ingest step",
    )

    rank = sub.add_parser("rank", help="rebuild per-language ranks")
    rank.add_argument("--top-n", type=int, default=12000)

    export = sub.add_parser("export", help="write core_vocabulary.json")
    export.add_argument("--out", type=Path, default=OUT_DIR)
    export.add_argument("--top-n", type=int, default=12000)
    export.add_argument("--pivot", type=str, help="pivot language for a pack export (e.g. zh)")

    export_sqlite_cmd = sub.add_parser("export-sqlite", help="write lexicon-core.db")
    export_sqlite_cmd.add_argument("--out", type=Path, default=OUT_DIR)
    export_sqlite_cmd.add_argument("--top-n", type=int, default=12000)
    export_sqlite_cmd.add_argument("--pivot", type=str)
    export_sqlite_cmd.add_argument("--from-json", type=Path, help="convert an existing catalog JSON/JSON.GZ")

    args = parser.parse_args()
    if args.cmd == "app":
        from warehouse.web import run

        run(args.host, args.port)
        return 0
    if args.cmd == "migrate":
        migrate()
        seed_reference_data()
        print("migrated")
        return 0
    if args.cmd == "ingest":
        only = args.only
        if only in (None, "wordfreq") and not args.wordnet_only:
            ingest_wordfreq(limit_per_lang=args.limit)
        if only in (None, "wordnet") or args.wordnet_only:
            ingest_wordnet()
        if only in (None, "omw") and not args.wordnet_only:
            ingest_omw()
        if only in (None, "wiktionary") and not args.wordnet_only and not args.skip_wiktionary:
            ingest_wiktionary(max_entries=args.limit)
        if only in (None, "readings") and not args.skip_readings:
            ingest_readings(limit=args.limit)
        return 0
    if args.cmd == "rank":
        compute_ranks(args.top_n)
        return 0
    if args.cmd == "export":
        export_json(args.out, args.top_n, args.pivot)
        return 0
    if args.cmd == "export-sqlite":
        export_sqlite(args.out, args.top_n, args.pivot, args.from_json)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
