#!/usr/bin/env python3
"""Index the Fluent Emoji catalogue for the picture search.

Fluent Emoji (Microsoft, MIT) draws nearly the same emoji set as OpenMoji, but
in a third style - the third drawing of a motif that the deck builder can fall
back to when the OpenMoji and Twemoji artwork of a word is already taken.

The repository holds the drawings under ``assets/<Title>/Color/<file>.svg``
(the *Color* variant is the one used here; 3D and the skin-tone variants are
ignored). This tool reads the file tree once, matches every drawing to the
OpenMoji code from ``catalog.json`` - so a word can ask for the same motif in
any of the three sets - and writes the index used by ``image_providers.py``.

Example:
  python3 tools/import_fluent_emoji.py             # pin the current main commit
  python3 tools/import_fluent_emoji.py --ref <sha>  # re-index a fixed commit
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bilder_waehlen as editor  # noqa: E402
import image_providers  # noqa: E402

REPO = "microsoft/fluentui-emoji"
API = f"https://api.github.com/repos/{REPO}"
OUTPUT = ROOT / "tools" / "image-sources" / "fluent.json"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "lernkarten-werkstatt"})
    with urllib.request.urlopen(request, timeout=120) as answer:
        return answer.read()


@functools.lru_cache(maxsize=1)
def code_by_title() -> dict[str, str]:
    """Normalisierter englischer Titel -> OpenMoji-Code."""
    def normal(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

    return {normal(row["title"]): str(row["code"]) for row in image_providers.catalog()["items"]}


def slug_key(title: str, code: str) -> str:
    """Schlüssel im Slug: der Emoji-Code, sonst der Titel des Motivs."""
    if code:
        return code
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "motiv"


def build(ref: str) -> dict:
    tree = json.loads(fetch(f"{API}/git/trees/{ref}?recursive=1"))
    if tree.get("truncated"):
        raise SystemExit("Dateibaum abgeschnitten - bitte später erneut versuchen")
    namen = code_by_title()
    items: list[dict] = []
    for entry in tree["tree"]:
        path = str(entry["path"])
        parts = path.split("/")
        if len(parts) != 4 or parts[0] != "assets" or parts[2] != "Color":
            continue
        if not path.endswith(".svg"):
            continue
        title = parts[1]
        code = namen.get(re.sub(r"[^a-z0-9]+", " ", title.lower()).strip(), "")
        items.append({"slug": f"fluent--{slug_key(title, code)}", "code": code,
                      "title": title, "file": path})
    items.sort(key=lambda row: (row["code"] or "zz", row["title"]))
    if len(items) < 1000:
        raise SystemExit(f"Nur {len(items)} Zeichnungen gefunden - Abbruch")
    return {
        "name": "Fluent Emoji",
        "repository": f"https://github.com/{REPO}",
        "ref": ref,
        "license": "MIT",
        "licenseUrl": f"https://github.com/{REPO}/blob/{ref}/LICENSE",
        "author": "Microsoft Corporation and contributors",
        "note": ("Nur die Color-Variante der Grundzeichnung (assets/<Motiv>/Color/). "
                 "Der Code ist der OpenMoji-Code desselben Motivs - so kann ein Wort "
                 "dieselbe Zeichnung in jeder der drei Sammlungen anfordern."),
        "items": items,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fluent-Emoji-Index für die Bildsuche schreiben")
    ap.add_argument("--ref", default="", help="Commit oder Zweig (Vorgabe: aktueller main)")
    args = ap.parse_args()

    ref = args.ref or json.loads(fetch(f"{API}/commits/main"))["sha"]
    index = build(ref)
    editor.atomic(OUTPUT, index)
    mit_code = sum(1 for row in index["items"] if row["code"])
    print(f"{OUTPUT} · {len(index['items'])} Zeichnungen · {mit_code} mit OpenMoji-Code · "
          f"Stand {ref[:10]}")


if __name__ == "__main__":
    main()
