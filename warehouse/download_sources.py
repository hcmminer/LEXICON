from __future__ import annotations

import argparse
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

from warehouse.config import CACHE
from warehouse.ingest.kaikki_langs import KAIKKI_NATIVE_LANGS

DATA_SOURCES = {
    "wordnet": {
        "filename": "wordnet.zip",
        "urls": [
            "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip",
            "https://github.com/nltk/nltk_data/raw/gh-pages/packages/corpora/wordnet.zip",
        ],
        "dest_subdir": "nltk_data/corpora",
        "extract": True,
        "check_path": "nltk_data/corpora/wordnet",
    },
    "omw": {
        "filename": "omw-1.4.zip",
        "urls": [
            "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/omw-1.4.zip",
            "https://github.com/nltk/nltk_data/raw/gh-pages/packages/corpora/omw-1.4.zip",
        ],
        "dest_subdir": "nltk_data/corpora",
        "extract": True,
        "check_path": "nltk_data/corpora/omw-1.4",
    },
    "wiktionary": {
        "filename": "kaikki.org-dictionary-English.jsonl.gz",
        "urls": [
            "https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz",
        ],
        "dest_subdir": "",
        "extract": False,
        "check_path": "kaikki.org-dictionary-English.jsonl.gz",
    },
}

for _iso, _name in KAIKKI_NATIVE_LANGS.items():
    _fname = f"kaikki.org-dictionary-{_name.replace(' ', '_')}.jsonl.gz"
    DATA_SOURCES[f"kaikki-{_iso}"] = {
        "filename": _fname,
        "urls": [f"https://kaikki.org/dictionary/{_name}/kaikki.org-dictionary-{_name}.jsonl.gz"],
        "dest_subdir": "kaikki-native",
        "extract": False,
        "check_path": f"kaikki-native/{_fname}",
    }


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def download_file(urls: list[str], dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest.with_suffix(dest.suffix + ".part")
    
    headers = {"User-Agent": "LexiconDataPlatform/1.0 (Enterprise Dictionary Ingester)"}

    for url in urls:
        log(f"📥 Downloading from: {url}")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response, temp_dest.open("wb") as out_file:
                total = response.headers.get("Content-Length")
                expected = int(total) if total else None
                read = 0
                last_mb = 0

                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    read += len(chunk)
                    curr_mb = read // (1024 * 1024)
                    if curr_mb > last_mb and curr_mb % 20 == 0:
                        last_mb = curr_mb
                        if expected:
                            log(f"   Progress: {read / expected * 100:5.1f}% ({curr_mb} MB / {expected // (1024*1024)} MB)")
                        else:
                            log(f"   Downloaded: {curr_mb} MB")

            temp_dest.replace(dest)
            log(f"✅ Saved to {dest} ({dest.stat().st_size // (1024*1024)} MB)")
            return True
        except Exception as exc:
            log(f"⚠️ Failed to download from {url}: {exc}")
            if temp_dest.exists():
                temp_dest.unlink()

    return False


def ensure_data_source(name: str, force: bool = False) -> bool:
    if name not in DATA_SOURCES:
        log(f"❌ Unknown data source: {name}")
        return False

    spec = DATA_SOURCES[name]
    check_target = CACHE / spec["check_path"]

    if check_target.exists() and not force:
        log(f"✨ Found cached {name} at {check_target}")
        return True

    dest_file = CACHE / spec["dest_subdir"] / spec["filename"] if spec["dest_subdir"] else CACHE / spec["filename"]
    
    if not dest_file.exists() or force:
        success = download_file(spec["urls"], dest_file)
        if not success:
            log(f"❌ Could not download {name} from any available mirror.")
            return False

    if spec.get("extract") and dest_file.suffix == ".zip":
        extract_dir = CACHE / spec["dest_subdir"]
        log(f"📦 Extracting {dest_file.name} to {extract_dir}...")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest_file, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        log(f"✅ Extracted {name}")

    return True


def ensure_all_sources(force: bool = False) -> bool:
    log("🚀 Checking and verifying all upstream dictionary sources...")
    all_ok = True
    for name in DATA_SOURCES:
        ok = ensure_data_source(name, force=force)
        if not ok:
            all_ok = False
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify upstream linguistic source dumps")
    parser.add_argument("--source", choices=list(DATA_SOURCES.keys()) + ["all"], default="all")
    parser.add_argument("--force", action="store_true", help="Force re-download even if cache exists")
    args = parser.parse_args()

    if args.source == "all":
        ok = ensure_all_sources(force=args.force)
    else:
        ok = ensure_data_source(args.source, force=args.force)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
