#!/usr/bin/env python3
"""Article balance report: how often der/die/das appear per theme and area.

Author tool, not learner material. German nouns are not evenly spread over the
three articles - fruit is almost always "die", jobs are mostly "der" - so a deck
that follows a topic tends to drift away from the didactically useful one third
per article. This report shows that drift per theme and per deck-plan file so
the missing article is easy to add.

Measured value is Cramer's V against an equal distribution (0 = perfect, 1 =
only one article), plus how many words are missing to reach equal counts and
which article they belong to.

Example:
  python3 tools/artikel_balance.py
  python3 tools/artikel_balance.py --bereich 02-krabbeltiere-obst --worte
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ("der", "die", "das")


@dataclass
class Group:
    """A theme or an area with its article counts."""

    title: str
    area: str = ""
    counts: dict[str, int] = field(default_factory=lambda: {a: 0 for a in ARTICLES})
    words: dict[str, list[str]] = field(default_factory=lambda: {a: [] for a in ARTICLES})

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def chi2(self) -> float:
        """Abstand zur Gleichverteilung (jeder Artikel ein Drittel)."""
        if not self.total:
            return 0.0
        expected = self.total / 3
        return sum((self.counts[a] - expected) ** 2 / expected for a in ARTICLES)

    @property
    def v(self) -> float:
        """Cramérs V, 0 = gleichmäßig, 1 = nur ein Artikel."""
        return (self.chi2 / (2 * self.total)) ** 0.5 if self.total else 0.0

    @property
    def max_share(self) -> float:
        return max(self.counts.values()) / self.total if self.total else 0.0

    @property
    def missing(self) -> dict[str, int]:
        """Fehlende Wörter je Artikel, damit alle drei gleich oft vorkommen."""
        if not self.total:
            return {}
        expected = self.total / 3
        return {a: round(expected - self.counts[a]) for a in ARTICLES if self.counts[a] < expected - 0.5}

    @property
    def to_balance(self) -> int:
        """Wie viele Wörter fehlen, um auf gleiche Zahlen zu kommen."""
        return 3 * max(self.counts.values()) - self.total if self.total else 0


def area_map(plan_folder: Path) -> dict[str, str]:
    """Themen-Kennung -> Deck-Plan-Datei ("Themenbereich")."""
    mapping: dict[str, str] = {}
    for path in sorted(plan_folder.glob("*.json")):
        for theme in json.loads(path.read_text(encoding="utf-8")).get("themes") or []:
            mapping[str(theme["id"])] = path.stem
    return mapping


def load_themes(folder: Path, areas: dict[str, str]) -> list[Group]:
    groups: list[Group] = []
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        entries = doc.get("entries") or []
        if not entries:
            continue
        theme_id = str(doc.get("themeId") or path.stem)
        slug = theme_id.split("-", 2)[-1] if theme_id.startswith("theme-") else theme_id
        group = Group(str(doc.get("themeName") or path.stem), areas.get(slug, areas.get(theme_id, "?")))
        for entry in entries:
            article = str(entry.get("article") or "")
            if article not in ARTICLES:
                continue
            group.counts[article] += 1
            group.words[article].append(str(entry.get("word") or ""))
        for words in group.words.values():
            words.sort()
        groups.append(group)
    return groups


def combine(title: str, groups: list[Group]) -> Group:
    total = Group(title)
    for group in groups:
        total.counts = {a: total.counts[a] + group.counts[a] for a in ARTICLES}
        for a in ARTICLES:
            total.words[a].extend(group.words[a])
    return total


def gap_text(group: Group) -> str:
    parts = [f"{count}× {article}" for article, count in
             sorted(group.missing.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ", ".join(parts) if parts else "–"


def reserve_words(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Gestrichene Wörter je Theme aus themen-reserve/verworfen.md.

    Die Liste ist auf 96 Zeichen umbrochen, deshalb wird erst der ganze
    Abschnitt eingesammelt und dann ausgewertet.
    """
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    theme = ""
    body: list[str] = []

    def auswerten() -> None:
        if theme and body:
            out[theme].extend((m.group(1).strip(), m.group(2).strip())
                              for m in re.finditer(r"`([^`]+)`\s*\(([^)]*)\)?", " ".join(body)))

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            auswerten()
            theme = line[4:].split(" – ")[0].strip()
            body = []
            continue
        if line.startswith("#"):
            continue
        if line.strip():
            body.append(line.strip())
    auswerten()
    return out


