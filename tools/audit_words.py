#!/usr/bin/env python3
"""Audit article and plural of every theme entry against the offline dictionary.

The dictionary (dictionary/nouns.json) comes from the Kaikki/Wikitextract dump of
de.wiktionary.org and is editor-only -- it never reaches the exported HTML. This
tool only reports; it never edits a theme.

Example:
  python3 tools/audit_words.py
  python3 tools/audit_words.py --themes selected-themes --report dictionary/pruefbericht.md
  python3 tools/audit_words.py --only-errors --fail-on-error
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from stoffnamen import STOFFNAMEN

ARTICLES = ("der", "die", "das")

# Hinweise, keine Fehler: fachsprachliche Mehrzahlen von Stoffnamen, Wörter, die es
# nur in der Mehrzahl gibt, und Wörter, deren Mehrzahl von der Bedeutung abhängt.
NOTE_KINDS = {"plural-fehlt", "nur-mehrzahl", "wort-fehlt", "bedeutung"}

# Mehrzahl hängt an der Bedeutung: Unsere Themen meinen die eine, das Wörterbuch
# führt zuerst die andere.
SENSE_VARIANTS = {
    "atlas": "Kartenwerk (Atlanten), das Wörterbuch nennt zuerst die Stoffbedeutung (Atlasse)",
}

# Kurze Endungen, mit denen sich eine Mehrzahlform auf ihren Grundform zurückführen lässt.
PLURAL_SUFFIXES = ("nen", "en", "er", "es", "n", "e", "s")


def casefold(text: str) -> str:
    return (text or "").strip().casefold()


def clean_plural(text: str) -> str:
    """Strip a leading article and stray markers from a plural field."""
    value = (text or "").strip()
    for article in ARTICLES:
        if value.casefold().startswith(article + " "):
            value = value[len(article) + 1 :].strip()
    return value.strip(" .,")


@dataclass
class Finding:
    kind: str
    theme: str
    word: str
    detail: str


@dataclass
class Report:
    dic: dict
    findings: list[Finding] = field(default_factory=list)
    total: int = 0
    missing_words: list[str] = field(default_factory=list)
    plural_index: dict = field(default_factory=dict)

    def lemma_candidates(self, word: str) -> list[str]:
        """Guess the dictionary lemma of a plural form like 'Nudeln' -> 'Nudel'."""
        key = casefold(word)
        hits = list(self.plural_index.get(key) or [])
        for suffix in PLURAL_SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix) + 2:
                stem = key[: -len(suffix)]
                for candidate in (stem, stem + "e", stem + "en", stem + "er"):
                    entry = self.dic.get(candidate)
                    if entry and clean_plural(entry.get("plural", "")).casefold() == key:
                        hits.append(candidate)
        return sorted(set(hits))


def load_dictionary(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_entries(folder: Path) -> list[tuple[str, str, dict]]:
    rows: list[tuple[str, str, dict]] = []
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for theme in data if isinstance(data, list) else [data]:
            name = str(theme.get("themeName") or path.stem)
            for entry in theme.get("entries") or []:
                if isinstance(entry, dict) and entry.get("word"):
                    rows.append((path.name, name, entry))
    return rows


def build_plural_index(dic: dict) -> dict:
    index: dict[str, list[str]] = {}
    for key, entry in dic.items():
        for value in entry.get("plurals") or [entry.get("plural") or ""]:
            for form in str(value).split(","):
                plural = clean_plural(form)
                if plural and not plural.startswith("-"):
                    index.setdefault(casefold(plural), []).append(key)
    return index


def articles_of(entry: dict) -> list[str]:
    return [a for a in (entry.get("articles") or [entry.get("article")]) if a]


def plurals_of(entry: dict) -> list[str]:
    forms = entry.get("plurals") or [entry.get("plural") or ""]
    return [clean_plural(form) for form in forms if clean_plural(form)]


def check_entry(report: Report, theme: str, entry: dict) -> None:
    word = str(entry["word"]).strip()
    article = str(entry.get("article") or "").strip()
    plural = clean_plural(entry.get("plural", ""))
    plural_with_article = str(entry.get("pluralWithArticle") or "").strip()
    known = report.dic.get(casefold(word))
    report.total += 1

    # 1) Steht das Wort überhaupt im Wörterbuch?
    if known is None:
        lemmas = report.lemma_candidates(word)
        if lemmas:
            lemma = report.dic[lemmas[0]]
            detail = f"nur als Mehrzahl von „{lemma.get('word', lemmas[0])}“ bekannt"
            if not plural:
                detail += " – Feld „plural“ ist leer, das ist bei Mehrzahlwörtern richtig"
            report.findings.append(Finding("nur-mehrzahl", theme, word, detail))
        else:
            report.missing_words.append(word)
            report.findings.append(Finding("wort-fehlt", theme, word, "steht nicht im Offline-Wörterbuch"))
        return

    # 2) Artikel – jede im Wörterbuch belegte Variante ist in Ordnung.
    articles = articles_of(known)
    if article not in articles:
        report.findings.append(
            Finding("artikel", theme, word, f"Thema „{article}“, Wörterbuch „{'/'.join(articles) or '?'}“")
        )

    # 3) Mehrzahl – auch hier zählt jede belegte Variante. Stoffnamen haben
    #    bewusst keine (tools/stoffnamen.py).
    reference_forms = [casefold(form) for form in plurals_of(known)]
    theme_forms = [form.strip() for form in plural.split(",") if form.strip()]
    if reference_forms and not theme_forms and casefold(word) not in STOFFNAMEN:
        report.findings.append(
            Finding("plural-fehlt", theme, word, f"Thema leer, Wörterbuch „{', '.join(plurals_of(known))}“")
        )
    elif theme_forms and not reference_forms:
        report.findings.append(
            Finding("plural-ueberzaehlig", theme, word, f"Thema „{plural}“, Wörterbuch kennt keine Mehrzahl")
        )
    elif theme_forms and reference_forms and casefold(theme_forms[0]) not in reference_forms:
        hint = SENSE_VARIANTS.get(casefold(word))
        report.findings.append(
            Finding(
                "bedeutung" if hint else "plural",
                theme,
                word,
                hint or f"Thema „{plural}“, Wörterbuch „{', '.join(plurals_of(known))}“",
            )
        )

    # 4) Die vorgelesene Form muss zur Mehrzahl passen: die Grundform steckt am Ende,
    #    Adjektivbeugung davor ist erlaubt ("Roter Panda" -> "die roten Pandas").
    if plural:
        spoken = casefold(plural_with_article)
        head = casefold(plural).split()[-1]
        if spoken and not spoken.endswith(head):
            report.findings.append(
                Finding("vorsprech-form", theme, word, f"pluralWithArticle „{plural_with_article}“ passt nicht zu „{plural}“")
            )
    elif plural_with_article:
        report.findings.append(
            Finding("vorsprech-form", theme, word, f"pluralWithArticle „{plural_with_article}“ trotz leerer Mehrzahl")
        )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Artikel und Mehrzahl der Themen gegen das Offline-Wörterbuch prüfen")
    ap.add_argument("--themes", type=Path, default=root / "themes", help="Ordner mit Themen-JSONs")
    ap.add_argument("--dict", dest="dictionary", type=Path, default=root / "dictionary" / "nouns.json", help="Offline-Wörterbuch")
    ap.add_argument("--report", type=Path, help="Markdown-Bericht schreiben")
    ap.add_argument("--only-errors", action="store_true", help="nur Auffälligkeiten auflisten")
    ap.add_argument("--fail-on-error", action="store_true", help="Rückgabewert 1, wenn es Auffälligkeiten gibt")
    args = ap.parse_args()

    if not args.dictionary.exists():
        print(f"Wörterbuch fehlt: {args.dictionary} – erst „python3 tools/update_dictionary.py“ laufen lassen.")
        sys.exit(2)

    report = Report(dic=load_dictionary(args.dictionary))
    report.plural_index = build_plural_index(report.dic)
    rows = load_entries(args.themes)
    for _, theme, entry in rows:
        check_entry(report, theme, entry)

    titles = {
        "artikel": "falscher Artikel",
        "plural": "andere Mehrzahl",
        "plural-fehlt": "Hinweis: kein Plural im Thema (nur fachsprachliche Formen)",
        "plural-ueberzaehlig": "Mehrzahl erfunden?",
        "vorsprech-form": "Vorsprech-Form passt nicht",
        "nur-mehrzahl": "Hinweis: nur als Mehrzahl bekannt",
        "wort-fehlt": "Hinweis: nicht im Wörterbuch",
        "bedeutung": "Hinweis: Mehrzahl hängt an der Bedeutung",
    }
    order = ["artikel", "plural", "plural-ueberzaehlig", "vorsprech-form", "bedeutung", "plural-fehlt", "nur-mehrzahl", "wort-fehlt"]
    lines: list[str] = []
    lines.append(f"Wörterbuch: {len(report.dic):,} Nomen · geprüft: {report.total} Einträge aus {args.themes.name}/")
    errors = [f for f in report.findings if f.kind not in NOTE_KINDS]
    lines.append(f"Fehler: {len(errors)} · Hinweise: {len(report.findings) - len(errors)}")
    for kind in order:
        hits = [f for f in report.findings if f.kind == kind]
        if not hits:
            continue
        lines.append("")
        lines.append(f"## {titles[kind]} ({len(hits)})")
        for finding in hits:
            lines.append(f"- **{finding.word}** ({finding.theme}): {finding.detail}")
    if not report.findings:
        lines.append("Keine Auffälligkeiten. ✅")

    text = "\n".join(lines)
    if args.only_errors and not report.findings:
        text = lines[0] + "\nKeine Auffälligkeiten. ✅"
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
        print(f"\nBericht geschrieben: {args.report}")
    if args.fail_on_error and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
