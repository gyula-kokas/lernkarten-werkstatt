#!/usr/bin/env python3
"""Build a review sheet: every theme with all its words and pictures.

The page is meant for authors, not for learners: it lines up every deck word
next to its picture, article, plural and both sentences, so odd combinations
(wrong picture, strange word, picture shared with another theme) are easy to
spot. Pictures used in more than one theme are marked, because that is what a
learner notices first.

Example:
  python3 tools/word_overview.py
  python3 tools/word_overview.py --output output-selected/wortuebersicht.html
"""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

STYLE = """
:root{--der:#1f6bb4;--die:#d73b78;--das:#278d45;--line:#dcdcdc}
*{box-sizing:border-box}
body{margin:0;padding:24px 28px 60px;background:#f6f6f4;color:#22252a;
  font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
h1{margin:0 0 6px;font-size:24px}
h2{margin:34px 0 4px;font-size:19px;border-bottom:2px solid var(--line);padding-bottom:4px}
h2 small{font-weight:400;color:#6b7280;font-size:13px}
.summary{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:14px 0 6px}
.summary b{font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin-top:12px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px}
.card.dupe{border-color:#e8a33d;box-shadow:0 0 0 2px #fdf2dd inset}
.pic{height:104px;display:flex;align-items:center;justify-content:center;background:#fff}
.pic svg{max-height:100px;max-width:100%;height:100px;width:auto}
.word{margin-top:8px;font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px}
.pill{font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;color:#fff}
.pill.der{background:var(--der)}.pill.die{background:var(--die)}.pill.das{background:var(--das)}
.plural{color:#4b5563;font-size:12.5px}
.sentence{margin-top:6px;font-size:12.5px;color:#333}
.sentence span{display:block}
.sentence i{font-style:normal;color:#9aa1ab;font-size:11px;margin-right:4px}
.meta{margin-top:7px;font-size:11px;color:#9aa1ab;word-break:break-all}
.badge{display:inline-block;margin-top:5px;font-size:11px;background:#fdf2dd;color:#8a5a00;
  border:1px solid #e8a33d;border-radius:6px;padding:1px 6px}
.badge.other{background:#eef4fb;color:#25567f;border-color:#b9d3ea;margin-left:4px}
.dupes>ul{list-style:none;margin:10px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px}
.dupes li{display:flex;gap:10px;align-items:flex-start}
.dupes .mini{flex:0 0 44px;height:44px;display:flex;align-items:center;justify-content:center}
.dupes .mini svg{max-width:44px;max-height:44px;width:44px;height:44px}
.dupes small{color:#6b7280}
.worte{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-top:10px}
.worte ul{list-style:none;margin:10px 0 0;padding:0;columns:2;column-gap:28px}
.worte li{margin:0 0 3px;break-inside:avoid}
.worte b{font-weight:700}
.worte .themen{color:#6b7280}
"""


def load_decks(folder: Path) -> list[dict]:
    decks = []
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("entries"):
            decks.append((path.name, doc))
    return decks


def picture_usage(decks: list[dict]) -> dict[str, dict]:
    """Bildquelle -> verwendende Wörter - nur wenn wirklich *verschiedene* Wörter
    dieselbe Zeichnung nutzen. Dasselbe Wort in zwei Themen (Mond, Blume) ist
    unauffällig und soll die Liste nicht zumüllen."""
    groups: dict[str, dict] = {}
    for name, doc in decks:
        theme = doc.get("themeName", name)
        for entry in doc["entries"]:
            key = f"{theme}::{entry['word']}"
            source = str(entry.get("imageSource") or entry["word"])
            row = groups.setdefault(source, {"words": [], "svg": entry.get("imageSvg", "")})
            row["words"].append(key)
    return {k: v for k, v in groups.items()
            if len({w.split("::")[1].casefold() for w in v["words"]}) > 1}


