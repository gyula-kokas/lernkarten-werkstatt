# Third-Party Notices

## OpenMoji

Der Editor kann OpenMoji-SVGs auswählen. OpenMoji-Inhalte stehen unter
CC BY-SA 4.0. Die konkrete Bildquelle, Autor-/Projektangabe und Lizenz werden
pro ausgewähltem Bild in das exportierte Theme übernommen.

## Twemoji

Der Editor kann Twemoji-SVGs auswählen. Die Bilddaten werden unter den vom
Upstream-Projekt angegebenen Bedingungen verwendet; die konkrete Quellen- und
Lizenzangabe wird pro ausgewähltem Bild gespeichert.
Twemoji dient zusätzlich als **zweite Zeichnung** desselben Motivs: ist das
OpenMoji-Bild schon an ein anderes Wort vergeben, wird die Twemoji-Fassung
genommen – das sind zwei unterschiedliche Bilder, keine Kopie.

## Material Design Icons (Pictogrammers)

Für Objekte, die es als Emoji nicht gibt (Heizung, Kessel, Teppich, Regal,
Wald, Schneeflocke, Sprungseil …), kann der Editor SVGs aus
[Material Design Icons](https://github.com/Templarian/MaterialDesign) (Pictogrammers)
übernehmen. Die Icons stehen unter **Apache-2.0**, der Lizenztext liegt in
`tools/image-sources/LICENSE-MaterialDesign.txt` bei, der verwendete Commit ist in
`tools/image-sources/mdi.json` festgehalten. Quelle, Autor und Lizenz wandern in
jeden exportierten Eintrag und in die Quellenliste der Lern-HTML.

## Fluent Emoji (Microsoft)

Als **dritte Zeichnung** eines Motivs kann der Editor SVGs aus
[Fluent Emoji](https://github.com/microsoft/fluentui-emoji) übernehmen (Color-Variante,
z. B. die eckige Waffel oder die Rückansicht des Körpers). Die Grafiken stehen unter
**MIT**, Copyright (c) Microsoft Corporation. Der verwendete Commit ist in
`tools/image-sources/fluent.json` festgehalten, neu erzeugt wird der Index mit
`python3 tools/import_fluent_emoji.py`. Der Lizenztext liegt unter
`tools/image-sources/LICENSE-FluentEmoji.txt` bei. Quelle, Autor und Lizenz wandern in
jeden exportierten Eintrag und in die Quellenliste der Lern-HTML.

## ClipSafari

Der Editor übernimmt nur ClipSafari-Treffer, bei denen die lokale Prüfung eine
CC0-Angabe auf der Quellseite findet. Die Quell-URL wird pro Bild gespeichert.

## Deutsches Wiktionary / Kaikki

Der Editor kann Artikel und Plural aus dem deutschen Wiktionary lesen und lokal
cachen. Optional kann ein Kaikki/Wiktextract-Dump importiert werden. Diese Daten
sind Editor-Hilfsdaten und werden nicht in die fertige Lernkarten-HTML exportiert.
Bei einer Weitergabe eines daraus erzeugten Wörterbuch-Caches sind die
Wiktionary-Lizenz- und Attributionsbedingungen zu beachten.

## Wikidata

Die automatische grobe semantische Klassifikation verwendet die öffentliche
Wikidata-Suche. Die Klassifikation ist nur Editor-Metadatum und wird nicht in
die fertige Lernkarten-HTML exportiert.

## TTS

Der Editor und Builder verwenden ausschließlich **Piper** mit der deutschen
Stimme `de_DE-thorsten-high`. Die Ausgabe wird als MP3 (MPEG-1 Layer III,
48 kbit/s, 44,1 kHz) eingebettet. Es gibt keinen TTS-Fallback.

Eingebettet werden nur die erzeugten Audiodaten — weder Piper noch ffmpeg werden
mitgeliefert oder in die Lernkarten-HTML kopiert:

- **Piper (`piper-tts`)** – GPL-3.0-or-later
  (https://github.com/OHF-Voice/piper1-gpl). Wird als eigenständiges Programm
  lokal installiert und aufgerufen; es wird kein Quelltext übernommen oder
  weitergegeben.
- **Stimme `de_DE-thorsten-high`** – **CC0 1.0 (Public Domain)**, Datensatz
  https://github.com/thorstenMueller/Thorsten-Voice. Die damit erzeugten
  Audiodaten dürfen frei verwendet und weitergegeben werden.
- **ffmpeg / libmp3lame** – ffmpeg steht unter LGPL-2.1-or-later (optionale
  Teile unter GPL), libmp3lame unter LGPL-2.0-or-later. ffmpeg wird ebenfalls
  nur als Programm aufgerufen.
- **MP3-Patente** – die letzten MP3-Patente sind 2017 abgelaufen; MP3 darf frei
  verwendet werden.

Für die fertige Lernkarten-HTML heißt das: sie enthält eigenen Code und die
vorgerenderten Audiodaten, kein Fremdprogramm. Eine freie Weitergabe ist damit
auch rechtlich unkritisch.

## Piper voice model in the project tree

The editor uses only the German Piper voice `de_DE-thorsten-high` (CC0 1.0, dataset Thorsten-Voice). On first use the model is copied into `vendor/piper/` so every build resolves the same fixed voice from the project tree; a build never downloads anything and never substitutes another voice. The voice files themselves may be redistributed freely (CC0). The Piper program is installed separately and remains under GPL-3.0-or-later.

## Eigene Bild-Uploads

Lokale Benutzer-Uploads sind keine Drittanbieter-Inhalte der Lernkarten-Werkstatt.
Die Werkstatt speichert sie nur technisch im Projekt. Wer solche Bilder
veröffentlicht, muss selbst sicherstellen, dass die nötigen Nutzungsrechte
vorliegen.

## Editor-Wörterbuch 0.1

`tools/update_dictionary.py` kann den aktuellen Kaikki/Wiktextract-Rohdump der
deutschen Wiktionary-Ausgabe herunterladen und auf Artikel/Plural-Daten für
Nomen reduzieren. Dieser erzeugte Wörterbuchbestand ist nur Autorenwerkzeug und
wird nicht in die Single-HTML für Lernende eingebettet. Bei Weitergabe eines
solchen Wörterbuch-Caches sind die einschlägigen Wiktionary-Lizenz- und
Attributionsbedingungen zu beachten.
