# Local embedding runtime for the video

`embedding_server.py` uses the existing `mlx-lm` environment and the installed
`~/Models/Qwen3-Embedding-8B-4bit-DWQ` weights. It is a demo runtime adapter,
separate from the application source. It exposes the OpenAI-shaped embeddings
endpoint required by ClaimCoach's corpus importer.

The installed `mlx_lm.server` exposes text completion, not embeddings. This
adapter runs the Qwen3 transformer body, pools its final token, and normalizes
4096-dimensional float vectors. It processes documents one by one without
padding or a chat template. This follows the
[official Qwen embedding inference recipe](https://huggingface.co/Qwen/Qwen3-Embedding-8B#transformers-usage).
Local model files are required and Hugging Face offline mode is enabled.

```sh
~/Models/.venvs/mlx-lm/bin/python docs/video-artifacts/runtime/embedding_server.py \
  --model ~/Models/Qwen3-Embedding-8B-4bit-DWQ --port 18203
```

When the ClaimCoach worker owns this process, use that worker's model lifecycle;
do not start a second server on the port. Health endpoints are `/health`,
`/healthz`, and `/v1/models`. Requests go to `/v1/embeddings` and use `input` as one
string or up to 32 strings. Inputs beyond 8192 tokens are refused, not truncated.
Only `127.0.0.1` binding is supported. Request bodies and errors are not logged.

To repeat the functional check against a running server:

```sh
.venv/bin/python docs/video-artifacts/runtime/verify_embeddings.py
```

`embedding-validation.json` records the executed real-model check: output shape,
unit norms, identical-input consistency and a related/unrelated semantic
comparison. It is a smoke check, not an embedding-quality benchmark.
