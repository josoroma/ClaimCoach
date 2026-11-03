#!/usr/bin/env python3
"""Validate local narration WAVs and transcribe them with local Whisper.

ASR is a review aid: proper names and command spellings may differ from speech.
It does not prove voice quality or correctness by itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import wave


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def distance(a: list[str], b: list[str]) -> int:
    row = list(range(len(b) + 1))
    for i, aw in enumerate(a, 1):
        nxt = [i]
        for j, bw in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (aw != bw)))
        row = nxt
    return row[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--whisper-model", type=Path,
                        default=Path.home() / "Models/faster-whisper-base.en")
    parser.add_argument("--only")
    args = parser.parse_args()
    import numpy as np
    from faster_whisper import WhisperModel
    manifest = json.loads((args.directory / "manifest.json").read_text())
    model = WhisperModel(str(args.whisper_model), device="cpu", compute_type="int8",
                         local_files_only=True, cpu_threads=2)
    target = args.directory / "verification.json"
    results = json.loads(target.read_text()) if target.exists() else {"scenes": {}}
    results.update({"engine": "faster-whisper", "model": str(args.whisper_model),
                    "language": "en", "purpose": "Offline ASR round-trip and waveform validation"})
    for scene_id, entry in manifest["scenes"].items():
        if args.only and args.only != scene_id:
            continue
        path = args.directory / entry["file"]
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        existing = results["scenes"].get(scene_id)
        if existing and existing["sha256"] == sha:
            continue
        with wave.open(str(path)) as wav:
            channels, rate, width = wav.getnchannels(), wav.getframerate(), wav.getsampwidth()
            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float) / 32768
        if channels != 1 or rate != 24000 or width != 2 or not samples.size:
            raise ValueError(f"Unexpected WAV format for {scene_id}")
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if not np.isfinite(samples).all() or rms < 0.001:
            raise ValueError(f"Silent or invalid waveform for {scene_id}")
        pieces, info = model.transcribe(str(path), language="en", beam_size=5)
        transcript = [{"start": p.start, "end": p.end, "text": p.text.strip()} for p in pieces]
        text = " ".join(p["text"] for p in transcript)
        expected = words(entry["text"])
        results["scenes"][scene_id] = {
            "file": path.name, "sha256": sha, "format": "PCM signed 16-bit mono 24 kHz",
            "duration": len(samples) / rate, "rms": rms, "peak": float(np.max(np.abs(samples))),
            "clip_fraction": float(np.mean(np.abs(samples) >= 32767 / 32768)),
            "expected": entry["text"], "transcript": text, "segments": transcript,
            "word_error_rate": distance(expected, words(text)) / len(expected),
        }
        target.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps({"scene": scene_id, "transcript": text,
                          "word_error_rate": results["scenes"][scene_id]["word_error_rate"]}), flush=True)


if __name__ == "__main__":
    main()