def reserve_report(themes: list[Group], reserve: dict[str, list[tuple[str, str]]],
                   dictionary: dict, limit: int) -> None:
    """Wörter der Streichliste, deren Artikel im Theme fehlt - die schnellsten Lückenfüller.

    ``kein Satz geschrieben`` heißt: Bild war frei, nur die zwei Sätze fehlen.
    ``kein eigenes Bild`` heißt: das Motiv ist vergeben (Zweitzeichnung, MDI-Icon
    oder neues Bild nötig).
    """
    by_name = {t.title: t for t in themes}
    rows: list[tuple[int, str, str, str, str]] = []
    for name, words in reserve.items():
        theme = by_name.get(name)
        if theme is None:
            continue
        for word, reason in words:
            entry = dictionary.get(word.casefold())
            if entry is None:
                continue
            variants = entry.get("articles") or [entry.get("article") or ""]
            passend = [a for a in variants if a in theme.missing]
            if not passend:
                continue
            aufwand = ("nur Sätze schreiben" if "kein Satz geschrieben" in reason
                       else "Bild nötig" if "kein eigenes Bild" in reason
                       else reason or "?")
            rows.append((theme.missing[passend[0]], theme.title, word,
                         "/".join(passend), aufwand))
    if not rows:
        return
    print("\n## Streichliste: gestrichene Wörter mit dem fehlenden Artikel")
    print(f"{'Theme':<28}{'Wort':<20}{'Artikel':<9}{'Aufwand'}")
    for _, name, word, art, aufwand in sorted(rows, key=lambda r: (-r[0], r[1], r[2]))[:limit]:
        print(f"{name[:27]:<28}{word[:19]:<20}{art:<9}{aufwand}")
    print("\n(Quelle: themen-reserve/verworfen.md · „nur Sätze schreiben“ = Bild ist frei,")
    print(" es fehlen nur die zwei Sätze in tools/saetze/*.json.)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Artikel-Verteilung je Thema und Themenbereich zeigen")
    ap.add_argument("--themes", type=Path, default=ROOT / "selected-themes",
                    help="Ordner mit den Theme-JSONs (Standard: selected-themes)")
    ap.add_argument("--plans", type=Path, default=ROOT / "tools" / "decks",
                    help="Deck-Plan-Ordner, der die Themenbereiche liefert")
    ap.add_argument("--reserve", type=Path, nargs="?",
                    const=ROOT / "themen-reserve" / "verworfen.md", default=None,
                    help="Streichliste mitprüfen (Standardpfad themen-reserve/verworfen.md)")
    ap.add_argument("--max-reserve", type=int, default=40,
                    help="höchstens so viele Zeilen der Streichliste")
    ap.add_argument("--bereich", default="", help="nur ein Themenbereich, z. B. 01-tiere")
    ap.add_argument("--min", type=int, default=0, help="Themes unter dieser Wortzahl weglassen")
    ap.add_argument("--worte", action="store_true", help="die Wörter je Artikel auflisten")
    args = ap.parse_args()

    themes = [t for t in load_themes(args.themes, area_map(args.plans)) if t.total >= args.min]
    if args.bereich:
        themes = [t for t in themes if t.area.startswith(args.bereich)]
    if not themes:
        raise SystemExit(f"Keine Themes mit Einträgen in {args.themes}")

    by_area: dict[str, list[Group]] = defaultdict(list)
    for theme in themes:
        by_area[theme.area].append(theme)

    print(f"# {len(themes)} Themes · {sum(t.total for t in themes)} Wörter · "
          f"Ziel je Artikel: ein Drittel\n")
    print("## Themenbereiche")
    print(f"{'Bereich':<26}{'n':>4}{'der':>5}{'die':>5}{'das':>5}{'V':>7}   fehlt für Gleichstand")
    for area in sorted(by_area, key=lambda a: -combine(a, by_area[a]).v):
        group = combine(area, by_area[area])
        print(f"{area:<26}{group.total:>4}{group.counts['der']:>5}{group.counts['die']:>5}"
              f"{group.counts['das']:>5}{group.v:>7.3f}   {gap_text(group)}")
    gesamt = combine("GESAMT", themes)
    print(f"{'GESAMT':<26}{gesamt.total:>4}{gesamt.counts['der']:>5}{gesamt.counts['die']:>5}"
          f"{gesamt.counts['das']:>5}{gesamt.v:>7.3f}   {gap_text(gesamt)}")

    print("\n## Themes (schlechteste Balance zuerst)")
    print(f"{'Theme':<34}{'Bereich':<24}{'n':>4}{'der':>5}{'die':>5}{'das':>5}{'V':>7}"
          f"{'größter':>9}{'auf Gleichstand':>18}")
    for theme in sorted(themes, key=lambda t: -t.v):
        print(f"{theme.title[:33]:<34}{theme.area[:23]:<24}{theme.total:>4}{theme.counts['der']:>5}"
              f"{theme.counts['die']:>5}{theme.counts['das']:>5}{theme.v:>7.3f}"
              f"{theme.max_share * 100:>8.0f}%{theme.to_balance:>12} W ({gap_text(theme)})")

    if args.worte:
        print("\n## Wörter je Theme und Artikel")
        for theme in sorted(themes, key=lambda t: -t.v):
            print(f"\n**{theme.title}** ({theme.total} Wörter) – {theme.area}")
            for article in ARTICLES:
                fehlt = theme.missing.get(article, 0)
                hint = f" ← {fehlt} fehlen" if fehlt else ""
                print(f"  {article}: {theme.counts[article]}{hint}")
                print(f"     {', '.join(theme.words[article]) or '–'}")

    if args.reserve:
        dictionary = json.loads((ROOT / "dictionary" / "nouns.json").read_text(encoding="utf-8"))
        reserve_report(themes, reserve_words(args.reserve), dictionary, args.max_reserve)


if __name__ == "__main__":
    main()
