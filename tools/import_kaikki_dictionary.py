#!/usr/bin/env python3
"""Extract a compact German noun dictionary from a Kaikki/Wiktextract JSONL dump.

Example:
  python3 tools/import_kaikki_dictionary.py ~/Downloads/de-extract.jsonl.gz

The output only stores lemma, article and nominative plural and is intended for
local editor assistance. It is not embedded into exported learning-card HTML.

An existing dictionary file is kept as a fallback: words that the dump does not
contain stay in the result, everything the dump knows wins.
"""
from __future__ import annotations
import argparse, gzip, json
from pathlib import Path

GENDER_TO_ARTICLE = {
    "masculine": "der",
    "feminine": "die",
    "neuter": "das",
}


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.suffix == ".gz" else path.open("r", encoding="utf-8", errors="replace")


def extract(row: dict):
    """Pull every article and every nominative plural of one dump row.

    German nouns are ambiguous often enough ("der/die Paprika", "Atlas/Atlanten"
    versus "Atlasse"), so all variants are kept and the first one becomes the
    primary value the editor shows.
    """
    if row.get("lang_code") != "de" or row.get("pos") != "noun":
        return None
    word = str(row.get("word", "")).strip()
    if not word or not word[:1].isupper():
        return None

    tags = set(row.get("tags") or [])
    articles = [a for g, a in GENDER_TO_ARTICLE.items() if g in tags]
    plurals: list[str] = []
    accusative: list[str] = []
    dative: list[str] = []
    for form in row.get("forms") or []:
        if not isinstance(form, dict):
            continue
        ftags = set(form.get("tags") or [])
        value = str(form.get("form", "")).strip()
        if {"nominative", "singular"} <= ftags and form.get("article") in {"der", "die", "das"}:
            if form["article"] not in articles:
                articles.append(form["article"])
        if {"nominative", "plural"} <= ftags and value and value not in {"-", "—"}:
            if value.startswith("die "):
                value = value[4:].strip()
            if value not in plurals:
                plurals.append(value)
        # Schwache Nomen: Bär -> den Bären, Mensch -> den Menschen. Der Dump kennt
        # diese Formen, deshalb braucht niemand eine Liste im Code.
        if "singular" in ftags and value:
            if "accusative" in ftags and value not in accusative:
                accusative.append(value)
            if "dative" in ftags and value not in dative:
                dative.append(value)
    if not articles:
        return None
    return word, {
        "word": word,
        "article": articles[0],
        "articles": articles,
        "plural": plurals[0] if plurals else "",
        "plurals": plurals,
        "accusative": accusative,
        "dative": dative,
        "source": "Kaikki/Wiktionary",
    }


def merge(target: dict, data: dict) -> None:
    """Add article and plural variants of a second sense of the same word."""
    for field in ("articles", "plurals", "accusative", "dative"):
        source = data.get(field) or ([data.get(field[:-1])] if data.get(field[:-1]) else [])
        target.setdefault(field, [])
        for value in source:
            if value and value not in target[field]:
                target[field].append(value)
    target["article"] = target["articles"][0] if target["articles"] else ""
    target["plural"] = target["plurals"][0] if target["plurals"] else ""


def load_existing(path: Path) -> dict:
    """Return the current dictionary so unknown words are not lost."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    for entry in data.values():
        if isinstance(entry, dict):
            entry.setdefault("articles", [entry.get("article")] if entry.get("article") else [])
            entry.setdefault("plurals", [entry.get("plural")] if entry.get("plural") else [])
            entry.setdefault("accusative", [])
            entry.setdefault("dative", [])
    return data


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Kaikki/Wiktextract JSONL or JSONL.GZ")
    ap.add_argument("--output", type=Path, default=root / "dictionary" / "nouns.json")
    ap.add_argument("--no-merge", action="store_true", help="vorhandene Wörterbuchdatei nicht als Rückfall behalten")
    args = ap.parse_args()

    result = {}
    with open_text(args.input) as f:
        for n, line in enumerate(f, 1):
            try:
                item = extract(json.loads(line))
            except Exception:
                continue
            if item:
                word, data = item
                current = result.get(word.casefold())
                if current is None:
                    result[word.casefold()] = data
                else:
                    merge(current, data)
            if n % 100000 == 0:
                print(f"{n:,} Zeilen · {len(result):,} Nomen")
    kept = 0
    if not args.no_merge:
        for key, entry in load_existing(args.output).items():
            if key not in result:
                result[key] = entry
                kept += 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"FERTIG: {len(result):,} Nomen -> {args.output}" + (f" ({kept:,} aus der alten Datei behalten)" if kept else ""))


if __name__ == "__main__":
    main()
