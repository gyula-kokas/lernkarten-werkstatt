## Was ändert sich?

<!-- Kurz beschreiben: Welche Datei, welches Theme, welche Karte? -->

## Warum?

<!-- Auslöser, Wunsch oder Fehler. Bei UI-Änderungen gern ein Bildschirmfoto. -->

## Geprüft

- [ ] `python3 tests/smoke_test.py` läuft grün
- [ ] `python3 tools/audit_words.py` meldet 0 Fehler und 0 Hinweise
- [ ] `python3 -m py_compile bilder_waehlen.py build_simple.py tools/*.py`
- [ ] Vorlage geändert? Dann Syntax geprüft (`node --check` auf das Skript) und
      die Karten bei 3×3, 4×4 und 8×8 im Blick behalten (nichts abgeschnitten)
- [ ] Ausdruck geprüft? Lösungsblatt und Blattaufteilung stimmen noch
- [ ] Bilder: keine Bildwahl in `image-library/selections.json` überschrieben
- [ ] Keine neue TTS-Kette, keine zusätzlichen Abhängigkeiten, keine Sätze
      automatisch erzeugt (siehe [CONTRIBUTING.md](../CONTRIBUTING.md))

## Betroffene Themes / Wörter

<!-- z. B. „Wetter: Hagel ergänzt“ oder „keine“ -->
