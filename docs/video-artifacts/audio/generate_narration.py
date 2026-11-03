#!/usr/bin/env python3
"""Render scene narration offline with the installed Chatterbox Multilingual V3.

Input: [{"id": "01-intro", "narration": "..."}, ...] or {"scenes": [...]}.
WAV files preserve the model's PerTh-watermarked samples (16-bit PCM encoding).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import re
import time
import wave


def segments(text: str, limit: int) -> list[str]:
    remaining = " ".join(text.split())
    result = []
    while len(remaining) > limit:
        window = remaining[:limit]
        stops = [m.end() for m in re.finditer(r'[.!?][\"”’)]*\s+', window)]
        spaces = [m.end() for m in re.finditer(r'\s+', window)]
        boundary = stops[-1] if stops else spaces[-1] if spaces else limit
        result.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        result.append(remaining)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    parser.add_argument("--model", type=Path, default=Path.home() / "Models/chatterbox-multilingual-v3")
    parser.add_argument("--device", choices=("mps", "cpu"), default="cpu")
    parser.add_argument("--language", default="en")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--segment-limit", type=int, default=180)
    parser.add_argument("--only", help="One scene ID to generate")
    parser.add_argument("--replace", action="store_true", help="Replace existing matching audio")
    args = parser.parse_args()
    if not 30 <= args.segment_limit <= 240:
        parser.error("--segment-limit must be between 30 and 240")
    source = json.loads(args.script.read_text())
    scenes = source["scenes"] if isinstance(source, dict) else source
    if args.only:
        scenes = [s for s in scenes if str(s["id"]) == args.only]
        if not scenes:
            parser.error("Requested scene ID was not found")
    args.output.mkdir(parents=True, exist_ok=True)
    model_path = args.model.expanduser().resolve()
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      PKUSEG_HOME=str(model_path / "pkuseg"), PYTORCH_ENABLE_MPS_FALLBACK="1")
    import numpy as np
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    started = time.monotonic()
    engine = ChatterboxMultilingualTTS.from_local(str(model_path), device=args.device, t3_model="v3")
    if engine.conds is None:
        raise RuntimeError("The model's bundled conds.pt default voice is required")
    print(json.dumps({"event": "loaded", "device": args.device, "seconds": round(time.monotonic()-started, 2)}), flush=True)
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update({"engine": "Chatterbox Multilingual V3", "model": str(model_path),
                     "revision": (model_path / "mentor-model-revision.txt").read_text().strip(),
                     "runtime": {name: importlib.metadata.version(name) for name in ("torch", "torchaudio", "numpy", "chatterbox-tts")},
                     "voice": "Bundled conds.pt default voice; no reference audio or voice cloning",
                     "language": args.language, "device": args.device, "seed": args.seed,
                     "parameters": {"exaggeration": 0.5, "cfg_weight": 0.0, "temperature": 0.8},
                     "watermark": "PerTh watermark retained from model output", "sample_rate": engine.sr})
    manifest.setdefault("scenes", {})
    for scene in scenes:
        scene_id = str(scene["id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", scene_id):
            raise ValueError("Scene IDs may contain only letters, digits, underscores and hyphens")
        text = scene.get("narration", scene.get("text", "")).strip()
        if not text:
            raise ValueError(f"Missing narration for {scene_id}")
        script_hash = hashlib.sha256(text.encode()).hexdigest()
        generation_key = hashlib.sha256(json.dumps({
            "text": text, "language": args.language, "model": str(model_path),
            "revision": manifest["revision"], "seed": args.seed, "device": args.device,
            "segment_limit": args.segment_limit, "parameters": manifest["parameters"],
        }, sort_keys=True).encode()).hexdigest()
        scene_seed = args.seed + int(hashlib.sha256(scene_id.encode()).hexdigest()[:6], 16)
        output = args.output / f"{scene_id}.wav"
        existing = manifest["scenes"].get(scene_id)
        if not args.replace and output.exists() and existing and existing.get("generation_key") == generation_key:
            print(json.dumps({"event": "reused", "id": scene_id}), flush=True)
            continue
        chunks = segments(text, args.segment_limit)
        arrays, chunk_info = [], []
        chunk_cache = args.output / "segments" / f"{scene_id}-{generation_key[:16]}"
        chunk_cache.mkdir(parents=True, exist_ok=True)
        scene_started = time.monotonic()
        for chunk_index, chunk in enumerate(chunks):
            cached = chunk_cache / f"{chunk_index:02d}.npy"
            if cached.exists() and not args.replace:
                samples = np.load(cached, allow_pickle=False)
            else:
                torch.manual_seed(scene_seed + chunk_index)
                audio = engine.generate(chunk, language_id=args.language, exaggeration=0.5, cfg_weight=0.0, temperature=0.8)
                samples = audio.detach().cpu().numpy().reshape(-1)
            if not samples.size or not np.isfinite(samples).all():
                raise RuntimeError(f"Invalid waveform for {scene_id}")
            if not cached.exists() or args.replace:
                np.save(cached, samples, allow_pickle=False)
            arrays.append(samples)
            chunk_info.append({"text": chunk, "duration": round(len(samples)/engine.sr, 4)})
            if chunk_index < len(chunks)-1:
                arrays.append(np.zeros(round(engine.sr * 0.12), dtype=np.float32))
            print(json.dumps({"event": "segment", "id": scene_id, "index": chunk_index+1, "of": len(chunks), "duration": chunk_info[-1]["duration"]}), flush=True)
        samples = np.concatenate(arrays)
        pcm = (np.clip(samples, -1, 1)*32767).round().astype("<i2")
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(engine.sr)
            target.writeframes(pcm.tobytes())
        manifest["scenes"][scene_id] = {"file": output.name, "text": text, "text_sha256": script_hash, "generation_key": generation_key,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "duration": round(len(samples)/engine.sr, 4),
            "rms": float(np.sqrt(np.mean(samples**2))), "peak": float(np.max(np.abs(samples))), "scene_seed": scene_seed,
            "segments": chunk_info, "generation_seconds": round(time.monotonic()-scene_started, 2)}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
        print(json.dumps({"event": "saved", "id": scene_id, "file": str(output), "duration": manifest["scenes"][scene_id]["duration"]}), flush=True)


if __name__ == "__main__":
    main()
