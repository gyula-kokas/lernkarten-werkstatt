# Technik: Aufbau, Bau der Datei, Tests

Diese Datei ist für Menschen, die am Programm arbeiten. Für Benutzerführung siehe
[README.md](README.md); die **Regeln und Entscheidungen** des Projekts stehen in
[AGENTS.md](AGENTS.md) — die Datei ist bewusst knapp gehalten, wo AGENTS.md
ausführlich ist.

## Drei Schichten

```text
Editor-Backend      bilder_waehlen.py        stdlib-HTTP-Server auf 127.0.0.1:8765
Editor-Frontend     tools/image-picker.html  eine Datei, alle Aufrufe über api(path, data)
Lern-Ausgabe        der_die_das_template.html + Theme-JSON → eine HTML-Datei
```

Datenfluss:

```text
themes/*.json  →  [Editor: Bildwahl in image-library/selections.json]  →  selected-themes/*.json
                                                                              ↓ build_simple.py
                                                              output-selected/*.html (in sich geschlossen)
```

| Datei | Aufgabe |
|---|---|
| `bilder_waehlen.py` | Editor: Suche, Wörterbuch, Prüfung, Export, Bau anstoßen. Bewusst dicht und einzeilig geschrieben, deutsche Docstrings |
| `tools/image-picker.html` | Editor-Oberfläche (eine Datei, `__TOKEN__` wird beim Ausliefern ersetzt) |
| `der_die_das_template.html` | Lernansicht: Druck + Spiel, wird in die fertige Datei eingebettet |
| `build_simple.py` | **aktueller** Builder: rendert mit Piper, bettet Themen und Ton ein |
| `tools/tts_piper.py` | die eine Stimme und die ganze Audio-Kette |
| `tools/piper_worker.py` | läuft *im* Piper-venv, hält das Modell geladen |

`build.py` und `der_die_das.html` waren die früheren Fassungen und sind entfernt.

## Die eine Stimme

```text
Piper de_DE-thorsten-high (CC0 1.0, 22,05 kHz, LENGTH_SCALE 1.12)
  → Trimmen/Pegel normalisieren (tools/tts_piper.py)
  → MP3 48 kbit/s, 44,1 kHz (MPEG-1 Layer III, ffmpeg + libmp3lame)
```

- **Kein Fallback.** Fehlt Piper oder ffmpeg, startet der Editor nicht und der Bau
  bricht ab. Der Codec ist fest, weil die exportierte Datei überall laufen muss
  (MPEG-1 spielt auf Safari, iOS, Chromium, Firefox und Desktop-Playern).
- Die Ansage wird **aus Bausteinen zusammengesetzt**: `texts_for_entries()` erzeugt
  den festen Vorspann („Das Wort heißt“) **einmal** plus einen Clip je Wort. Das
  spart gegenüber einem Satz pro Wort rund 600 Clips.
- Ein Bau lädt das ONNX-Modell **einmal pro Worker** (`default_workers()`, env
  `DED_TTS_WORKERS`), nicht pro Clip. Fertige MP3s landen in `tts-cache/`.
- Stimme oder Sprechtempo zu ändern macht den ganzen Ton-Cache ungültig
  (`FORMAT_VERSION` in `tools/tts_piper.py` hochsetzen).

## Aufbau der fertigen Datei

`build_simple.py` ersetzt zwei Marker in der Vorlage (jeder genau **einmal**):

| Marker | Ort in der Datei | Inhalt |
|---|---|---|
| `/*__THEMES_JSON__*/ []` | im Hauptskript, in `const BUILTIN_THEMES = …` | Themes mit Bildern |
| `/*__EMBEDDED_TTS__*/ {"mode":"none"}` | `<script id="ttsData" type="application/json">` **am Ende des Body** | `audioByText` mit MP3-Daten-URLs |

**Der Ton bleibt immer am Dateiende.** Eine fertige Datei ist ~35 MB (10 MB Bilder,
26 MB MP3 als base64). Browser lesen eine `file://`-Datei sequenziell mit nur
wenigen MB/s; deshalb entscheidet die Lage der Bytes, wann man etwas sieht:

| Anordnung | Karten sichtbar | Ton fertig |
|---|---|---|
| Ton am Dateiende (jetzt) | **3,7 s** | 11,2 s |
| Ton vor den Themen | ~23 s | ~26 s |

