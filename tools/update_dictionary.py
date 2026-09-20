#!/usr/bin/env python3
"""Download the current compressed German-Wiktionary Wiktextract dump and
build dictionary/nouns.json for the editor.

This is intentionally an editor maintenance tool. The generated dictionary is
never embedded into the single-HTML learning-card export.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "https://kaikki.org/dewiktionary/raw-wiktextract-data.jsonl.gz"


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Lernkarten-Werkstatt/0.4 dictionary updater"})
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk); got += len(chunk)
            if total:
                print(f"\rDownload: {got/1024/1024:7.1f} / {total/1024/1024:7.1f} MiB ({got*100/total:5.1f}%)", end="", flush=True)
            else:
                print(f"\rDownload: {got/1024/1024:7.1f} MiB", end="", flush=True)
    print()
    tmp.replace(dst)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Lokales deutsches Nomen-Wörterbuch aktualisieren")
    ap.add_argument("--keep-dump", action="store_true", help="großen Kaikki-Dump nach dem Import behalten")
    ap.add_argument("--dump", type=Path, default=root / "dictionary" / "raw-wiktextract-data.jsonl.gz")
    args = ap.parse_args()
    if not args.dump.exists():
        print("Lade aktuellen Kaikki/Wiktextract-Dump …")
        download(URL, args.dump)
    else:
        print(f"Verwende vorhandenen Dump: {args.dump}")
    cmd = [sys.executable, str(root / "tools" / "import_kaikki_dictionary.py"), str(args.dump)]
    subprocess.run(cmd, check=True, cwd=root)
    if not args.keep_dump:
        args.dump.unlink(missing_ok=True)
        print("Großen Roh-Dump gelöscht; kompaktes nouns.json bleibt erhalten.")


if __name__ == "__main__":
    main()
