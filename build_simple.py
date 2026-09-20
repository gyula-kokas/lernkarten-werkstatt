#!/usr/bin/env python3
"""Build one self-contained learning-card HTML with mandatory Piper audio.

Speech is rendered during export with Piper (de_DE-thorsten-high, CC0 1.0) and
embedded as MP3 data URIs (48 kbit/s, 44.1 kHz, MPEG-1 Layer III). The
generated HTML therefore needs no system TTS, no network and no browser voice.
There is deliberately no fallback synthesizer.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from tools.tts_piper import (
    ENGINE,
    MP3_BITRATE,
    MP3_SAMPLE_RATE,
    VOICE,
    default_workers,
    probe,
    synthesize_many,
    texts_for_entries,
)

THEME_MARKER = "/*__THEMES_JSON__*/ []"
TTS_MARKER = '/*__EMBEDDED_TTS__*/ {"mode":"none"}'


def safe_json(data) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("</", r"<\/")
        .replace("\u2028", r"\u2028")
        .replace("\u2029", r"\u2029")
    )


def load_themes(folder: Path) -> list[dict]:
    themes: list[dict] = []
    seen: set[str] = set()
    for path in sorted(folder.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        docs = raw if isinstance(raw, list) else raw.get("themes", [raw]) if isinstance(raw, dict) else []
        for theme in docs:
            if not isinstance(theme, dict):
                continue
            theme = dict(theme)
            theme_id = str(theme.get("themeId", "")).strip()
            if not theme_id:
                raise SystemExit(f"{path.name}: themeId fehlt")
            if theme_id in seen:
                raise SystemExit(f"Doppelte themeId: {theme_id}")
            seen.add(theme_id)
            cleaned_entries = []
            words_seen: set[str] = set()
            for entry in theme.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                e = dict(entry)
                for key in list(e):
                    if key.startswith("editor") or key.startswith("_editor"):
                        e.pop(key, None)
                e.pop("imageSearch", None)
                word = str(e.get("word", "")).strip()
                if not word:
                    raise SystemExit(f"{path.name}: leeres Wort")
                folded = word.casefold()
                if folded in words_seen:
                    raise SystemExit(f"{path.name}: doppeltes Wort: {word}")
                words_seen.add(folded)
                if e.get("article") not in {"der", "die", "das"}:
                    raise SystemExit(f"{path.name}: ungültiger Artikel bei {word}")
                if not str(e.get("accusativeSentence", "")).strip():
                    raise SystemExit(f"{path.name}: Akkusativsatz fehlt bei {word}")
                if not str(e.get("dativeSentence", "")).strip():
                    raise SystemExit(f"{path.name}: Dativsatz fehlt bei {word}")
                if not str(e.get("imageSvg", "")).strip():
                    raise SystemExit(f"{path.name}: Bild fehlt bei {word}")
                cleaned_entries.append(e)
            if not cleaned_entries:
                # Ein leeres Theme (z.B. frisch im Editor angelegt und noch nicht
                # gefüllt) darf den Gesamtbau nicht abbrechen.
                print(f"Warnung: {path.name} enthält keine Wörter – übersprungen", flush=True)
                continue
            theme["entries"] = cleaned_entries
            theme["entryCount"] = len(cleaned_entries)
            for key in list(theme):
                if key.startswith("editor") or key.startswith("_editor"):
                    theme.pop(key, None)
            themes.append(theme)
    if not themes:
        raise SystemExit(f"Keine Theme-JSONs in {folder}")
    return themes


def build_audio(themes: list[dict], cache_dir: Path) -> dict:
    ok, detail = probe()
    if not ok:
        raise SystemExit(
            "Pflicht-TTS fehlt: " + detail + "\n"
            "Der Build wird abgebrochen. Es gibt keinen Browser-/Piper-/anderen Fallback."
        )

    texts = texts_for_entries(themes)
    workers = default_workers()
    print(f"TTS: {detail}")
    print(f"Erzeuge/verwende {len(texts)} eindeutige MP3-Audioclips ({workers} Prozesse parallel) …")

    def progress(done: int, total: int) -> None:
        if done == 1 or done % 100 == 0 or done == total:
            print(f"  Audio {done}/{total}", flush=True)

    clips = synthesize_many(texts, cache_dir, progress=progress)
    audio_by_text: dict[str, str] = {
        text: "data:audio/mpeg;base64," + base64.b64encode(clips[text]).decode("ascii")
        for text in texts
        if text in clips
    }

    return {
        "mode": "embedded-piper-mp3",
        "engine": ENGINE,
        "voice": VOICE,
        "codec": "MP3 (MPEG-1 Layer III)",
        "bitrate": MP3_BITRATE,
        "sampleRate": MP3_SAMPLE_RATE,
        "audioByText": audio_by_text,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Lernkarten Single-HTML Builder mit Pflicht-Piper-Audio")
    parser.add_argument("--themes", type=Path, default=root / "selected-themes")
    parser.add_argument("--template", type=Path, default=root / "der_die_das_template.html")
    parser.add_argument("--output", type=Path, default=root / "lernkarten.html")
    parser.add_argument("--tts-cache", type=Path, default=root / "tts-cache")
    args = parser.parse_args()

    template = args.template.read_text(encoding="utf-8")
    if template.count(THEME_MARKER) != 1 or template.count(TTS_MARKER) != 1:
        raise SystemExit("Template-Marker fehlen oder sind doppelt")

    themes = load_themes(args.themes)
    tts = build_audio(themes, args.tts_cache)

    html = template.replace(THEME_MARKER, safe_json(themes), 1)
    html = html.replace(TTS_MARKER, safe_json(tts), 1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"FERTIG: {args.output}")
    print(f"Themes: {len(themes)}")
    print(f"TTS: Pflichtstimme {ENGINE} {VOICE}, MP3 {MP3_BITRATE}, vollständig eingebettet")
    print(f"Größe: {args.output.stat().st_size / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    main()
