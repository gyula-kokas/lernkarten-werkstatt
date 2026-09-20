#!/usr/bin/env python3
"""Bau die Lerndecks aus dem Plan - Bild zuerst, Wort danach.

Ein Wort kommt nur in ein Deck, wenn

* das Offline-Wörterbuch Artikel und Mehrzahl kennt und
* der Bildkatalog ein Bild dazu hat und
* dieses Bild noch **kein anderes Wort** zeigt (projektweit, nicht nur im Deck) und
* in ``tools/saetze/*.json`` ein **geschriebener** Akkusativ- und Dativsatz steht.

Jedes Bild gehört also genau einem Wort. Dasselbe Wort in zwei Themen behält
sein Bild; hat ein anderes Thema das Bild schon, greift ein Ausweichbild aus dem
Plan (``[Hauptbegriff, Ausweichbegriff, …]``) – sonst fällt das Wort weg.

**Die Bildwahl der Werkstatt steht über dem Plan.** Was in
``image-library/selections.json`` steht (jede Wahl aus ``bilder_waehlen.py``),
bleibt beim Bauen unangetastet; der Plan entscheidet nur über Wörter, die noch
kein Bild haben. Sonst würde ein Bau die von Hand ausgesuchten Zeichnungen
(ClipSafari statt Emoji) wieder durch den Katalogtreffer ersetzen. Mit
``--plan-bilder`` wird diese Regel bewusst außer Kraft gesetzt.

Es gibt keinen Satzbaukasten mehr: jeder Satz ist einzeln geschrieben und wird
streng geprüft (Kasusform aus dem Wörterbuch, kein Fragezeichen, Präposition und
Kasus passend). Fehlt ein Satz, wird das Wort übersprungen und gemeldet.
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bilder_waehlen as editor  # noqa: E402
import image_providers  # noqa: E402
from stoffnamen import STOFFNAMEN  # noqa: E402

MAX_WOERTER = 25
MIN_WOERTER = 15

# Bei mehrdeutigen Nomen führt das Wörterbuch zuerst eine andere Bedeutung
# ("der Butter" = schweizerisch, "der Radio" = umgangssprachlich, "der Leiter" =
# die Person). Für die Lernkarten gilt der übliche Artikel, sonst stünde der
# falsche Artikel als Lösung auf der Karte.
ARTIKEL_UEBLICH = {
    "butter": "die", "radio": "das", "taxi": "das", "baguette": "das",
    "trikot": "das", "bonbon": "das", "zwiebel": "die", "kiwi": "die",
    "leiter": "die", "frisbee": "der",
    # Das Kaikki-Dump führt zu vielen Wörtern regionale/veraltete Varianten mit
    # ("Thermometer: der/das"). Hier stehen die Fälle, in denen die *übliche*
    # Form nicht die erste im Wörterbuch ist - Duden kennt nur "das Thermometer".
    "thermometer": "das",
}

# Nur-Dativ- und Nur-Akkusativ-Präpositionen: damit der Kasus im Satz sicher zum
# Artikel passt. Wechselpräpositionen (in, an, auf, über, unter, vor, ...) sind
# erlaubt, werden aber zur Kontrolle gemeldet.
DAT_PREPOSITIONS = ("mit", "bei", "nach", "von", "zu", "aus", "seit", "gegenüber")
AKK_PREPOSITIONS = ("für", "durch", "gegen", "ohne", "um")
WECHSEL_PREPOSITIONS = ("in", "an", "auf", "über", "unter", "vor", "hinter", "neben", "zwischen")

def load_sentences(folder: Path) -> dict[str, dict[str, list[str]]]:
    """Geschriebene Sätze aus tools/saetze/*.json: {thema: {wort: [akk, dat]}}."""
    saetze: dict[str, dict[str, list[str]]] = {}
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for theme, rows in doc.items():
            if theme.startswith("_"):
                continue
            saetze.setdefault(theme, {}).update({str(k): list(v) for k, v in rows.items()})
    return saetze


def required_phrase(entry: dict, kind: str, word: str) -> str:
    """Die Form, die im Satz stehen muss: "den Bären", "der Katze", "dem Haus"."""
    forms = entry.get("accusative" if kind == "acc" else "dative") or []
    inflected = forms[0] if forms else word
    return f"{editor.CASE_FORMS[kind][entry['article']]} {inflected}"


def check_sentence(text: str, entry: dict, kind: str, word: str) -> str:
    """Leere Zeichenkette heißt in Ordnung, sonst die Begründung."""
    text = str(text or "").strip()
    if not text:
        return "Satz fehlt"
    if "?" in text:
        return "Fragezeichen im Satz"
    if not editor.sentence_has_case(text, entry["article"], kind, word):
        return "Kasusform fehlt"
    phrase = required_phrase(entry, kind, word)
    if phrase not in text:
        forms = entry.get("accusative" if kind == "acc" else "dative") or []
        tolerant = [f"{editor.CASE_FORMS[kind][entry['article']]} {form}" for form in forms]
        # Das Dativ-e ist veraltet, aber richtig ("dem Sonnenaufgange").
        tolerant.append(f"{editor.CASE_FORMS[kind][entry['article']]} {word}")
        if not any(form in text for form in tolerant):
            return f'"{phrase}" fehlt'
    # Nur echte Präpositionsgruppen prüfen: trennbare Verben wie "hält das Ohr zu"
    # oder "drückt den Schwamm aus" sind kein Kasusfehler.
    gruppe = lambda praep: re.search(
        r"\b(?:" + "|".join(praep) + r")\s+(?:dem|der|den|einem|einer|einen)\b", text, re.I)
    if kind == "acc" and gruppe(DAT_PREPOSITIONS):
        return "Dativpräposition im Akkusativsatz"
    if kind == "dat" and gruppe(AKK_PREPOSITIONS):
        return "Akkusativpräposition im Dativsatz"
    return ""


def wechsel_hinweis(text: str) -> str:
    """Wechselpräpositionen sind richtig, aber einen Blick wert."""
    woerter = set(re.findall(r"[a-zA-ZäöüßÄÖÜ]+", str(text).casefold()))
    return ", ".join(p for p in WECHSEL_PREPOSITIONS if p in woerter)


def load_plan(folder: Path) -> list[dict]:
    themes: list[dict] = []
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for theme in doc.get("themes") or []:
            theme["_file"] = path.name
            themes.append(theme)
    return themes


def catalog_images(query: str, allow_tags: bool) -> list[str]:
    """Passende Bildcodes zum englischen Begriff, bester Treffer zuerst."""
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    if not tokens:
        return []
    ranked: list[tuple[int, str]] = []
    for row in image_providers.catalog()["items"]:
        title = str(row["title"]).lower()
        title_words = set(re.findall(r"[a-z0-9]+", title))
        all_words = title_words | set(re.findall(r"[a-z0-9]+", str(row["tags"]).lower()))
        if not all(token in all_words for token in tokens):
            continue
        if title.strip() == query.lower().strip():
            rank = 0
        elif all(token in title_words for token in tokens):
            rank = 1
        else:
            if not allow_tags:
                continue
            rank = 2
        ranked.append((rank, str(row["code"])))
    ranked.sort()
    return [code for _, code in ranked]


def slug_for(code: str) -> str:
    """Bildcode aus dem Katalog -> Dateiname in ``image-library/``."""
    return f"openmoji--{code}"


@functools.lru_cache(maxsize=1)
def twemoji_von_code() -> dict[str, str]:
    """OpenMoji-Code -> Twemoji-Kennung (zweite Zeichnung desselben Motivs)."""
    return {str(row["code"]): str(row["twemoji"]) for row in image_providers.catalog()["items"]
            if row.get("twemoji")}


def mdi_passt(name: str, query: str) -> bool:
    """Alle Suchwörter müssen als ganze Wörter im Icon-Namen stehen."""
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    if not tokens:
        return False
    words = set(re.findall(r"[a-z0-9]+", name.lower()))
    return all(token in words for token in tokens)


def bild_kandidaten(queries: list[str], provider: str, allow_tags: bool) -> list[tuple[str, str]]:
    """Bildkandidaten als ``(slug, Suchbegriff)``, bester Treffer zuerst.

    Standard ist OpenMoji. Für dasselbe Emoji gibt es Twemoji als **zweite
    Zeichnung** – sie steht direkt hinter ihrem OpenMoji-Bild und wird genommen,
    wenn das OpenMoji-Bild schon ein anderes Wort zeigt. Mit ``provider='mdi'``
    kommen Objekt-Icons aus Material Design statt Emoji-Bilder.
    """
    gesehen: list[str] = []
    out: list[tuple[str, str]] = []
    if provider == "clipsafari":
        # Der Suchbegriff ist hier die Clipsafari-Kennung, z. B. "o133477-cartoon-knight"
        # oder ein daraus abgeleitetes eigenes Bild in image-library/.
        return [(query, query) for query in queries]
    for query in queries:
        if provider == "mdi":
            for row in image_providers.mdi_catalog()["items"]:
                if not mdi_passt(str(row["name"]), query):
                    continue
                slug = f"mdi--{row['name']}"
                if slug not in gesehen:
                    gesehen.append(slug)
                    out.append((slug, query))
            continue
        for code in catalog_images(query, allow_tags):
            zweit = twemoji_von_code().get(code)
            wunsch = ([f"twemoji--{zweit}", f"openmoji--{code}"] if provider == "twemoji" and zweit
                      else [f"openmoji--{code}"] + ([f"twemoji--{zweit}"] if zweit else []))
            for slug in wunsch:
                if slug not in gesehen:
                    gesehen.append(slug)
                    out.append((slug, query))
    return out


def bild_datei(slug: str) -> Path:
    """Bilddatei zu einem Slug in ``image-library/``."""
    return ROOT / "image-library" / f"{slug}.json"


def werkstatt_bilder() -> dict[tuple[str, str], dict]:
    """Bildwahl aus der Werkstatt: ``(Themen-Kennung, Wort) -> {"slug", "query"}``.

    Die Werkstatt (``bilder_waehlen.py``) merkt sich jede Bildwahl in
    ``image-library/selections.json`` unter ``<themedatei>::<Wort>``. Diese Wahl
    ist maßgeblich: der Plan entscheidet nur über Wörter, die noch kein Bild
    haben. Sonst würde ein Deck-Bau die von Hand gewählten Zeichnungen
    (z. B. ClipSafari statt Emoji) wieder durch den Katalogtreffer ersetzen.
    """
    pfad = ROOT / "image-library" / "selections.json"
    if not pfad.exists():
        return {}
    try:
        auswahl = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(auswahl, dict):
        return {}

    # Themendatei (theme-66-gesundheit.json) -> Plan-Kennung (gesundheit)
    kennung_je_datei: dict[str, str] = {}
    for datei in sorted((ROOT / "themes").glob("*.json")):
        try:
            doc = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        kennung_je_datei[datei.name] = str(doc.get("themeId") or datei.stem).split("-", 2)[-1]

    out: dict[tuple[str, str], dict] = {}
    for key, wahl in auswahl.items():
        datei, trenner, wort = str(key).partition("::")
        kennung = kennung_je_datei.get(datei)
        if trenner and kennung and wort.strip():
            out[(kennung, wort.strip().casefold())] = wahl if isinstance(wahl, dict) else {}
    return out


def build(folder: Path, dictionary: dict, sentences: dict, allow_tags: bool,
          belegt: dict[str, tuple[str, str]] | None = None,
          vorhanden: dict[tuple[str, str], dict] | None = None) -> tuple[list[dict], list[str]]:
    """Decks aus Plan, Wörterbuch, Bildern und Sätzen bauen.

    Ein Bild darf **projektweit** nur ein Wort zeigen: ``belegt`` hält fest,
    welches Wort (in welchem Thema) ein Bild schon hat. Dasselbe Wort in zwei
    Themen behält sein Bild - zwei verschiedene Wörter nie.

    ``vorhanden`` ist die Bildwahl aus der Werkstatt (``werkstatt_bilder()``).
    Sie gewinnt gegen den Plan: nur Wörter ohne eigene Bildwahl bekommen ein
    neues Bild aus dem Katalog.
    """
    plans: list[dict] = []
    notes: list[str] = []
    if belegt is None:
        belegt = {}
    if vorhanden is None:
        vorhanden = {}
    for theme in load_plan(folder):
        entries: list[dict] = []
        skipped: list[str] = []
        seen: set[str] = set()
        for position, pair in enumerate(theme.get("words") or []):
            word = str(pair[0]).strip()
            # Der Bildbegriff darf eine Liste sein: der erste Treffer ist das
            # Hauptbild, die weiteren sind Ausweichbilder, falls das Hauptbild
            # schon ein anderes Wort belegt.
            roh = pair[1] if len(pair) > 1 else ""
            queries = [str(x).strip() for x in (roh if isinstance(roh, list) else [roh]) if str(x).strip()]
            # Drittes Element im Plan ist eine Ausnahme für den Satzbau
            # (z. B. "Ampel" im Fahrzeug-Thema ist ein Ort, kein Fahrzeug).
            kind_type = str(pair[2]) if len(pair) > 2 and pair[2] else str(theme.get("type", "object"))
            # Viertes Element im Plan wählt die Bildquelle: "mdi" für Objekt-
            # Icons aus Material Design, "twemoji" für die zweite Emoji-Zeichnung.
            bild_quelle = str(pair[3]).strip().lower() if len(pair) > 3 and pair[3] else "openmoji"
            if word.casefold() in seen:
                skipped.append(f"{word} (doppelt im Thema)")
                continue
            seen.add(word.casefold())
            entry = dictionary.get(word.casefold())
            if entry is None:
                skipped.append(f"{word} (kein Wörterbuch-Eintrag)")
                continue
            article = ARTIKEL_UEBLICH.get(word.casefold()) or entry.get("article") or ""
            entry = dict(entry, article=article)
            if article not in editor.CASE_FORMS["acc"]:
                skipped.append(f"{word} (kein Artikel)")
                continue
            gefunden = bild_kandidaten(queries, bild_quelle, allow_tags)
            frei = [(slug, query) for slug, query in gefunden
                    if slug not in belegt or belegt[slug][0] == word.casefold()]
            # Die Bildwahl der Werkstatt steht über dem Plan. Sie wird nur
            # verworfen, wenn die Bilddatei fehlt oder das Bild inzwischen ein
            # anderes Wort zeigt.
            wahl = vorhanden.get((str(theme.get("id") or ""), word.casefold())) or {}
            gewaehlt = str(wahl.get("slug") or "")
            gehalten = bool(gewaehlt) and bild_datei(gewaehlt).exists() and (
                gewaehlt not in belegt or belegt[gewaehlt][0] == word.casefold())
            if not frei and not gehalten:
                belegung = "; ".join(
                    f"{belegt[slug][1]} hat „{belegt[slug][0]}“ schon" for slug, _ in gefunden if slug in belegt
                )
                skipped.append(f"{word} ({', '.join(queries) or 'ohne Bildbegriff'}: kein eigenes Bild – {belegung})")
                continue
            if gehalten:
                bild_slug, query = gewaehlt, str(wahl.get("query") or "")
            else:
                bild_slug, query = frei[0]
            # Stoffnamen (Milch, Reis, Blut) haben keine Mehrzahl.
            if word.casefold() in STOFFNAMEN:
                plural = ""
            else:
                plural = ", ".join(entry.get("plurals") or [])[:60].split(",")[0].strip()

            # Geschriebene Sätze: ohne sie kommt das Wort nicht ins Deck.
            paar = (sentences.get(theme["id"]) or {}).get(word)
            if not paar or len(paar) < 2:
                skipped.append(f"{word} (kein geschriebener Satz)")
                continue
            acc, dat = str(paar[0]), str(paar[1])
            problem = check_sentence(acc, entry, "acc", word) or check_sentence(dat, entry, "dat", word)
            if problem:
                skipped.append(f"{word} ({problem})")
                continue
            belegt[bild_slug] = (word.casefold(), theme["name"])
            entries.append({
                "word": word,
                "article": article,
                "plural": plural,
                "pluralWithArticle": f"die {plural}" if plural else "",
                "accusativeSentence": acc,
                "dativeSentence": dat,
                "imageIndex": len(entries),
                "editorType": kind_type,
                "_slug": bild_slug,
                "_query": query,
                # Nur zur Kontrolle: Werkstatt-Bild behalten, und was der Plan
                # heute stattdessen vorgeschlagen hätte.
                "_behalten": gehalten,
                "_plan_slug": frei[0][0] if frei else "",
            })
            if len(entries) >= int(theme.get("max") or MAX_WOERTER):
                skipped.extend(f"{str(rest[0])} (Deck voll)" for rest in theme["words"][position + 1:])
                break
        if len(entries) < MIN_WOERTER:
            notes.append(f"{theme['name']}: nur {len(entries)} Wörter mit eigenem Bild – Thema wird übersprungen")
            continue
        plans.append({"theme": theme, "entries": entries, "skipped": skipped})
    return plans, notes


def write_decks(plans: list[dict], first_id: int) -> None:
    selections = editor.selections()
    for number, plan in enumerate(plans):
        theme = plan["theme"]
        theme_id = f"theme-{first_id + number}-{theme['id']}"
        file_name = f"{theme_id}.json"

        # Erst die Bilder holen: ein Bild, das die Prüfung nicht übersteht, lässt
        # sein Wort fallen statt den ganzen Bau abzubrechen.
        entries: list[dict] = []
        for entry in plan["entries"]:
            slug = entry["_slug"]
            if not bild_datei(slug).exists():
                try:
                    editor.download(slug)
                except Exception as exc:  # noqa: BLE001 - jede Bildpanne überspringt nur das Wort
                    plan["skipped"].append(f"{entry['word']} (Bild nicht verwendbar: {exc})")
                    continue
            # Die Bildwahl der Werkstatt bleibt samt Suchbegriff unverändert -
            # nur neue Bilder werden eingetragen.
            if not entry.get("_behalten"):
                selections[f"{file_name}::{entry['word']}"] = {"slug": slug, "query": entry["_query"]}
            entries.append(entry)

        if len(entries) < MIN_WOERTER:
            print(f"  {file_name:38s} nur {len(entries)} Bilder nutzbar – übersprungen")
            continue
        doc = {
            "themeId": theme_id,
            "themeName": theme["name"],
            "language": "de",
            "version": 1,
            "entryCount": len(entries),
            "imageMode": "per-entry-svg",
            "entries": [
                dict((k, v) for k, v in e.items() if not k.startswith("_"))
                for e in entries
            ],
        }
        for position, entry in enumerate(doc["entries"]):
            entry["imageIndex"] = position
        editor.atomic(ROOT / "themes" / file_name, doc)
        editor.atomic(ROOT / "image-library" / "selections.json", selections)
        editor.export_theme(file_name)
        print(f"  {file_name:38s} {len(doc['entries']):3d} Wörter · Bild exportiert")

    # Bildzuordnungen gestrichener Wörter entfernen: sonst meldet die
    # Qualitätsprüfung Bilder als vergeben, die kein Deck mehr verwendet.
    aktuell = {
        f"theme-{first_id + number}-{plan['theme']['id']}.json::{entry['word']}"
        for number, plan in enumerate(plans)
        for entry in plan["entries"]
        if (ROOT / "image-library" / f"{entry['_slug']}.json").exists()
    }
    verwaist = {k: v for k, v in selections.items() if k not in aktuell}
    if verwaist:
        sauber = {k: v for k, v in selections.items() if k in aktuell}
        editor.atomic(ROOT / "image-library" / "selections.json", sauber)
        print(f"  Bildzuordnungen aufgeräumt: {len(sauber)} behalten · {len(verwaist)} verwaist")


def write_dropped_words(plans: list[dict], notes: list[str], path: Path) -> None:
    """Liste der gestrichenen Wörter schreiben (für themen-reserve/verworfen.md)."""
    grund_map = (
        ("kein Wörterbuch-Eintrag", "nicht im Wörterbuch"),
        ("kein geschriebener Satz", "kein Satz geschrieben"),
        ("Deck voll", "über 25 Wörter"),
        ("doppelt im Thema", "doppelt im Thema"),
    )
    zeilen = [
        "# Gestrichene Wörter", "",
        "Kein Wort ist verloren: hier stehen alle Begriffe, die es nicht in ein Deck",
        "geschafft haben. Ein Bild darf projektweit nur ein Wort zeigen – hat ein anderes",
        "Thema das Bild schon, braucht das Wort ein eigenes Bild.", "",
    ]
    for plan in plans:
        woerter = []
        for eintrag in plan["skipped"]:
            if "(" not in eintrag:
                continue
            wort, rest = eintrag.split(" (", 1)
            grund = rest.rsplit(")", 1)[0]
            # "kein eigenes Bild – Thema hat „X“ schon" bleibt im Klartext stehen,
            # damit man sieht, wer das Bild belegt.
            for schluessel, text in grund_map:
                if schluessel in grund:
                    grund = text
                    break
            grund = re.sub(r"^[a-z ,]*(?=kein eigenes Bild)", "", grund).strip()
            if grund in ("über 25 Wörter", "doppelt im Thema"):
                continue
            woerter.append(f"`{wort.strip()}` ({grund})")
        if not woerter:
            continue
        zeilen.append(f"### {plan['theme']['name']} – {len(plan['entries'])} Wörter im Deck, {len(woerter)} gestrichen")
        zeilen.append("")
        zeilen += textwrap.wrap(", ".join(woerter), 96)
        zeilen.append("")
    if notes:
        zeilen += ["## Themen, die ganz entfallen", ""] + [f"- {note}" for note in notes] + [""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    print(f"  Streichliste geschrieben: {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Decks aus Plan, Bildkatalog und Sätzen bauen")
    ap.add_argument("--plan", type=Path, default=ROOT / "tools" / "decks", help="Ordner mit Plan-Dateien")
    ap.add_argument("--saetze", type=Path, default=ROOT / "tools" / "saetze", help="Ordner mit geschriebenen Sätzen")
    ap.add_argument("--write", action="store_true", help="Themen schreiben, Bilder laden, exportieren")
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen und anzeigen")
    ap.add_argument("--first-id", type=int, default=50, help="erste Themennummer (theme-50-…)")
    ap.add_argument("--verworfen", type=Path, default=ROOT / "themen-reserve" / "verworfen.md",
                    help="Datei für die Liste der gestrichenen Wörter")
    ap.add_argument("--allow-tags", action="store_true", help="auch Bilder über Stichwörter zulassen (ungenauer)")
    ap.add_argument("--plan-bilder", action="store_true",
                    help="Bildwahl der Werkstatt ignorieren und alle Bilder neu aus dem Plan lösen")
    args = ap.parse_args()

    dictionary = json.loads((ROOT / "dictionary" / "nouns.json").read_text(encoding="utf-8"))
    sentences = load_sentences(args.saetze)
    vorhanden = {} if args.plan_bilder else werkstatt_bilder()
    plans, notes = build(args.plan, dictionary, sentences, args.allow_tags, vorhanden=vorhanden)

    print(f"Geplante Themen: {len(load_plan(args.plan))} · gebaut: {len(plans)}")
    print()
    for plan in plans:
        theme = plan["theme"]
        words = ", ".join(e["word"] for e in plan["entries"])
        print(f"{theme['name']} ({len(plan['entries'])} Wörter)")
        print(f"   {words}")
        for note in plan["skipped"][:6]:
            print(f"   – {note}")
        if len(plan["skipped"]) > 6:
            print(f"   – … {len(plan['skipped']) - 6} weitere")
    if notes:
        print()
        print("Übersprungen:")
        for note in notes:
            print("  -", note)

    words_total = sum(len(p["entries"]) for p in plans)
    bilder: dict[str, set[str]] = {}
    for plan in plans:
        for entry in plan["entries"]:
            bilder.setdefault(entry["_slug"], set()).add(entry["word"].casefold())
    kollisionen = {slug: woerter for slug, woerter in bilder.items() if len(woerter) > 1}
    print()
    print(f"Wörter mit eigenem Bild: {words_total} · verschiedene Bilder: {len(bilder)}")
    if kollisionen:
        print(f"  Achtung: {len(kollisionen)} Bilder zeigen zwei verschiedene Wörter:")
        for slug, woerter in sorted(kollisionen.items()):
            print(f"    {slug}: {', '.join(sorted(woerter))}")

    alle = [e for plan in plans for e in plan["entries"]]
    gehalten = [e for e in alle if e.get("_behalten")]
    neu_vergeben = [e for e in alle if not e.get("_behalten")]
    print(f"Bilder aus der Werkstatt beibehalten: {len(gehalten)} · neu aus dem Plan: {len(neu_vergeben)}")
    abweichend = [e for e in gehalten if e.get("_plan_slug") and e["_plan_slug"] != e["_slug"]]
    if abweichend:
        print(f"  Bei {len(abweichend)} davon hätte der Plan heute ein anderes Bild gewählt (Werkstatt gewinnt):")
        for e in abweichend[:12]:
            print(f"    {e['word']}: Werkstatt {e['_slug']} · Plan {e['_plan_slug']}")
        if len(abweichend) > 12:
            print(f"    … {len(abweichend) - 12} weitere")
    if args.plan_bilder and gehalten:
        print("  (--plan-bilder: die Werkstatt-Wahl wurde bewusst ignoriert)")

    if not args.write:
        write_dropped_words(plans, notes, args.verworfen)
        print("\nProbelauf – nichts geschrieben.")
        return
    print()
    write_decks(plans, args.first_id)
    # Erst nach dem Schreiben: jetzt stehen auch Bildpannen in plan["skipped"].
    write_dropped_words(plans, notes, args.verworfen)
    print("FERTIG")


if __name__ == "__main__":
    main()
