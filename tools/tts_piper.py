#!/usr/bin/env python3
"""Strict Piper speech helper: one voice, one codec, no fallback.

The project has exactly one voice (Piper ``de_DE-thorsten-high``, released as
CC0 1.0, 22.05 kHz) and exactly one output format (MP3 48 kbit/s at 44.1 kHz,
i.e. MPEG-1 Layer III). MPEG-1 plays on Safari, iOS, Firefox, Chromium and
every desktop player, which matters because the exported HTML must be a single
self-contained file that anyone can open. There is no fallback synthesizer.

Piper runs in its own virtual environment because the project itself only uses
the standard library: :mod:`tools.piper_worker` keeps the ONNX model loaded and
feeds one text per line, this module trims and levels the PCM, and ffmpeg
encodes the result. The voice model lives in ``vendor/piper/`` and is copied
from a locally available download; a build never downloads anything by itself.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
from array import array
from pathlib import Path

ENGINE = "Piper"
VOICE = "de_DE-thorsten-high"
# Speaking rate of the voice model: 1.0 is the model default, higher is slower.
# Short words in particular are clearer and calmer when the model gets more frames.
LENGTH_SCALE = 1.12
# MPEG-1 Layer III at 44.1 kHz. 48 kbit/s mono is transparent enough for
# speech and keeps a whole card set in the low tens of megabytes.
MP3_BITRATE = "48k"
MP3_SAMPLE_RATE = 44100
# Every clip is scaled to this peak (about -1 dBFS) so volume stays even.
TARGET_PEAK = 0.89
LEAD_SILENCE_MS = 50
TAIL_SILENCE_MS = 120
# Relative to the clip peak: below this a sample counts as silence.
SILENCE_FLOOR = 0.012
# The spoken prompt consists of this fixed prefix plus the word clip. The word
# is never spoken with its article: in the article quiz the article is the answer.
PROMPT_PREFIX = "Das Wort heißt"

# Bump when the produced bytes change, so cached clips are rebuilt.
FORMAT_VERSION = 6

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "vendor" / "piper"
VOICE_MODEL = VENDOR_DIR / f"{VOICE}.onnx"
VOICE_CONFIG = VENDOR_DIR / f"{VOICE}.onnx.json"
WORKER = Path(__file__).resolve().parent / "piper_worker.py"
VOICE_FILES = (f"{VOICE}.onnx", f"{VOICE}.onnx.json")

# Interpreters that may have Piper installed, in order of preference. A
# PIPER_PYTHON environment variable wins over this list. Windows virtualenvs put
# the interpreter into ``Scripts\python.exe`` instead of ``bin/python``, so the
# two platforms need their own list - the README walks users through the setup.
if os.name == "nt":  # pragma: no cover - platform specific
    VENV = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ded-tts" / "venv"
    PIPER_PYTHONS = (VENV / "Scripts" / "python.exe",)
else:
    VENV = Path.home() / ".local" / "share" / "ded-tts" / "venv"
    PIPER_PYTHONS = (
        VENV / "bin" / "python",
        Path.home() / ".local" / "share" / "piper" / "venv" / "bin" / "python",
    )
# Places a one-time ``piper.download_voices`` run may have left the models in.
MODEL_SOURCES = (
    Path.home() / ".local" / "share" / "piper" / "voices",
    Path.home() / ".local" / "share" / "piper",
    Path("/usr/share/piper/voices"),
    Path("/usr/local/share/piper/voices"),
)

_PROBE_CACHE: tuple[bool, str] | None = None
_PYTHON: str | None = None
_RATE: int | None = None


class _PiperProcess:
    """One long-running Piper worker with its own model load."""

    def __init__(self, threads: int = 0) -> None:
        self.threads = threads
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def start(self) -> subprocess.Popen:
        if self.proc is not None and self.proc.poll() is None:
            return self.proc

        python = piper_python()
        if not python:
            raise RuntimeError("Kein Python mit installiertem Piper gefunden.\n" + install_hint())
        if not VOICE_MODEL.is_file():
            raise RuntimeError(f"Stimmmodell fehlt: {VOICE_MODEL}")

        cmd = [
            python, str(WORKER),
            "--model", str(VOICE_MODEL),
            "--config", str(VOICE_CONFIG),
            "--length-scale", str(LENGTH_SCALE),
        ]
        if self.threads:
            cmd += ["--threads", str(self.threads)]

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # Diagnostics stay out of the binary frame stream; failures travel in
            # the frame itself (see ERROR_FLAG in piper_worker).
            stderr=subprocess.DEVNULL,
            env=_worker_env(),
        )
        return self.proc

    def synthesise(self, text: str) -> bytes:
        """Return raw 16-bit mono PCM for one text."""
        with self.lock:
            proc = self.start()
            if proc.stdin is None or proc.stdout is None:  # pragma: no cover - defensive
                raise RuntimeError("Piper-Prozess ist nicht verbunden.")
            proc.stdin.write(text.encode("utf-8") + b"\n")
            proc.stdin.flush()

            length = struct.unpack("<I", _read_exact(proc.stdout, 4))[0]
            if length & 0x80000000:
                message = _read_exact(proc.stdout, length & 0x7FFFFFFF).decode("utf-8", "replace")
                raise RuntimeError(message)
            return _read_exact(proc.stdout, length)

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


# The editor asks for one clip at a time, so it shares a single process that may
# use all cores.
_DEFAULT = _PiperProcess()
atexit.register(_DEFAULT.stop)


def stop_worker() -> None:
    """Shut the shared Piper process down and let it exit cleanly."""
    _DEFAULT.stop()


def default_workers() -> int:
    """Number of Piper processes to run in parallel (env DED_TTS_WORKERS wins)."""
    override = os.environ.get("DED_TTS_WORKERS", "").strip()
    if override.isdigit() and int(override) > 0:
        return max(1, min(8, int(override)))
    return max(1, min(4, (os.cpu_count() or 4) // 2))


def threads_per_worker(workers: int) -> int:
    """Split the machine's threads between the parallel workers."""
    return max(1, (os.cpu_count() or 2) // max(1, workers))


def _read_exact(stream, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise RuntimeError("Die Piper-Stimme wurde unerwartet beendet.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _run_piper(text: str) -> bytes:
    """Synthesize one text through the shared process."""
    return _DEFAULT.synthesise(text)


def install_hint() -> str:
    """Copy-paste commands that make the mandatory toolchain available."""
    if os.name == "nt":  # pragma: no cover - platform specific
        venv = str(VENV)
        return (
            "Einmalige Einrichtung (nur dieser Schritt braucht Internet):\n"
            "  py -m venv \"%LOCALAPPDATA%\\ded-tts\\venv\"\n"
            f"  \"{venv}\\Scripts\\pip.exe\" install piper-tts\n"
            f"  \"{venv}\\Scripts\\python.exe\" -m piper.download_voices {VOICE} "
            "--download-dir vendor\\piper\n"
            "  ffmpeg installieren: winget install Gyan.FFmpeg  (oder https://www.gyan.dev/ffmpeg/builds/)\n"
            f"  Falls Python nicht gefunden wird: PIPER_PYTHON=\"{venv}\\Scripts\\python.exe\" setzen"
        )
    return (
        "Einmalige Einrichtung (nur dieser Schritt braucht Internet):\n"
        f"  python3 -m venv {VENV}\n"
        f"  {VENV}/bin/pip install piper-tts\n"
        f"  cd {ROOT} && {VENV}/bin/python -m piper.download_voices {VOICE} --download-dir vendor/piper\n"
        "  sudo apt install ffmpeg   # nur ffmpeg mit libmp3lame wird zusätzlich gebraucht"
    )


def piper_python() -> str | None:
    """Return an interpreter that can ``import piper``, or None."""
    global _PYTHON
    if _PYTHON:
        return _PYTHON

    candidates: list[str] = []
    override = os.environ.get("PIPER_PYTHON", "").strip()
    if override:
        candidates.append(override)
    exe = shutil.which("piper")
    if exe:
        sibling = Path(exe).resolve().with_name("python")
        if sibling.is_file():
            candidates.append(str(sibling))
    candidates += [str(path) for path in PIPER_PYTHONS]
    candidates.append(sys.executable)

    for candidate in dict.fromkeys(candidates):
        try:
            proc = subprocess.run(
                [candidate, "-c", "import piper"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            _PYTHON = candidate
            return _PYTHON
    return None


def bootstrap_voice() -> tuple[bool, str]:
    """Make sure the one permitted voice sits in ``vendor/piper/``.

    We never download inside a build and never substitute another voice: the
    model is copied from a local Piper download directory, exactly like the
    previous voice database was copied from its package.
    """
    if VOICE_MODEL.is_file() and VOICE_MODEL.stat().st_size > 1_000_000 and VOICE_CONFIG.is_file():
        return True, str(VOICE_MODEL)

    for folder in MODEL_SOURCES:
        if all((folder / name).is_file() for name in VOICE_FILES):
            VENDOR_DIR.mkdir(parents=True, exist_ok=True)
            for name in VOICE_FILES:
                tmp = VENDOR_DIR / f"{name}.part"
                shutil.copy2(folder / name, tmp)
                tmp.replace(VENDOR_DIR / name)
            return True, str(VOICE_MODEL)

    return False, (
        f"Stimmmodell {VOICE} fehlt (erwartet: {VOICE_MODEL}).\n" + install_hint()
    )


def sample_rate() -> int:
    """Native sample rate of the voice model."""
    global _RATE
    if _RATE is None:
        try:
            config = json.loads(VOICE_CONFIG.read_text(encoding="utf-8"))
            _RATE = int(config.get("audio", {}).get("sample_rate", 16000))
        except (OSError, ValueError, TypeError):
            _RATE = 16000
    return _RATE


def _worker_env() -> dict[str, str]:
    env = dict(os.environ)
    # The worker protocol is line based UTF-8 on stdin and binary on stdout.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def process_samples(pcm: bytes, rate: int, channels: int = 1) -> array:
    """Trim silence and level the clip; returns 16-bit mono samples.

    Piper keeps a long pause in front of and behind every sentence and does not
    normalise loudness. Trimming makes playback start immediately and peak
    normalisation keeps every clip equally loud. Resampling is left to ffmpeg,
    which writes the mandated 44.1 kHz at the end of the chain anyway.
    """
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])

    if channels > 1:
        frames = len(samples) // channels
        mono = array("h", bytes(2 * frames))
        for i in range(frames):
            base = i * channels
            mono[i] = sum(samples[base:base + channels]) // channels
        samples = mono

    peak = max((abs(x) for x in samples), default=0)
    if peak:
        floor = max(60, int(peak * SILENCE_FLOOR))
        start = 0
        while start < len(samples) and abs(samples[start]) < floor:
            start += 1
        end = len(samples)
        while end > start and abs(samples[end - 1]) < floor:
            end -= 1
        lead = int(rate * LEAD_SILENCE_MS / 1000)
        tail = int(rate * TAIL_SILENCE_MS / 1000)
        trimmed = array("h", bytes(2 * (lead + (end - start) + tail)))
        trimmed[lead:lead + (end - start)] = samples[start:end]
        samples = trimmed

    peak = max((abs(x) for x in samples), default=0)
    if peak:
        scale = (TARGET_PEAK * 32767) / peak
        if abs(scale - 1.0) > 0.001:
            for i in range(len(samples)):
                samples[i] = max(-32768, min(32767, int(samples[i] * scale)))
    return samples


def encode_mp3(pcm: bytes, rate: int, bitrate: str = MP3_BITRATE) -> bytes:
    """Encode raw 16-bit mono PCM with the one mandated MP3 setting."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg wurde nicht gefunden.\n" + install_hint())
    proc = subprocess.run(
        [
            exe, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
            "-c:a", "libmp3lame", "-b:a", bitrate,
            "-ar", str(MP3_SAMPLE_RATE), "-ac", "1",
            "-f", "mp3", "pipe:1",
        ],
        input=pcm,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0 or len(proc.stdout) < 100:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError("MP3-Kodierung fehlgeschlagen: " + (detail or "unbekannter Fehler"))
    return proc.stdout


def mp3_looks_valid(data: bytes) -> bool:
    """True when the bytes start with an ID3 tag or a Layer-III frame sync."""
    if data.startswith(b"ID3"):
        return True
    offset = 0
    while offset + 4 <= len(data) and offset < 4096:
        if data[offset] == 0xFF and data[offset + 1] & 0xE0 == 0xE0:
            return True
        offset += 1
    return False


def probe() -> tuple[bool, str]:
    """Return readiness of the exact required chain, never a fallback."""
    global _PROBE_CACHE
    if _PROBE_CACHE and _PROBE_CACHE[0]:
        return _PROBE_CACHE

    if not shutil.which("ffmpeg"):
        return False, "ffmpeg wurde nicht gefunden.\n" + install_hint()

    ok, voice_detail = bootstrap_voice()
    if not ok:
        return False, voice_detail

    if piper_python() is None:
        return False, "Kein Python mit installiertem Piper gefunden.\n" + install_hint()

    try:
        rate = sample_rate()
        pcm = _run_piper("Test.")
        if len(pcm) < 1000:
            return False, f"{VOICE} lieferte keine verwertbare Ausgabe."
        # Exercise the whole chain: trim/level plus the MP3 encoder.
        encoded = encode_mp3(process_samples(pcm, rate).tobytes(), rate)
        if not mp3_looks_valid(encoded):
            return False, "ffmpeg lieferte kein gültiges MP3."
    except Exception as exc:
        return False, f"{VOICE} konnte nicht synthetisiert werden: {exc}"

    _PROBE_CACHE = (
        True,
        f"{ENGINE} {VOICE} bereit · MP3 {MP3_BITRATE} / {MP3_SAMPLE_RATE} Hz · "
        f"Tempo {LENGTH_SCALE} · Modell: {VOICE_MODEL}",
    )
    return _PROBE_CACHE


def cache_key(text: str) -> str:
    model_sig = "missing"
    if VOICE_MODEL.is_file():
        stat = VOICE_MODEL.stat()
        model_sig = f"{stat.st_size}:{stat.st_mtime_ns}"
    material = (
        f"engine={ENGINE}\nvoice={VOICE}\nmodel={model_sig}\n"
        f"length={LENGTH_SCALE}\nbitrate={MP3_BITRATE}\nrate={MP3_SAMPLE_RATE}\npeak={TARGET_PEAK}\n"
        f"format={FORMAT_VERSION}\n{text}"
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def synthesize_mp3(text: str, cache_dir: Path | None = None) -> bytes:
    """Return one ready-to-embed MP3 clip for ``text``."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("Leerer TTS-Text")
    if len(text) > 2000:
        raise ValueError("TTS-Text ist länger als 2000 Zeichen")

    ok, detail = probe()
    if not ok:
        raise RuntimeError(
            "Pflicht-TTS ist nicht verfügbar: " + detail +
            "\nBenötigt werden Piper mit der Stimme " + VOICE +
            " (CC0 1.0) und ffmpeg. Es gibt absichtlich keinen Ersatz/Fallback."
        )

    try:
        return _render(text, cache_dir, _DEFAULT)
    except RuntimeError as exc:
        raise RuntimeError(f"{VOICE}-Synthese fehlgeschlagen: {exc}") from exc


def _render(text: str, cache_dir: Path | None, process: _PiperProcess) -> bytes:
    """One clip: cache lookup, Piper, trim/level, MP3, cache write."""
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{cache_key(text)}.mp3"
        if cache_path.is_file() and cache_path.stat().st_size > 500:
            data = cache_path.read_bytes()
            if mp3_looks_valid(data):
                return data

    rate = sample_rate()
    samples = process_samples(process.synthesise(text), rate)
    data = encode_mp3(samples.tobytes(), rate)

    if cache_path is not None:
        tmp = cache_path.with_suffix(".mp3.part")
        tmp.write_bytes(data)
        tmp.replace(cache_path)
    return data


def synthesize_many(
    texts: list[str],
    cache_dir: Path | None = None,
    workers: int | None = None,
    progress=None,
) -> dict[str, bytes]:
    """Render many clips, splitting the work over several Piper processes.

    A single Piper process only uses part of the machine; each extra process
    carries its own loaded model and its own slice of the queue, so a full
    rebuild finishes in a fraction of the time. Quality and cache keys are
    untouched: every clip is produced exactly like :func:`synthesize_mp3` does.
    """
    ordered = [str(text or "").strip() for text in texts]
    count = max(1, int(workers or default_workers()))

    if count == 1 or len(ordered) < 2 * count:
        result: dict[str, bytes] = {}
        done = 0
        for text in ordered:
            if not text:
                continue
            result[text] = _render(text, cache_dir, _DEFAULT)
            done += 1
            if progress:
                progress(done, len(ordered))
        return result

    result = {}
    result_lock = threading.Lock()
    counter = {"done": 0}

    def run(queue: list[str]) -> None:
        process = _PiperProcess(threads_per_worker(count))
        try:
            for text in queue:
                if not text:
                    continue
                data = _render(text, cache_dir, process)
                with result_lock:
                    result[text] = data
                    counter["done"] += 1
                    if progress:
                        progress(counter["done"], len(ordered))
        finally:
            process.stop()

    threads = [
        threading.Thread(target=run, args=(ordered[index::count],), daemon=True)
        for index in range(count)
        if ordered[index::count]
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return {text: result[text] for text in ordered if text in result}


def texts_for_entries(themes: list[dict]) -> list[str]:
    """Collect every string the final learning UI can speak.

    The spoken prompt is assembled in the learning UI from two building blocks
    (:data:`PROMPT_PREFIX` + the word clip), so the prefix is rendered once for
    all words instead of once per word. The second prompt ("Hör noch einmal")
    reuses the same clip — it only differs in the text shown on screen.
    """
    seen: set[str] = set()
    out: list[str] = []

    def add(value: str) -> None:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)

    for theme in themes:
        for row in theme.get("entries", []):
            for part in prompt_parts(row.get("word", "")):
                add(part)
            add(row.get("accusativeSentence", ""))
            add(row.get("dativeSentence", ""))
            add(plural_phrase(row))
    return out


def plural_phrase(row: dict) -> str:
    """The plural form the plural task shows and speaks ("die Bären.")."""
    phrase = str(row.get("pluralWithArticle", "")).strip()
    if not phrase:
        plural = str(row.get("plural", "")).strip()
        phrase = f"die {plural}" if plural else ""
    if not phrase:
        return ""
    return phrase if phrase.endswith(".") else phrase + "."


def word_clip(word: str) -> str:
    """The word as its own clip, with a final period for a closed intonation."""
    clean = str(word or "").strip()
    if not clean:
        return ""
    return clean if clean.endswith(".") else clean + "."


def prompt_parts(word: str) -> list[str]:
    """Building blocks of the spoken prompt: fixed prefix, then the word."""
    clip = word_clip(word)
    return [PROMPT_PREFIX, clip] if clip else []
