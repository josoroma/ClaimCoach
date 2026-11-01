# Runbook: evals and release gates

Covers US-12.1 (the redactor's PHI recall on the synthetic set, release-blocking at 98%), US-12.2
(denial-classification accuracy, 85%; appeal drafts accepted with only minor edits, 70%), US-12.3
(the median upload-to-draft time on this Mac, at most 10 minutes), and US-12.4 (a full case flow
opens no connection beyond loopback). Each eval drives the running worker and its real local
models through the same REST routes the pane uses, then writes a JSON report as evidence:

| Command | Report | Target |
| --- | --- | --- |
| `make eval-redaction` | `evidence/US-12.1/redaction-recall.json` | recall ≥ 0.98 (per category reported) |
| `make eval-classification` | `evidence/US-12.2/classification-accuracy.json` | accuracy ≥ 0.85 |
| `make eval-drafts REVIEWS=…` | `evidence/US-12.2/draft-acceptance.json` | ≥ 0.70 accepted with minor edits |
| `make eval-latency` | `evidence/US-12.3/latency.json` | median ≤ 600 s, every case finished |
| `make eval-egress` | `evidence/US-12.4/egress.json` | flow completed, 0 non-loopback findings |

`python -m claimcoach.evals` exits **0** when its target is met, **1** when it is missed (the
release is blocked), and **2** when nothing was measured (the worker is down, an eval set does not load, a
case model's weights are missing, a download is running, or `lsof` failed). A report holds eval-set
IDs, categories, codes, and numbers only: never a PHI value, a document, or a letter (BR-14).
Through `make`, any failure exits 2 (make's own code); the eval's code is the one in make's
`Error 1` / `Error 2` line, and the verdict is the command's first line (`PASS`, `BLOCKED`, or
`not measured: …`).

Eval sets:

- `tests/fixtures/phi/phi_set.json`: 12 synthetic documents seeded with names, DOB, MRN, member
  ID, SSN, address, and phone (US-3.1; `make phi-fixtures` regenerates it).
- `tests/fixtures/denials/denial_set.json`: 20 synthetic denial cases, two per denial family,
  each denied under a reason code that `REASON_GUIDE` lists for its label; 7 pasted 835s, 7 letter
  uploads, 6 EOB PDFs (`uv run python -m tests.fixtures.denials.generate` regenerates it). A
  partner's labeled de-identified set with the same schema replaces it: `DENIAL_SET=path`.
- The manager's draft reviews (`REVIEWS=path`): a JSON object
  `{"name", "provenance", "reviews": [{"id", "denial_reason", "draft", "final"}]}` with each
  model draft (before any edit) next to the letter the manager approved, de-identified. The
  rubric: a draft is accepted with minor edits when the approved letter keeps at least 85% of its
  words in order and at least 85% of the approved letter is the draft's words. `make evals`
  without `REVIEWS` counts this gate as not measured, which blocks the release.

## Preconditions

- The worker is running with the real models and was started after this release's code was
  installed (`make stop`, then `make start`: an older worker has no egress audit, and
  `make eval-egress` refuses it). `make start`, then `make models-check` lists every
  role except `transcription` with `weights present`. `make models-status` shows no role
  `downloading`; do not run a corpus import meanwhile (the egress check refuses to
  run during a download, and an import is the other sanctioned way out, BR-1).
- The global corpus holds the code notes, rule cards, and letter templates the pipeline uses
  (`make corpus-list`); without a template every draft fails `no_letter_template`.
- ClaimCoach runs alone on the Mac (the latency benchmark measures it, BR-12), and `lsof` is at
  `/usr/sbin/lsof` (`make doctor`).
- Eval cases are created in a profile's user scope and purged as soon as each flow ends; the case
  rows and audit entries stay, as for any purge. Use a dedicated Hermes profile for evals
  (`EVAL_PROFILE=claimcoach-evals` for classification and latency; the egress check runs in the
  active profile, so set `HERMES_HOME` to that profile's home for it).

## Steps

The PHI recall gate (minutes):

```bash
make eval-redaction
```

Classification accuracy and the latency benchmark (each runs every case through upload,
extraction, and diagnosis; latency also drafts; `LIMIT=n` runs fewer, round-robin by kind):

```bash
make eval-classification EVAL_PROFILE=claimcoach-evals
```

```bash
make eval-latency EVAL_PROFILE=claimcoach-evals LIMIT=6
```

Draft acceptance, from the manager's review file:

```bash
make eval-drafts REVIEWS=~/ClaimCoach-reviews/2026-10.json
```

The zero-egress check (one case from upload through export; `EVAL_CASE=denial_001` picks another):

```bash
make eval-egress
```

Everything a release needs, in order: `make verify` (offline), then every gate; every gate runs
even after one misses, and the last line names the ones that blocked:

```bash
make release-gate REVIEWS=~/ClaimCoach-reviews/2026-10.json
```

## Verification

- Each command's first line is the verdict (`PASS` or `BLOCKED`) with the measured value and the
  target; the following lines give it per category (PHI category, denial reason), per case
  (latency: seconds or the error code), or per finding (egress: source, process, PID, address).
- The report exists and says the same:

  ```bash
  python3 -m json.tool evidence/US-12.1/redaction-recall.json | head -20
  ```

- `make evals` ends with `every eval gate passed: …` or `release blocked by: …`.
- No eval case is left with content: `make case-list PROFILE=claimcoach-evals` shows the run's
  cases with no documents. A command that could not purge one names it:
  `warning: eval case case_… could not be purged: make corpus-purge PROFILE=… CASE=… CONFIRM=yes`.
- `worker/egress.jsonl` under the plugin data dir (`~/.hermes/plugin-data/claimcoach/worker/`)
  lists every non-loopback attempt the worker ever made, one JSON record per line (time, process,
  PID, event, host, port). Outside a confirmed download it stays empty. The egress report's
  `observers` say what watched each process: the worker by its audit hook and `lsof`, each model
  server by `lsof` only (a DNS lookup or a connection between two samples of a model server is not
  seen; the servers run with `HF_HUB_OFFLINE=1`).

## Rollback

- The evals change nothing but evidence files and their own eval cases. To discard a run's
  reports: `git checkout -- evidence/US-12.1 evidence/US-12.2 evidence/US-12.3 evidence/US-12.4`.
- Ctrl-C purges the running eval case before the command stops. A case left with content anyway
  (the worker stopped first) is named by the warning above:
  `make corpus-purge PROFILE=<profile> CASE=<id> CONFIRM=yes` (see [phi-purge](phi-purge.md)).
- A blocked gate is not rolled back: fix the cause (a model change, a prompt, a missing corpus
  item) and run the gate again. A finding in `make eval-egress` is a PHI incident until shown
  otherwise: stop the worker (`make stop`) and follow [phi-incident](phi-incident.md).
- `worker/egress.jsonl` may be deleted while the worker is stopped; it is recreated (mode 0600)
  on the next attempt.
