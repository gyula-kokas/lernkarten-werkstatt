"""Stoffnamen ohne Mehrzahl.

Ein Stoffname (Milch, Reis, Blut) hat im Deutschen keine übliche Mehrzahl. Das
Wörterbuch kennt zwar fachsprachliche Formen ("Milche", "Reise", "Butters"), die
sind auf einer Lernkarte aber falsch: der Bau lässt darum die Mehrzahl leer, das
Lösungsblatt druckt "keine Mehrzahl" und keine Mehrzahl wird eingesprochen.

Alle drei Stellen müssen dieselbe Liste benutzen, sonst meldet die Prüfung
Fehler, die der Deck-Bau absichtlich so schreibt:

* ``tools/build_decks.py`` - schreibt die leere Mehrzahl,
* ``bilder_waehlen.py`` - Prüfung im Editor (``audit_theme``),
* ``tools/audit_words.py`` - Offline-Prüfung aller Themen.
"""

STOFFNAMEN = frozenset({
    "butter", "milch", "reis", "honig", "salz", "wasser", "käse", "eis", "blut",
    "regen", "schokolade", "müsli", "fleisch", "schnee", "mehl", "zucker",
    "sahne", "öl",
})
