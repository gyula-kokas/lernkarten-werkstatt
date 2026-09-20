# Security

Die Lernkarten-Werkstatt bindet den Editor ausschließlich an `127.0.0.1`.
Schreibende API-Aufrufe benötigen zusätzlich ein zufällig erzeugtes
Session-Token. Der Host-Header wird geprüft.

Fremde SVGs werden vor dem Speichern bereinigt. Skripte, `foreignObject`,
externe Referenzen und aktive Attribute werden abgewiesen. Lokale Rasterbilder
werden nicht als HTML ausgeführt, sondern als Base64-Bilddaten in einen von der
Werkstatt erzeugten SVG-Rahmen eingebettet. Uploads sind auf 6 MB begrenzt.

Der Editor kann für Bildsuche, Wiktionary-Wörterbuch-Fallback und
Wikidata-Klassifikation auf das Internet zugreifen. Die **fertig exportierte
HTML-Datei** enthält diese Editor-Funktionen nicht und ist offline nutzbar.
Audio ist dort ausschließlich vorgerendertes MP3 (Piper `de_DE-thorsten-high`,
48 kbit/s, 44,1 kHz) — kein Fremdprogramm und keine Netzwerkverbindung.

Theme-Dateien und Bilder aus unbekannten Quellen sollten trotzdem nur aus
vertrauenswürdigen Quellen übernommen werden. Bei eigenen Uploads ist der Autor
für Urheber- und Nutzungsrechte verantwortlich.
