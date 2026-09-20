# Editor-Wörterbuch

`nouns.json` ist das lokale Wörterbuch für deutsche Nomen mit Artikel und
Nominativ-Plural. Es gehört nur zum Editor und wird nicht in die exportierte
Lernkarten-HTML eingebettet.

Der Bestand ist inzwischen vollständig: **119.744 Nomen** aus dem Kaikki/
Wiktextract-Rohdump des deutschen Wiktionary. Einträge halten **alle** belegten
Varianten, weil deutsche Nomen mehrdeutig sind:

```json
{"kiwi": {"word": "Kiwi", "article": "der", "articles": ["der", "die"],
          "plural": "Kiwis", "plurals": ["Kiwis"], "source": "Kaikki/Wiktionary"}}
```

`article` und `plural` sind die zuerst gefundene Form (die der Editor vorschlägt),
`articles` und `plurals` sind die vollständige Liste. Fehlt ein Nomen trotzdem,
fragt der Editor das deutsche Wiktionary nach und cached den Treffer lokal.

## Auffrischen oder neu aufbauen

```bash
python3 tools/update_dictionary.py --keep-dump
python3 tools/import_kaikki_dictionary.py /pfad/raw-wiktextract-data.jsonl.gz
```

Das Tool lädt den aktuellen Kaikki/Wiktextract-Rohdump (einige hundert MB
komprimiert), streamt ihn, behält vorhandene Einträge als Rückfall und schreibt
nur die kompakte Nomenliste. Ohne `--keep-dump` wird der Rohdump danach gelöscht.

## Wörter und Mehrzahl prüfen

```bash
python3 tools/audit_words.py
python3 tools/audit_words.py --only-errors --report dictionary/pruefbericht.md
```

Meldet falschen Artikel, andere Mehrzahl, erfundene Mehrzahl, fehlende Mehrzahl,
Mehrzahlwörter ohne Grundform und Wörter, die gar nicht im Wörterbuch stehen.
Mehrdeutige Formen gelten als gültig; Bedeutungssonderfälle (`Atlas` → Atlanten
als Kartenwerk, Atlasse als Stoff) stehen als Hinweis in `SENSE_VARIANTS`.

Die Prüfung läuft auch im Testlauf mit (`python3 tests/smoke_test.py`) und wird
übersprungen, wenn die Wörterbuchdatei fehlt.

Bei einer Weitergabe des Wörterbuch-Caches sind die Lizenz- und
Attributionsbedingungen der zugrunde liegenden Wiktionary-Daten zu beachten.
