#!/usr/bin/env python3
"""Keep one Piper voice loaded and synthesise every text in a single process.

The project itself only uses the standard library, so Piper runs in a separate
virtual environment. One Piper CLI call per clip would reload the ONNX model
every time (about two seconds); this worker loads it once and reads texts from
stdin instead.

Protocol (binary, on stdout), one frame per input line:

    <4-byte little-endian length><16-bit mono PCM>

An error frame carries the payload length with the high bit set and a UTF-8
message as payload, so the caller can report what went wrong without mixing
diagnostics into the audio stream. Several workers may run side by side; then
``--threads`` caps each one so they share the CPU instead of fighting for it.

This file is executed by the Piper interpreter, never by the project itself.
"""
from __future__ import annotations

import argparse
import io
import struct
import sys
import wave

ERROR_FLAG = 0x80000000


def limit_threads(count: int) -> None:
    """Cap ONNX Runtime's thread pools in this process.

    Piper builds its session with default options, so every worker would use
    one pool per physical core. Several workers in parallel would oversubscribe
    the CPU; capping each one keeps the total within the machine's threads.
    """
    import onnxruntime  # noqa: PLC0415 - only exists in the Piper environment

    original = onnxruntime.InferenceSession

    def limited(*args, **kwargs):
        options = kwargs.get("sess_options") or onnxruntime.SessionOptions()
        options.intra_op_num_threads = count
        options.inter_op_num_threads = 1
        kwargs["sess_options"] = options
        return original(*args, **kwargs)

    onnxruntime.InferenceSession = limited


def synthesise(voice, text: str, syn_config=None) -> bytes:
    """Return 16-bit mono PCM for one text."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config)
    buffer.seek(0)
    with wave.open(buffer, "rb") as wav:
        if wav.getsampwidth() != 2:
            raise RuntimeError("Piper lieferte kein 16-Bit-Audio")
        return wav.readframes(wav.getnframes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Piper batch worker")
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", default=None)
    # Optional prosody knobs; without them the voice model's own defaults apply.
    parser.add_argument("--length-scale", type=float, default=None)
    parser.add_argument("--noise-scale", type=float, default=None)
    parser.add_argument("--noise-w-scale", type=float, default=None)
    # 0 = leave ONNX Runtime's default (one thread pool per core).
    parser.add_argument("--threads", type=int, default=0)
    args = parser.parse_args()

    if args.threads > 0:
        limit_threads(args.threads)

    from piper import PiperVoice  # noqa: PLC0415 - only exists in the Piper environment

    voice = PiperVoice.load(args.model, args.config)

    syn_config = None
    if (args.length_scale, args.noise_scale, args.noise_w_scale) != (None, None, None):
        from piper.config import SynthesisConfig  # noqa: PLC0415

        # Not given options stay None, so the voice model's own defaults apply.
        syn_config = SynthesisConfig(
            length_scale=args.length_scale,
            noise_scale=args.noise_scale,
            noise_w_scale=args.noise_w_scale,
        )

    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", newline="\n")
    out = sys.stdout.buffer
    for line in stdin:
        text = line.rstrip("\r\n")
        try:
            pcm = synthesise(voice, text, syn_config) if text else b""
            frame = struct.pack("<I", len(pcm)) + pcm
        except Exception as exc:  # keep the worker alive for the remaining clips
            message = f"{type(exc).__name__}: {exc}".encode("utf-8")
            frame = struct.pack("<I", ERROR_FLAG | len(message)) + message
        out.write(frame)
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
