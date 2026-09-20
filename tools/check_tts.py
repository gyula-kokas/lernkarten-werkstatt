#!/usr/bin/env python3
"""Check the mandatory TTS chain: Piper de_DE-thorsten-high -> MP3 48k/44.1 kHz."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import tts_piper


def main() -> int:
    ok, detail = tts_piper.probe()
    print(("OK: " if ok else "FEHLER: ") + detail)
    print("Projektstimme:", tts_piper.VOICE_MODEL,
          "" if tts_piper.VOICE_MODEL.is_file() else "(fehlt)")
    print("Piper-Python:", tts_piper.piper_python() or "nicht gefunden")
    print("ffmpeg:", shutil.which("ffmpeg") or "nicht gefunden")
    print("Format: MP3 (MPEG-1 Layer III)", tts_piper.MP3_BITRATE,
          f"/ {tts_piper.MP3_SAMPLE_RATE} Hz")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
