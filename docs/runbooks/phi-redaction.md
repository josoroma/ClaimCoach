# Runbook: PHI redaction (detector, validators, second pass)

Covers US-3.1 (and the guard that uses it in US-3.2). The redactor runs inside the worker:
Qwen3-8B (`phi_detection` role, port 18202) proposes name/address/other spans, the regex
validators add SSN, MRN, DOB, phone, and member ID, and a second pass re-checks the output.
Nothing here sends text off the Mac (BR-1, BR-2).

## Preconditions

- The worker is running: `make start` (see [worker-start-stop-health](worker-start-stop-health.md)).
- `Qwen3-8B-4bit` is under `MODELS_HOME` and the `mlx-lm` venv exists: `make models-check` shows
  `phi_detection ... present  venv ok`. If not, follow
  [model-download-convert](model-download-convert.md) (`make models-download ROLE=phi_detection CONFIRM=yes`).
- A text file to check. Use the synthetic set (`tests/fixtures/phi/phi_set.json`) rather than
  real patient documents whenever possible.

## Steps

1. Check the setup without changing anything:

   ```bash
   make doctor
   ```

2. Redact a file through the running worker (prints only the redacted text, then per-category
   counts on stderr):

   ```bash
   make redact FILE=/path/to/note.txt
   ```

3. Run the offline redaction tests (fake model; no weights needed):

   ```bash
   make test-story STORY=US-3.1
   ```

4. Run the real-model test against Qwen3-8B (skips when the weights are missing):

   ```bash
   make test-models
   ```

5. After changing the fixture generator, regenerate and commit the fixture set:

   ```bash
   make phi-fixtures
   ```

## Verification

- Step 2 prints placeholders such as `[NAME]`, `[DOB]`, `[SSN]` where the PHI was, and the
  counts line lists the categories found. Denial codes (CARC/RARC) and claim numbers remain.
- A failure prints the error envelope instead of text: `model_unavailable` (model missing or not
  healthy), `model_busy` (memory guard queue), or `redaction_failed` (the model's reply was not
  usable). In every failure case no unredacted text is returned.
- Step 4 reports `test_us_3_1_spans_carry_category PASSED` (or `SKIPPED` with the missing path).

## Rollback

- Redaction has no state to roll back: it writes nothing to disk.
- If a model change breaks redaction (`redaction_failed` on every call), restore the previous
  `phi_detection` entry in `<hermes root>/plugin-data/claimcoach/models.yaml` and restart the
  worker: `make stop && make start`.
- If PHI was seen in any output, stop and follow [phi-incident](phi-incident.md).
