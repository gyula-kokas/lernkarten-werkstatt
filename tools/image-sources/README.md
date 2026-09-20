# Suchkataloge und Bildlizenzen

OpenMoji: https://github.com/hfg-gmuend/openmoji – Grafik und Metadaten CC BY-SA 4.0, OpenMoji contributors. Die individuellen Urheber stehen im Katalog. Englische Titel und Tags stammen aus data/openmoji.json.

Twemoji: https://github.com/jdecked/twemoji – Grafik CC BY 4.0, Twitter, Inc. and other contributors. Unicode-Kennungen wurden gegen das offizielle SVG-Dateiverzeichnis abgeglichen; Suchbegriffe stammen aus dem OpenMoji-Katalog.

Material Design Icons: https://github.com/Templarian/MaterialDesign – Grafik Apache 2.0, Pictogrammers. `mdi.json` ist der Namensindex (Icon-Name und Titel) mit festgehaltenem Commit; der Lizenztext liegt als LICENSE-MaterialDesign.txt bei. Diese Icons füllen Objekte, die es als Emoji nicht gibt.

Bildquelle wird so gewählt: OpenMoji zuerst. Ist das Motiv schon an ein anderes Wort vergeben, kommt Twemoji (zweite Zeichnung desselben Emojis). Wörter mit `provider` "mdi" im Plan (`tools/decks/*.json`, 4. Element) holen ihr Bild aus Material Design, `"clipsafari"` nutzt eine feste ClipSafari-Kennung.
catalog.json ist ein bearbeiteter Suchindex (Felder ausgewählt, Twemoji-Kennungen zugeordnet), unter CC BY-SA 4.0. openmojiRef und twemojiRef enthalten die festgehaltenen Git-Commits. SVG-Downloads verwenden genau diese Versionen. Die Lizenztexte sind beigefügt.

Die Bildauswahl verändert SVGs technisch: unsichere/nicht unterstützte Elemente werden entfernt, IDs isoliert und Maße für skalierte Darstellung angepasst. Urheber, Originalquelle, Lizenzlink und Änderungshinweis werden in die exportierten Theme-Einträge und die Quellenliste der Lern-HTML übernommen.