`ladeTon()` (vom Nachlauf-Skript aufgerufen) füllt das veränderliche
`EMBEDDED_TTS`; die Statuszeile geht von `⏳ Ton wird geladen` auf
`🔊 Ton eingebaut`. `tests/smoke_test.py` (`check_vorlage_aufbau`) und der
CI-Templating-Schritt prüfen die Reihenfolge.

Nebenbei: Ein `<script type="application/json">` **statt** eines JS-Objektliterals
bringt hier nichts (gemessen: `JSON.parse` von 21,6 MB = 104 ms) — der Flaschenhals
ist der `file://`-Leser des Browsers, nicht das Format.

## Datenvertrag

Ein Theme hat `themeId` (projektweit eindeutig), `themeName`, `entries`; jeder
Eintrag hat `word`, `article` ∈ {`der`,`die`,`das`}, `plural`,
`accusativeSentence`, `dativeSentence` und nach dem Export `imageSvg`.

- Wörter sind je Thema eindeutig (groß/klein-unabhängig).
- **Massennomen** (Milch, Reis, Blut …) haben `plural: ""`. Die Liste liegt einmal
  in `tools/stoffnamen.py` und wird von `tools/build_decks.py`,
  `bilder_waehlen.audit_theme` und `tools/audit_words.py` benutzt — die drei müssen
  übereinstimmen.
- Editor-Metadaten (`editorType`, `imageSearch`, alles mit `editor*`/`_editor*`)
  werden beim Export entfernt und dürfen **nie** in die fertige Datei gelangen.
- Beispielsätze werden **von Hand** geschrieben (`tools/saetze/*.json`). Der
  Deck-Bau prüft, dass die Kasusform des jeweiligen Wortes wirklich vorkommt, der
  bestimmte Artikel benutzt wird und die Präpositionengruppe stimmt. Es gab einmal
  einen Satzgenerator — nicht wiedereinführen, der produzierte Unsinn wie
  „Das Kind trinkt die Erdbeere“.

## Decks bauen

```bash
python3 tools/build_decks.py --dry-run          # Plan gegen den Bildkatalog auflösen
python3 tools/build_decks.py --write            # schreibt themes/ + selected-themes/
python3 tools/build_decks.py --verworfen        # gestrichene Wörter protokollieren
```

- Der Plan steht in `tools/decks/*.json`: `[Wort, englischer Bildbegriff, Typ, Quelle]`;
  der Bildbegriff darf eine **Liste** sein (Hauptbegriff + Ausweichbegriffe).
- Höchstens **25 Wörter je Thema**, mindestens 15; ein Thema kann mit `"max": N`
  mehr bekommen (Körper).
- **Ein Bild gehört zu genau einem Wort** — projektweit.
- **Die Bildwahl aus der Werkstatt gewinnt.** `build_decks.py` liest
  `image-library/selections.json` zuerst; der Plan entscheidet nur über Wörter ohne
  Bildwahl. `--plan-bilder` setzt das absichtlich außer Kraft.
  `tests/smoke_test.py` (`check_werkstatt_bilder`) bricht ab, wenn ein Bau eine
  bestehende Bildwahl ändern würde.

Weitere Werkzeuge: `tools/audit_words.py` (Artikel/Mehrzahl aller Themen),
`tools/artikel_balance.py` (der/die/das-Verteilung je Bereich + Vorschläge aus
`themen-reserve/verworfen.md`), `tools/word_overview.py` (Kontrollblatt),
`tools/shrink_svg.py` (zu große Bilder).

## Wörterbuch

`dictionary/nouns.json` (119.744 Nomen, aus dem Kaikki/Wikitextract-Dump) ist
**nur für Autoren** und wird nie in die Lernkarten-Datei eingebettet. Es behält
alle Artikel- und Mehrzahlvarianten (`articles`/`plurals`) und die
Akkusativ-/Dativformen, weil deutsche Nomen mehrdeutig sind (`der/die Paprika`).

```bash
python3 tools/import_kaikki_dictionary.py --dump dictionary/raw-wiktextract-data.jsonl.gz
python3 tools/update_dictionary.py            # nur die Einzelabfrage nachschlagen
```

Der Dump selbst (289 MB) liegt nicht im Repository.

## Lernansicht (Vorlage)

`der_die_das_template.html` ist die Ansicht für Druck und Spiel. Mechanik, die man
nicht kaputtmachen darf:

