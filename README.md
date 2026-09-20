# DER · DIE · DAS – Lernkarten-Werkstatt 0.4

[![Build und Tests](https://github.com/gyula-kokas/lernkarten-werkstatt/actions/workflows/build.yml/badge.svg)](https://github.com/gyula-kokas/lernkarten-werkstatt/actions/workflows/build.yml)
[![Lizenz: GPL-3.0](https://img.shields.io/badge/Lizenz-GPL--3.0-blue.svg)](LICENSE)

Lokaler visueller Editor für deutsche Lernkarten. Der Editor besteht aus mehreren
Dateien; **das Ergebnis für Lernende ist immer genau eine HTML-Datei**.

## Feste Aussprache

Die TTS-Kette ist eine Projektentscheidung und kein optionales Plugin:

```text
Piper (de_DE-thorsten-high, CC0 1.0) → MP3 48 kbit/s · 44,1 kHz (MPEG-1 Layer III)
```

Es gibt keinen Browser-, System- oder anderen Audio-Fallback. Wenn Piper oder
`ffmpeg` fehlt, startet die Werkstatt nicht und der Build wird abgebrochen. Beim
Export werden alle tatsächlich verwendeten Wörter und Sätze vorgerendert und als
MP3 direkt in die einzelne HTML-Datei eingebettet.

Zwei Details sparen dabei Arbeit und Dateigröße:

- Die Ansage wird im Lernprogramm aus zwei Bausteinen zusammengesetzt — der feste
  Vorspann („Das Wort heißt“) wird **einmal** gesprochen, danach folgt der Wortclip.
  Der zweite Prompt („Hör noch einmal“) nutzt dieselben Bausteine.
- Der Build spricht mehrere Clips gleichzeitig: vier Piper-Prozesse mit je zwei
  Threads teilen sich die CPU (`DED_TTS_WORKERS` überschreibt die Zahl).

Einmalige Einrichtung (nur dieser Schritt braucht Internet):

```bash
python3 -m venv ~/.local/share/ded-tts/venv
~/.local/share/ded-tts/venv/bin/pip install piper-tts
~/.local/share/ded-tts/venv/bin/python -m piper.download_voices \
    de_DE-thorsten-high --download-dir vendor/piper
sudo apt install ffmpeg
```

Schnelltest der kompletten Kette:

```bash
python3 tools/check_tts.py
```

## Start

```bash
python3 bilder_waehlen.py
```

Danach öffnet sich normalerweise:

```text
http://127.0.0.1:8765/
```

## Was 0.4 kann

- Themes visuell anlegen und bearbeiten
- neue Nomen zuerst gegen das deutsche Wörterbuch prüfen
- Artikel und Mehrzahl automatisch aus dem Wörterbuch übernehmen
- unbekannte Wörter nur nach ausdrücklicher manueller Bestätigung anlegen
- groben semantischen Typ nur für den Editor bestimmen
- 5 wechselnde Akkusativ- und Dativsatz-Vorschläge ohne KI erzeugen
- Sätze frei bearbeiten und sofort mit der **Piper-Stimme** anhören
- Arbeitsblätter wahlweise nach der Artikel-Grundform oder nach der Kasusform fragen
- Spielmodus mit drei Aufgabentypen: **Artikel**, **Kasus** und **Mehrzahl** (auch gemischt)
- Bilder aus OpenMoji, Twemoji und ClipSafari suchen
- eigene PNG/JPEG/WebP/SVG-Dateien per Dateiauswahl oder Drag & Drop verwenden
- Theme-Qualität prüfen: Bilder, Artikel, Plural, Sätze, Duplikate und
  Wörterbuch-Abweichungen
- Artikel und Mehrzahl aller Themen gegen das Offline-Wörterbuch prüfen
  (`tools/audit_words.py`)
- einzelnes Theme oder alle Themes bauen
- alle Themes gemeinsam in **eine einzige Offline-HTML** exportieren

Editor-Hilfsdaten wie `editorType`, Wörterbuch und Wikidata-Ergebnisse werden
nicht in die Lernkarten-HTML exportiert.

## Themen

Die Decks werden **bildgesteuert** gebaut: erst das Bild, dann das Wort.

1. Jedes Thema hat im Plan (`tools/decks/*.json`) eine Wunschliste aus Wort und
   englischem Bildbegriff, sortiert nach Wichtigkeit. Der Begriff darf eine Liste
   sein: `["Hauptbegriff", "Ausweichbegriff", …]`. Ein viertes Element wählt die
   Bildquelle: `"mdi"` (Material Design Icons für Objekte ohne Emoji),
   `"twemoji"` (zweite Emoji-Zeichnung) oder `"clipsafari"` (feste Kennung).
2. Der Bauer (`tools/build_decks.py`) nimmt ein Wort nur auf, wenn
   * das Offline-Wörterbuch Artikel und Mehrzahl kennt,
   * eine Bildquelle ein Bild dazu hat und
   * dieses Bild **projektweit** noch kein anderes Wort zeigt.
3. Ist das Bild schon vergeben, greift der Ausweichbegriff oder – bei Emoji – die
   Twemoji-Zeichnung desselben Motivs; gibt es nichts mehr, fällt das Wort weg.
   **Ein Bild gehört genau einem Wort – in allen Decks.** Dasselbe Wort in zwei
   Themen behält sein Bild.

```bash
python3 tools/build_decks.py --dry-run   # nur rechnen und anzeigen
python3 tools/build_decks.py --write     # Themen schreiben, Bilder laden, exportieren
```

Ergebnis dieses Durchlaufs: **30 Themen mit 696 Wörtern**, jedes Bild nur für ein
Wort (Bildquellen: OpenMoji, Twemoji, Material Design Icons, ClipSafari). Themen
brauchen mindestens 15 Wörter, sonst entfallen sie; die Regel sind höchstens 25
Wörter je Thema, einzelne Themen dürfen im Plan aber mehr haben (`"max"` – das
Thema *Körper* hat 41 Wörter und bekommt im Druck drei Blätter). Gestrichene Wörter
sind nicht verloren: `themen-reserve/verworfen.md` führt sie mit Grund auf – ein
zurückgeholtes Wort braucht allerdings ein eigenes Bild.

Die Beispielsätze sind **einzeln geschrieben**, nicht aus Bausteinen erzeugt:
Für jedes Thema steht in `tools/saetze/*.json` die Paarung
`{ "<themaId>": { "<Wort>": ["Akkusativsatz.", "Dativsatz."] } }`. Eine
Datei `_hinweis`-Zeile erklärt jeweils das Anliegen (kurz, Präsens, kindgerecht).
Beim Bauen prüft `tools/build_decks.py` jeden Satz: Der Akkusativsatz muss die
Akkusativform des Wortes enthalten, der Dativsatz die Dativform; schwache Nomen
(Bär → den Bären, Magnet → dem Magneten) kommen aus den Formenfeldern des
Wörterbuchs, nicht aus einer Liste im Code. Fehlt ein Satz oder passt er nicht,
fällt das Wort weg – lieber ein Wort weniger als ein falscher Satz.

## Wörterbuch

`dictionary/nouns.json` ist das lokale Editor-Wörterbuch und enthält:

```json
{
  "zebra": {
    "word": "Zebra",
    "article": "das",
    "articles": ["das"],
    "plural": "Zebras",
    "plurals": ["Zebras"]
  }
}
```

Deutsche Nomen sind oft mehrdeutig (`der/die Paprika`, `der/das Keks`). Deshalb
speichert der Import alle belegten Varianten; `article` und `plural` sind nur die
zuerst gefundene Form.

Der mitgelieferte Bestand war früher klein und deckte nur die Projekt-Themes ab.
Mittlerweile liegt der komplette lokale Bestand vor: **119.744 Nomen** aus dem
Kaikki/Wiktextract-Dump des deutschen Wiktionary. Fehlt trotzdem ein Nomen, fragt
der Editor das deutsche Wiktionary ab und speichert einen erfolgreichen Treffer
lokal.

Auffrischen (lädt den Dump, behält vorhandene Einträge als Rückfall):

```bash
python3 tools/update_dictionary.py --keep-dump
```

Der Roh-Dump ist einige hundert MB komprimiert, wird gestreamt und anschließend
auf deutsche Nomen reduziert. Das resultierende `dictionary/nouns.json` bleibt
lokal beim Editor und wird **nie** in die fertige HTML eingebettet.

Alternativ mit einem bereits vorhandenen Dump:

```bash
python3 tools/import_kaikki_dictionary.py /pfad/raw-wiktextract-data.jsonl.gz
```

### Wörter gegen das Wörterbuch prüfen

```bash
python3 tools/audit_words.py
python3 tools/audit_words.py --report dictionary/pruefbericht.md
```

Meldet falsche Artikel, andere Mehrzahlen, erfundene Mehrzahlen, fehlende
Mehrzahlen und Wörter, die nur in der Mehrzahl vorkommen. Mehrdeutige Formen
zählen als gültig (`der/die Kiwi`, `Pizzas/Pizzen`); Bedeutungssonderfälle wie
`Atlas` (Kartenwerk → Atlanten, Stoff → Atlasse) werden als Hinweis geführt.
Massewörter wie Milch oder Reis behalten bewusst eine leere Mehrzahl.

## Satzvorschläge

Die Vorschläge sind bewusst regelbasiert. Für jedes Wort wird aus Artikel und
Kasus die benötigte Form gebildet. Der Editor-Typ erlaubt zusätzlich vorsichtige
Sätze für Tier, Mensch, Pflanze, Essen, Gegenstand, Fahrzeug, Ort, Körperteil und
Natur. Die Kategorie ist nur eine Autorenhilfe und verschwindet beim Export.

Beispiel:

```text
Zebra · das
Akkusativ: Das Kind beobachtet das Zebra.
Dativ:     Das Kind steht neben dem Zebra.
```

## Bilder

Neben den integrierten Suchquellen kann ein Autor ein eigenes Bild direkt in die
Werkstatt ziehen. Rasterbilder werden als eingebettete Daten in einen sicheren
SVG-Rahmen gepackt. Fremde SVGs werden bereinigt; aktive Inhalte und externe
Referenzen werden abgewiesen. Für eigene Uploads ist der Autor selbst für die
Nutzungsrechte verantwortlich.

Sehr aufwendige Vektorbilder (nachgezeichnete Fotos mit Tausenden kleinen
Flächen) lassen sich mit `tools/shrink_svg.py` verkleinern – entweder nur die
Koordinaten runden oder in Druckauflösung rastern (28 mm ≈ 662 px bei 600 dpi).
Der Raster-Weg schreibt eine abgeleitete Datei `<slug>-karte.json` und behält
Quelle, Autor und Lizenz des Originals.

### Kontrollblatt für Autoren

`python3 tools/word_overview.py` schreibt `output-selected/wortuebersicht.html`:
alle Themen als Abschnitte, jedes Wort mit Bild, Artikel, Mehrzahl und beiden
Sätzen. Bilder, die **zwei verschiedene Wörter** zeigen, sind oben mit Vorschau
aufgelistet und auf den Karten markiert – das ist die häufigste Ursache für eine
Karte, die komisch wirkt.

## Qualitätsprüfung

**Qualität prüfen** meldet pro Theme unter anderem:

- fehlendes Bild
- leeres Wort
- ungültigen Artikel
- fehlende Mehrzahl
- fehlenden Akkusativ-/Dativsatz
- Satz, der die Kasusform des Wortes nicht enthält (dann bleibt die Druckkarte ohne
  Satzkontext)
- doppelte Wörter
- Abweichung von lokal bekannten Wörterbuchdaten
- ein Bild, das auch zwei oder mehr andere Wörter zeigen (Hinweis; innerhalb eines
  Themes darf ein Bild nur ein Wort haben)

Damit kann ein Theme vor dem Build systematisch fertiggestellt werden.

Zwei Feinheiten der Prüfung:

- Deutsch ist mehrdeutig (`der`/`die` Paprika) und die erste Wörterbuch-Bedeutung ist
  nicht immer der übliche Artikel (Butter, Kiwi, Zwiebel, Taxi). Als richtig gilt
  deshalb **jede belegte Variante** aus `articles`/`plurals` des Wörterbuchs.
- Stoffnamen (Milch, Reis, Blut, Klee) haben keine Mehrzahl: die Liste steht in
  `tools/stoffnamen.py` und wird vom Deck-Bau, der Prüfung im Editor und
  `tools/audit_words.py` gemeinsam benutzt. Auf der Karte steht dann „– keine
  Mehrzahl“, und es wird keine Mehrzahl eingesprochen. „Mehrzahl fehlt“ erscheint nur
  bei Wörtern, die keine Stoffnamen sind und für die das Wörterbuch eine Mehrzahl kennt.

## Moderne Druckansicht

Beim Öffnen der fertigen Datei gilt: **die Karten kommen zuerst.** Die Lernkarten-
HTML ist rund 35 MB groß (692 Bilder und 2.592 Tonclips stecken darin). Themen und
Bilder stehen im vorderen Drittel, die Töne ganz am Ende – deshalb stehen die
Karten schon nach wenigen Sekunden, während der Browser den Rest der Datei noch
liest. Die Statuszeile zeigt das an: **⏳ Ton wird geladen** wechselt nach ein
paar Sekunden auf **🔊 Ton eingebaut**. (Auf einer schnellen Platte geht das
schneller, auf einer alten mögen es ein paar Sekunden mehr sein.)

Die Druckkarten wurden reduziert. Auf dem Papier stehen nur lernrelevante
Informationen:

- Theme
- Aufgabe
- Bild
- Nomen
- bei Kasus-Aufgaben: Satz mit **ausgeblendeter Kasusform des Artikels**
- die Auswahlmöglichkeiten

Das Feld **Karten** wählt die Aufgabe fürs ganze Blatt:

| Karten | Karte zeigt | Auswahl |
|---|---|---|
| Artikel | Bild, Wort, **kein Satz** (der Satz würde die Lösung verraten) | `DER` · `DIE` · `DAS` |
| Kasus | Bild, Wort, Satz mit Lücke; Akkusativ und Dativ **gemischt**, die Marke `AKK.`/`DAT.` zeigt den Fall | Akkusativ `DEN` · `DIE` · `DAS` · Dativ `DEM` · `DER` |
| Gemischt | je Karte abwechselnd Artikel- und Kasus-Aufgabe | beides |

**Farben:** jede Antwortblase trägt die Farbe ihrer Artikelreihe, und die richtige
Blase ist immer die mit der Farbe des Wortes.

| Reihe | Normal | Akkusativ | Dativ |
|---|---|---|---|
| `der` – **blau** | der | den | dem |
| `die` – **rot** | die | die | der |
| `das` – **grün** | das | das | dem |

**Der Dativ ist die Ausnahme.** Er hat nur zwei Formen: `dem` für männliche **und**
sächliche Wörter, `der` für weibliche. Deshalb steht im Dativ **nur eine**
`DEM`-Blase auf der Karte, und sie ist **grau** — eine Reihenfarbe wäre gelogen,
denn `dem` gehört zu zwei Reihen. Im Dativ verrät die Farbe die Antwort also
nicht: dort muss man das Geschlecht kennen („das Eis“ → `dem`, „die Milch“ →
`der`). Früher standen dort zwei `DEM`-Blasen – dieselbe Form einmal falsch und
einmal richtig, was beim Ankreuzen nur verwirrt hat. Die Mehrzahl (`den Kindern`)
steht nur in der Mehrzahl-Aufgabe.

Ohne Sätze (Artikel-Modus) entfallen die Fallmarken; alle Karten stehen in einem
Raster mit größeren Bildern. Auch die Kasus-Aufgaben stehen in **einem** Raster –
Akkusativ und Dativ sind gemischt, und die Marke `AKK.`/`DAT.` in der Ecke jeder
Karte sagt, welche Form in die Lücke gehört. Getrennte Kästen mit Überschrift
„AKKUSATIV“ / „DATIV“ gibt es nicht mehr: die Karten zeigen ihren Fall selbst.

Der vollständige Beispielsatz verrät auf dem Arbeitsblatt also nicht mehr die
Lösung. Lösungsseiten sind standardmäßig ausgeschaltet und können bei Bedarf
zugeschaltet werden. Editor-, Quellen-, Status- und TTS-Informationen werden
nicht gedruckt.

**Reihenfolge:** standardmäßig sind alle gewählten Themen **gemischt** – die
Wörter werden einmal durchgemischt und der Reihe nach auf die Blätter verteilt,
jedes Wort kommt genau einmal vor. Die Reihenfolge bleibt stehen, auch wenn man
später das Raster oder die Seitenzahl ändert – neue Wörter kommen nur über den
Knopf **Neu mischen** oder eine geänderte Themenauswahl. 53 Wörter stehen in zwei
Themen (die *Ameise*
in *Wald und Wiese* **und** *Insekten und Kriechtiere*, die *Sonne* in *Wetter*
und *Flugzeuge und Weltall*): in der Mischung bekommt so ein Wort trotzdem nur
**eine** Karte, damit dieselbe Karte nicht zweimal auf dem Stapel liegt. Wer
lieber nach Themen lernt, stellt auf
**Nach Themen**; dann bekommt jedes Thema eigene Blätter, und zwar zuerst eines.
Mehr Blätter bekommt ein Thema erst, wenn mehr Seiten eingestellt sind als Themen
ausgewählt sind – dann bekommen zuerst die Themen mit den **meisten noch
ungedruckten Wörtern** weitere Blätter (das Thema *Körper* hat über 40 Wörter und
braucht bei 4×4 drei Blätter).

**Karten je Blatt:** das Raster ist frei wählbar, von **3×3** (9 große Bilder, gut
für Anfänger und kleine Kinder) bis **8×8** (64 kleine Karten, spart Papier).
Vorgabe ist **4×4** – das ist das frühere Blatt mit 16 Karten. Die Karten wachsen
und schrumpfen mit dem Raster: Bild, Wort, Schrift und Antwortkringel skalieren
mit, und sehr lange Wörter (z. B. „Schraubenschlüssel“) werden automatisch eine
Stufe kleiner, damit nichts abgeschnitten wird. Beim Umstellen wird nur
umverteilt: die Wörter bleiben auf ihren Karten, nur die Blätter schneiden
anders – deshalb reagiert die Ansicht sofort statt nach Sekunden. Nur die
Blätter, die man gerade sieht, werden berechnet; die übrigen holt der Browser
beim Blättern nach (spätestens beim Drucken sind alle fertig).

Die Zeile oben zeigt jederzeit, was aufs Papier kommt (z. B. „30 Themen ·
639 Begriffe · 40 Seiten · 4×4 · gemischt“), und bei knapper Seitenzahl zusätzlich,
wie viele Wörter es werden („16 von 639 Wörtern“). Die Seitenzahl stellt sich
automatisch auf **so viele Blätter, wie alle Wörter brauchen** (gemischt) bzw. auf
die Themenszahl (nach Themen). Wer eine eigene Zahl einträgt, behält sie.

## Themen auswählen

Im Feld **Themen** lässt sich eine beliebige Mischung zusammenstellen: alle,
ein einzelnes Thema oder z. B. *Tiere + Fahrzeuge + Farben*. Die Auswahl gilt für
Drucken **und** Spielen:

- **Drucken** mischt standardmäßig alle gewählten Themen (jedes Wort genau einmal,
  Raster 4×4 = 16 Karten je Blatt); **Nach Themen** gibt jedem Thema eigene Blätter.
- **Spielen** zieht die Karten nur aus den gewählten Themen.
- **Alle** / **Keine** setzen die Auswahl schnell zurück bzw. leeren sie.

Die Auswahl wird lokal gemerkt (localStorage) und ist nach dem Neuladen wieder da.

## Spielen

Der Spielmodus zeigt Bild und Wort, spricht die Frage vor und bietet drei Antworten.
**Aufgabe** wählt den Aufgabentyp:

| Aufgabentyp | Frage | Antwortmöglichkeiten |
|---|---|---|
| Artikel | Welcher Artikel ist richtig? | `DER` · `DIE` · `DAS` |
| Kasus | Welche Form steht im Akkusativ bzw. Dativ? | `DEN` · `DIE` · `DAS` bzw. `DEM` · `DER` (Dativ hat nur zwei Formen: `DEM` grau für männlich/sächlich, `DER` rot für weiblich) |
| Mehrzahl | Wie heißt die Mehrzahl? | die richtige Mehrzahlform plus zwei falsche Formen **desselben** Wortes (`die Bärs`, `die Bäre`) |
| Gemischt | wechselt die drei Typen ab | — |

Punkte gibt es nur für die richtige Antwort im ersten Versuch. Die Lösung
(Beispielsatz bzw. Mehrzahlform) erscheint erst danach und wird vorgelesen; die
Karte bleibt so lange stehen, bis die Stimme fertig ist.

Danach läuft eine **Wartepause von 10 Sekunden**, dann kommt die nächste Karte.
Unter der Karte stehen dafür zwei Knöpfe:

- **Weiter ⏭️** – sofort zur nächsten Karte (kein Warten)
- **⏸️ Anhalten** – stoppt die Automatik; die Karte bleibt stehen, bis du
  **▶️ Weiterlaufen** oder **Weiter** drückst

Der Zähler zeigt „weiter in 7 s“ bzw. „angehalten“, damit klar ist, was als
Nächstes passiert.

Stoffnamen ohne Mehrzahl (Milch, Reis, Butter …) werden in der Mehrzahl-Aufgabe
automatisch als Artikel-Aufgabe gestellt; im Lösungsblatt steht „– keine Mehrzahl“.

## Export

### Ein Theme

Im Editor: **Dieses Theme bauen**.

### Das ganze Projekt als eine Datei

Im Editor: **Alle Themes · 1 HTML**.

Oder auf der Kommandozeile:

```bash
python3 build_simple.py \
  --themes selected-themes \
  --output lernkarten.html
```

Die fertige Datei enthält HTML, CSS, JavaScript, Bilder, Theme-Daten und die
vorgerenderten MP3-Clips. Sie benötigt beim Lernenden weder Netzwerk noch Python,
Piper, ffmpeg oder ein Wörterbuch.

## Verzeichnisse

```text
themes/                  editierbare Theme-Daten
selected-themes/         bereinigte Build-Daten
themen-reserve/          Wortliste der gestrichenen Wörter + Sicherung alter Bildzuordnungen
dictionary/              Wörterbuch nur für Autoren
image-library/           ausgewählte/hochgeladene Bilder
tts-cache/               lokaler MP3-Audiocache (nicht im Repository)
vendor/piper/            Pflicht-Stimmmodell de_DE-thorsten-high (CC0 1.0, nicht im Repository)
output-selected/         fertige Single-HTML-Dateien (nicht im Repository)
tools/                   Editor-Hilfswerkzeuge
tools/decks/             Themenplan (Wort + englischer Bildbegriff)
```

## Repository

Im Repository liegen die **Quellen**: Themes, Bildauswahl, Wörterbuch, Vorlage,
Werkzeuge, Tests und diese Dokumentation. Insgesamt sind das rund 60 MB.

**Nicht** im Repository liegen die drei großen Brocken — `.gitignore` hält sie
fern, weil sie entweder erzeugt werden oder sehr groß sind:

| Was | Größe | Wie man es bekommt |
|---|---|---|
| `vendor/piper/de_DE-thorsten-high.onnx` | 109 MB | einmalig herunterladen, siehe „Feste Aussprache“ |
| `dictionary/raw-wiktextract-data.jsonl.gz` | 289 MB | Kaikki/Wiktextract-Dump, nur für `tools/import_kaikki_dictionary.py`; das fertige `dictionary/nouns.json` liegt bei |
| `tts-cache/`, `output-selected/` | 28 / 46 MB | entstehen beim Bauen und Exportieren von selbst |

Die fertige Lernkarten-Datei für Lernende hängt als Release-Anhang an der
jeweiligen Version — sie muss nicht gebaut werden, wenn man nur üben will.

### Prüfen

```bash
python3 tests/smoke_test.py        # Audio (gemockt), Sätze, Wörterbuch, Audit, Export, Bildschutz
python3 tools/audit_words.py       # Artikel und Mehrzahl aller Themes
python3 -m py_compile bilder_waehlen.py build_simple.py tools/*.py
python3 tools/check_tts.py         # nur mit Piper und ffmpeg: echte Stimme prüfen
```

Beiträge sind willkommen — bitte vorher [CONTRIBUTING.md](CONTRIBUTING.md) lesen.
Sicherheitsrelevantes steht in [SECURITY.md](SECURITY.md), Bild- und
Stimmlizenzen in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Lizenz

Der Quellcode steht unter der **GNU General Public License v3.0** (siehe
[LICENSE](LICENSE)). Die eingebetteten Bilder stammen aus OpenMoji (CC BY-SA 4.0),
Twemoji (CC BY 4.0) und ClipSafari (CC0) — die Pflichtangaben dazu stehen in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) und werden in jede gebaute
Lernkarten-Datei übernommen.
