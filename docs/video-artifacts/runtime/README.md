# Local ClaimCoach demonstration workspace

The dedicated workspace is `.local/hermes`; Desktop state is `.local/desktop`. Both are ignored by Git. It uses the existing stable Hermes v0.22.6 source installation and the packaged Desktop built from commit `f0d94882e89ab8d4098b5bb2f166adfb9ee0a0ab`. `hermes update --check` reported the latest stable release already installed on 2 November 2026.

From the ClaimCoach repository:

```sh
python3 docs/video-artifacts/runtime/workspace.py start
```

This verifies the existing Bonsai server, starts ClaimCoach's worker and opens its dedicated Desktop. The source launcher is `~/.local/bin/hermes`. `/Applications/Hermes.app` is a bootstrap installer on this machine, so the launcher opens the actual packaged app under `~/.hermes/hermes-agent/apps/desktop/release/mac-arm64/`.

The main model server is shared with the existing Legalizer workspace at `127.0.0.1:8080/v1`. Its current authentication file remains at `~/sites/legalizer/.local/model/api-key`. No key appears in these artifacts or command arguments. This demo depends on that server being available; it does not start or stop Legalizer. The ClaimCoach adapter starts on demand at `127.0.0.1:18206`, rewrites only the model identifier, forwards actual inference and reads the existing credential locally.

The installed ternary Bonsai 27B weights serve the text roles: classification, explanation, drafting and PHI detection. This is a demo registry override; it is not validation of the default Qwen text-role configuration. The real Qwen3 Embedding 8B model serves corpus import at port 18203. The runtime adapter supplies the embeddings endpoint missing from the configured `mlx_lm.server`. See [embedding validation](EMBEDDINGS.md).

The Qwen vision and Voxtral transcription weights are absent. The demonstration therefore uses deterministic 835 text intake, not PDF/image OCR or payer-call transcription. Model routing has no configured cloud fallback; [the route audit](../local-routing.json) is a configuration check, not an egress certification.

Run worker and plugin commands in the same workspace:

```sh
python3 docs/video-artifacts/runtime/workspace.py make worker-health
python3 docs/video-artifacts/runtime/workspace.py make models-status
python3 docs/video-artifacts/runtime/workspace.py hermes plugins doctor claimcoach
python3 docs/video-artifacts/runtime/workspace.py make corpus-import FILE=docs/video-artifacts/demo-inputs/isolated-demo-corpus.json
python3 docs/video-artifacts/runtime/workspace.py make models-unload ROLE=embedding
```

Unload embeddings after import on this 36 GiB Mac. The initial draft attempt encountered MTPLX memory pressure while the embedding model and narration process were resident; the retry completed after the unused embedding model was unloaded. This is a measured limitation of the demonstrated run.

`workspace.py init` preserves an existing configuration. Recreating it requires the ClaimCoach worker venv (`make worker-venv`) and the already installed model runtimes. Case data is stored by the actual worker; no case database or model output was fabricated.
