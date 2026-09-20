# Beiträge zur Lernkarten-Werkstatt

Danke fürs Mitmachen! Dieses Projekt ist bewusst klein und ohne Abhängigkeiten:
**Python-Standardbibliothek**, eine feste Stimme, eine einzige Ausgabedatei.
Bitte diese Linie nicht aufweichen.

## Schnellstart

```bash
git clone https://github.com/gyula-kokas/lernkarten-werkstatt.git
cd lernkarten-werkstatt
python3 tests/smoke_test.py        # läuft ohne Piper und ffmpeg (TTS wird gemockt)
```

Für die **echte** Stimme zusätzlich einmalig einrichten (siehe README,
Abschnitt „Feste Aussprache“): Piper im eigenen venv, Modell nach
`vendor/piper/`, `ffmpeg` mit `libmp3lame`. Danach prüft
`python3 tools/check_tts.py` die ganze Kette.

Der Editor startet mit:

```bash
python3 bilder_waehlen.py          # http://127.0.0.1:8765/
```

## Vor dem Pull Request

```bash
python3 tests/smoke_test.py
python3 tools/audit_words.py
python3 -m py_compile bilder_waehlen.py build_simple.py tools/*.py
```

Alle drei müssen grün sein. Die CI (`.github/workflows/build.yml`) prüft
dieselben Punkte; der Templating-Schritt läuft dort **ohne** Stimmmodell,
damit der Build auch ohne Piper nachvollziehbar bleibt.

## Regeln, die nicht verhandelbar sind

- **Genau eine TTS-Kette.** Piper `de_DE-thorsten-high` → MP3 48 kbit/s
  (MPEG-1 Layer III). Kein Browser-, System- oder Zweitstimmen-Fallback.
  Fehlt Piper oder `ffmpeg`, bricht der Build ab — das ist Absicht.
- **Beispielsätze werden von Hand geschrieben** (`tools/saetze/*.json`).
  Keine Satzgeneratoren, keine Vorlagenpools, kein Round-Robin.
- **Bilder in der Werkstatt gewinnen.** Wer ein Bild im Editor auswählt, darf
  es nicht durch einen Deck-Neubau verlieren; `python3 tools/build_decks.py --write`
  behält solche Bilder (Test: `check_werkstatt_bilder()`).
- **Ein Bild gehört zu genau einem Wort** (projektweit), maximal 25 Wörter je
  Theme, mindestens 15.
- **2.592 Audioclips sind die Obergrenze des Zumutbaren** — die Ansage wird aus
  zwei Bausteinen zusammengesetzt, nicht pro Wort neu gesprochen. Gemessen wird
  ein Prompt nicht neu, sondern wiederverwendet.
- **Deutsch für Lernende, Englisch im Code.** Benutzertexte, Fehlermeldungen und
  Dokumentation sind deutsch, Bezeichner englisch (Ausnahme: `bilder_waehlen.py`
  ist bewusst deutsch und dicht geschrieben).
- **Stil der Datei beibehalten.** `bilder_waehlen.py` ist absichtlich kompakt,
  `build_simple.py` und `tools/*.py` sind PEP 8 mit Typangaben.
- **Die fertige HTML-Datei bleibt eine Datei.** Bilder, Theme-Daten und Töne
  werden eingebettet; kein Nachladen aus dem Netz.

## Wenn du eine Karte oder den Ausdruck änderst

`der_die_das_template.html` ist die Lernansicht (Drucken + Spielen). Zwei Dinge
sind dort leicht kaputtzumachen:

1. **Die Diagrammreihenfolge:** Bild · Wort · Antwortblasen · Satz. Der Satz
   steht immer **unter** der der/die/das-Auswahl.
2. **Der Rasterwechsel.** Karten werden beim Umstellen **umgehängt**, nicht neu
   gebaut (`kartenPool`/`setzeZellen`). Wer hier `innerHTML` zurückbaut, macht
   den Rasterwechsel wieder sekundenlang blockierend.

Nach Änderungen an der Vorlage lohnt der kurze Syntaxblick:

```bash
python3 - <<'PY'
import re, pathlib
h = pathlib.Path("der_die_das_template.html").read_text(encoding="utf-8")
pathlib.Path("/tmp/vorlage.js").write_text(re.findall(r"<script[^>]*>(.*?)</script>", h, re.S)[0], encoding="utf-8")
PY
node --check /tmp/vorlage.js
```

## Größere Dinge

Für neue Werkzeuge, Datenformate oder Umbauten bitte **erst ein Issue** —
`AGENTS.md` beschreibt, welche Entscheidungen dahinterstecken, und viele
offensichtliche Vereinfachungen wurden schon einmal probiert und verworfen.

## Lizenz

Mit einem Beitrag stimmst du zu, dass er unter der **GPL-3.0** steht
(siehe [LICENSE](LICENSE)).