- **Karten skalieren über `--karten-schrift` (Millimeter).** `setzeKartenSchrift()`
  rechnet die Grundschrift aus der gemessenen Zelle aus
  (`min(cellW/28.27, cellH/36.29)`). **Keine Container-Abfragen** (`cqw/cqh`):
  Firefox löst die im Druck falsch auf, dann kommen leere Karten heraus
  (Chrome druckt korrekt — der Fehler fiel lange nicht auf).
- **Beim Rasterwechsel werden Karten umgehängt, nicht neu gebaut** (`kartenPool`,
  `setzeZellen`, `bildPool`). Ein `innerHTML`-Neuaufbau aller Karten kostete über
  2 s. Die Mischung wird einmal gewürfelt (`mischListe`) und nur auf *Neu mischen*
  oder bei geänderter Themenauswahl neu gemischt.
- **Nur sichtbare Blätter werden gerechnet** (`.page{content-visibility:auto}`, im
  Druck `visible`). `passeKartenAn()` misst Blatt für Blatt, die sichtbaren sofort,
  den Rest in `requestIdleCallback`; `kartenFertig()` muss vor `window.print()`
  abgewartet werden.
- **Ein Wort = eine Karte.** 53 Wörter stehen in zwei Themen (692 Einträge, aber
  nur 639 verschiedene Wörter); `gemischteWoerter()` entdoppelt.
- **Rückmeldung** (✓/✗) sitzt als Plakette *neben* der Karte in der Zelle, damit
  sie in jedem Raster 11 px bleibt; im Druck gibt es sie nicht.
- Die Info-Box (`#about`) ist für Lernende, Eltern und Lehrer geschrieben — keine
  Bau-Interna.

## Tests und CI

```bash
python3 tests/smoke_test.py       # Audio (gemockt), Sätze, Wörterbuch, Audit, Export, Bildschutz, Vorlagenaufbau
python3 tools/audit_words.py      # Artikel und Mehrzahl aller Themen (0 Fehler / 0 Hinweise)
python3 -m py_compile bilder_waehlen.py build_simple.py tools/*.py
python3 tools/check_tts.py        # nur mit Piper + ffmpeg: echte Stimme
```

`.github/workflows/build.yml` macht dasselbe ohne Stimmmodell: der
Templating-Schritt mockt `probe`/`synthesize_many` und setzt die Vorlage mit
`selected-themes/` zusammen (nicht mit `themes/` — dort fehlen die Bilder, die
kommen erst beim Export dazu).

Ein grüner Testlauf beweist **nicht**, dass die echte Stimme funktioniert — dafür
ist `tools/check_tts.py` da.

Vorlagen-JS schnell prüfen:

```bash
python3 - <<'PY'
import re, pathlib
h = pathlib.Path("der_die_das_template.html").read_text(encoding="utf-8")
pathlib.Path("/tmp/vorlage.js").write_text(re.findall(r"<script[^>]*>(.*?)</script>", h, re.S)[0], encoding="utf-8")
PY
node --check /tmp/vorlage.js
```

## Verzeichnisse

```text
themes/                  Theme-Daten (Autorenstand, ohne Bilder)
selected-themes/         Build-Daten (mit Bildern) — hier baut build_simple.py
themen-reserve/          gestrichene Wörter, alte Bildzuordnungen
dictionary/              Wörterbuch nur für Autoren
image-library/           gewählte/hochgeladene Bilder + selections.json
tools/decks/             Themenplan, tools/saetze/ die Sätze
docs/bilder/             Bildschirmfotos für die README
tts-cache/               MP3-Cache (nicht im Repository)
vendor/piper/            Stimmmodell (nicht im Repository)
output-selected/         fertige HTML-Dateien (nicht im Repository)
```

## Repository und Veröffentlichen

Im Repository liegen die Quellen (rund 60 MB, größte Datei
`dictionary/nouns.json` mit 25 MB). `.gitignore` hält Stimmmodell (109 MB),
Wörterbuch-Dump (289 MB), `tts-cache/` und die gebauten Dateien draußen — GitHub
lehnt Dateien über 100 MB ab.

Eine neue Fassung veröffentlichen (Details: AGENTS.md, Abschnitt „Release“):

```bash
python3 tests/smoke_test.py
python3 build_simple.py --themes selected-themes --output output-selected/lernkarten-alle-themes.html
git tag vX.Y && git push origin vX.Y
gh release create vX.Y output-selected/lernkarten-alle-themes.html \
   --title "Lernkarten-Werkstatt X.Y" --notes-file /tmp/notes.md
```

Fehler beim Druck in Firefox? Siehe „Karten skalieren über `--karten-schrift`“ oben.