def word_usage(decks: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """Wort (klein geschrieben) -> [(Thema, Schreibweise)]."""
    usage: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name, doc in decks:
        theme = doc.get("themeName", name)
        for entry in doc["entries"]:
            usage[entry["word"].casefold()].append((theme, entry["word"]))
    return dict(usage)


def card_html(entry: dict, dupe_with: list[str], auch_in: list[str]) -> str:
    article = str(entry.get("article", ""))
    plural = str(entry.get("plural", "")).strip()
    plural_text = f"die {plural}" if plural else "– keine Mehrzahl"
    badge = f'<div class="badge">Bild auch für {html.escape(", ".join(dupe_with))}</div>' if dupe_with else ""
    if auch_in:
        badge += f'<div class="badge other">auch in {html.escape(", ".join(auch_in))}</div>'
    return f"""      <div class="card{' dupe' if dupe_with else ''}">
        <div class="pic">{entry.get('imageSvg','')}</div>
        <div class="word">{html.escape(entry['word'])}<span class="pill {article}">{article}</span></div>
        <div class="plural">{html.escape(plural_text)}</div>
        <div class="sentence"><span><i>Akk.</i>{html.escape(str(entry.get('accusativeSentence','')))}</span>
          <span><i>Dat.</i>{html.escape(str(entry.get('dativeSentence','')))}</span></div>
        <div class="meta">{html.escape(entry.get('imageAuthor') or 'ohne Autor')} · {html.escape(entry.get('imageLicense') or '')}</div>
        {badge}
      </div>"""


def build(decks: list[dict], usage: dict[str, dict], worte: dict[str, list[tuple[str, str]]]) -> str:
    words = sum(len(doc["entries"]) for _, doc in decks)
    pictures = {str(e.get("imageSource") or e["word"]) for _, doc in decks for e in doc["entries"]}
    mehrfach = {k: v for k, v in worte.items() if len({t for t, _ in v}) > 1}
    paare: dict[tuple[str, str], int] = defaultdict(int)
    for eintraege in mehrfach.values():
        themen = sorted({t for t, _ in eintraege})
        for i in range(len(themen)):
            for j in range(i + 1, len(themen)):
                paare[(themen[i], themen[j])] += 1
    sections = []
    betroffen = 0
    for name, doc in decks:
        theme = doc.get("themeName", name)
        cards = []
        for entry in doc["entries"]:
            key = f"{theme}::{entry['word']}"
            source = str(entry.get("imageSource") or entry["word"])
            andere = sorted({w.split("::")[1] for w in usage.get(source, {}).get("words", []) if w != key})
            auch_in = sorted({t for t, _ in worte.get(entry["word"].casefold(), []) if t != theme})
            if andere:
                betroffen += 1
            cards.append(card_html(entry, andere, auch_in))
        sections.append(
            f"    <h2>{html.escape(theme)} <small>{len(doc['entries'])} Wörter · {name}</small></h2>\n"
            f'    <div class="grid">\n' + "\n".join(cards) + "\n    </div>"
        )
    gruppen = []
    for source, row in sorted(usage.items()):
        woerter = sorted({w.split("::")[1] for w in row["words"]})
        themen = sorted({w.split("::")[0] for w in row["words"]})
        gruppen.append(
            f'        <li><span class="mini">{row["svg"]}</span><span>'
            f'<b>{html.escape(" / ".join(woerter))}</b><br><small>{html.escape(", ".join(themen))}</small></span></li>'
        )
    dupes = (
        f'    <div class="dupes"><b>{len(usage)} Bilder zeigen zwei verschiedene Wörter</b> – dieselbe Zeichnung '
        f"für zwei Begriffe ist der häufigste Grund, warum eine Karte komisch wirkt:\n      <ul>\n"
        + "\n".join(gruppen) + "\n      </ul></div>"
        if usage else
        '    <div class="dupes"><b>Kein Bild wird für zwei verschiedene Wörter verwendet.</b></div>'
    )
    wortliste = "\n".join(
        f'        <li><b>{html.escape(v[0][1])}</b> <span class="themen">← {html.escape(" + ".join(t for t, _ in v))}</span></li>'
        for _, v in sorted(mehrfach.items(), key=lambda kv: (-len({t for t, _ in kv[1]}), kv[0]))
    )
    themenpaare = "\n".join(
        f"        <li>{html.escape(a)} ↔ {html.escape(b)}: <b>{n}</b> Wörter</li>"
        for (a, b), n in sorted(paare.items(), key=lambda kv: -kv[1]) if n >= 3
    )
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Wörter und Bilder – Übersicht</title>
<style>{STYLE}</style>
</head>
<body>
  <h1>Wörter und Bilder – Übersicht</h1>
  <div class="summary">
    <b>{len(decks)}</b> Themen · <b>{words}</b> Wörter · <b>{len(worte)}</b> verschiedene Wörter ·
    <b>{len(pictures)}</b> verschiedene Bilder ·
    <b>{betroffen}</b> Wörter teilen ihr Bild mit einem <i>anderen</i> Wort ·
    <b>{len(mehrfach)}</b> Wörter stehen in zwei Themen
  </div>
{dupes}
  <div class="worte"><b>Wörter in zwei Themen ({len(mehrfach)})</b> – das ist nicht falsch, aber einen Blick wert:
    <ul>
{wortliste}
    </ul></div>
  <div class="worte"><b>Themen mit vielen gemeinsamen Wörtern</b>
    <ul>
{themenpaare or '        <li>keine</li>'}
    </ul></div>
{chr(10).join(sections)}
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Übersicht aller Wörter und Bilder erzeugen")
    ap.add_argument("--themes", type=Path, default=ROOT / "selected-themes")
    ap.add_argument("--output", type=Path, default=ROOT / "output-selected" / "wortuebersicht.html")
    args = ap.parse_args()

    decks = load_decks(args.themes)
    if not decks:
        raise SystemExit(f"Keine Themes mit Einträgen in {args.themes}")
    usage = picture_usage(decks)
    worte = word_usage(decks)
    page = build(decks, usage, worte)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"{args.output} · {len(decks)} Themen · {sum(len(d['entries']) for _, d in decks)} Wörter "
          f"· {len(usage)} mehrfach verwendete Bilder · {args.output.stat().st_size / 1048576:.1f} MiB")


if __name__ == "__main__":
    main()
