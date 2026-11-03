#!/usr/bin/env python3
"""Encode scene WAVs from cached, unclipped floats with conservative peak gain.

Durations and pauses remain identical. Chatterbox's embedded watermark is not
removed; this applies only a uniform gain before ordinary PCM encoding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import wave


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--peak", type=float, default=0.97)
    args = parser.parse_args()
    if not 0.1 <= args.peak <= 0.99:
        parser.error("--peak must be between 0.1 and 0.99")
    import numpy as np

    path = args.directory / "manifest.json"
    manifest = json.loads(path.read_text())
    sample_rate = manifest["sample_rate"]
    for scene_id, entry in manifest["scenes"].items():
        cache = args.directory / "segments" / f"{scene_id}-{entry['generation_key'][:16]}"
        pieces = []
        for i, chunk in enumerate(entry["segments"]):
            samples = np.load(cache / f"{i:02d}.npy", allow_pickle=False)
            if abs(len(samples) / sample_rate - chunk["duration"]) > 0.0001:
                raise ValueError(f"Cached duration mismatch: {scene_id}/{i}")
            pieces.append(samples)
            if i < len(entry["segments"]) - 1:
                pieces.append(np.zeros(round(sample_rate * 0.12), dtype=np.float32))
        samples = np.concatenate(pieces)
        if not samples.size or not np.isfinite(samples).all():
            raise ValueError(f"Invalid samples: {scene_id}")
        source_peak = float(np.max(np.abs(samples)))
        gain = min(1.0, args.peak / source_peak) if source_peak else 1.0
        samples = samples * gain
        pcm = (samples * 32767).round().astype("<i2")
        output = args.directory / entry["file"]
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(sample_rate)
            target.writeframes(pcm.tobytes())
        entry.update({
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "source_peak": source_peak,
            "peak": float(np.max(np.abs(samples))),
            "rms": float(np.sqrt(np.mean(samples ** 2))),
            "normalization": {"method": "uniform gain from cached float source", "target_peak": args.peak, "gain": gain},
        })
        print(json.dumps({"scene": scene_id, "source_peak": source_peak, "gain": gain, "peak": entry["peak"]}))
    manifest["normalization"] = f"All scene WAVs encoded from unclipped cached floats; uniform gain only; peak at most {args.peak}"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
