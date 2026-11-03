# English narration

This pipeline uses the requested **Chatterbox Multilingual V3** checkpoint at
`~/Models/chatterbox-multilingual-v3`, explicitly selected with `t3_model="v3"`.
It uses the bundled `conds.pt` synthetic voice, with no reference recording or
voice cloning. Generation is local, with Hugging Face network access disabled.
Chatterbox's PerTh watermark is retained in the generated audio samples.

```sh
~/Models/.venvs/mentor-chatterbox/bin/python \
  docs/video-artifacts/audio/generate_narration.py \
  docs/video-artifacts/film/script.en.json --language en --device cpu \
  --output docs/video-artifacts/audio/en

~/Models/.venvs/mentor-chatterbox/bin/python \
  docs/video-artifacts/audio/normalize_audio.py docs/video-artifacts/audio/en
```

Input is a list of `id` / `narration` objects or an object containing that list
under `scenes`. Output is one 24 kHz mono PCM WAV per scene and `manifest.json`,
recording the exact text, model revision, runtime versions, seed, generation
parameters, duration, waveform statistics, and SHA-256 hashes. Completed scenes
and sentence chunks are cached; text and generation settings form the cache key.
Use `--only ID` for a single scene and `--replace` to regenerate cached audio.
The normalization pass reconstructs the WAVs from unclipped cached floating-point
samples and applies uniform gain when needed to keep peaks at or below 0.97.
It preserves timing, records the gain and original peak, and updates file hashes.
Run it after all generation has finished, then run the verifier on those WAVs.

CPU is used to leave the GPU available for the ClaimCoach language model. The
installed runtime supports MPS, but earlier local production notes report memory
pressure during long MPS generation. No new environment or model download is
required. Seeds record configuration; exact bytes across devices are not promised.

```sh
~/Models/.venvs/mentor-chatterbox/bin/python \
  docs/video-artifacts/audio/generate_narration.py \
  docs/video-artifacts/audio/smoke-en.json --language en --device cpu \
  --output docs/video-artifacts/audio/smoke-en-cpu

~/Models/.venvs/mentor-speech/bin/python \
  docs/video-artifacts/audio/verify_audio.py docs/video-artifacts/audio/en
```

The verifier uses local `faster-whisper-base.en` and writes `verification.json`
with decoded text and waveform checks. ASR is a review aid; proper names and
command spellings can differ from the narration script.

Installed runtime: Python 3.12, PyTorch/Torchaudio 2.6.0, NumPy 1.26.4,
`chatterbox-tts` 0.1.7. Model metadata records `ResembleAI/chatterbox` revision
`5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18`.

The English CPU smoke test produced a valid 5.84-second WAV in 24.23 seconds
of generation (excluding model loading). Its local ASR transcript recovered the
sentence but misrecognized the product name and "helps billers". That result is
retained in `smoke-en-cpu/verification.json`; it is diagnostic audio, not a film
scene. Final scene narration receives separate verification.

All ten final scene WAVs are in `en/`: **114.76 seconds of English narration**
before film pauses. `en/verification-summary.json` records script consistency,
file hashes, PCM format and measured durations. `en/verification.json` contains
the local ASR review. The peak normalization pass was completed from the cached
unclipped source samples; no delivered scene WAV contains clipped samples.

Sources: [Chatterbox repository](https://github.com/resemble-ai/chatterbox),
[model card](https://huggingface.co/ResembleAI/chatterbox). Runtime behavior was
checked against the installed `chatterbox/mtl_tts.py` before generating audio.
