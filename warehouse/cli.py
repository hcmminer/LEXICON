from __future__ import annotations

import argparse
from pathlib import Path

from warehouse.config import OUT_DIR
from warehouse.db import migrate
from warehouse.export_json import export_json
from warehouse.ingest.readings import ingest_readings
from warehouse.ingest.seed import seed_reference_data
from warehouse.ingest.wiktionary import ingest_wiktionary
from warehouse.ingest.wordfreq import ingest_wordfreq
from warehouse.ingest.wordnet_omw import ingest_omw, ingest_wordnet
from warehouse.rank import compute_ranks


def main() -> int:
    parser = argparse.ArgumentParser(description="Core vocabulary warehouse")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="create schema")

    ingest = sub.add_parser("ingest", help="load dumps into Postgres")
    ingest.add_argument("--limit", type=int, help="cap wordfreq list and wiktionary entries (smoke)")
    ingest.add_argument("--skip-wiktionary", action="store_true")
    ingest.add_argument("--skip-readings", action="store_true")
    ingest.add_argument("--wordnet-only", action="store_true")

    rank = sub.add_parser("rank", help="rebuild per-language ranks")
    rank.add_argument("--top-n", type=int, default=12000)

    export = sub.add_parser("export", help="write core_vocabulary.json")
    export.add_argument("--out", type=Path, default=OUT_DIR)
    export.add_argument("--top-n", type=int, default=12000)

    args = parser.parse_args()
    if args.cmd == "migrate":
        migrate()
        seed_reference_data()
        print("migrated")
        return 0
    if args.cmd == "ingest":
        ingest_wordfreq(limit_per_lang=args.limit)
        ingest_wordnet()
        ingest_omw()
        if not args.wordnet_only and not args.skip_wiktionary:
            ingest_wiktionary(max_entries=args.limit)
        if not args.skip_readings:
            ingest_readings(limit=args.limit)
        return 0
    if args.cmd == "rank":
        compute_ranks(args.top_n)
        return 0
    if args.cmd == "export":
        export_json(args.out, args.top_n)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
