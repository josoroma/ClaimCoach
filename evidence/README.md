# Delivery evidence

Each delivered story writes `evidence/US-x.y/` (ES-5):

- `test-report.md`, copied from [`TEMPLATE/test-report.md`](TEMPLATE/test-report.md);
- `junit.xml` from `make evidence STORY=US-x.y` (and `junit-node.xml` when the story has
  `node --test` cases);
- eval JSON, for model-quality stories (EPIC-12).

## Results

| Result | Meaning |
| --- | --- |
| `PASS` | The criterion was exercised by a named test or command, and the observed output matches the Gherkin `Then`. |
| `FAIL` | It was exercised and the output did not match. The verdict is `fail` and the change returns to the Implementer. |
| `UNVERIFIED` | It was **not** exercised: no executable check, missing dependency, or only partly covered. Say why in Notes. Never write `PASS` for something you did not run. |

`Coverage: n/m` counts the rows that are `PASS` or `FAIL` (`n`) against all rows (`m`).

## Checking reports

```bash
make evidence-check
```

This runs [`tools/check_evidence.py`](../tools/check_evidence.py) on every `US-x.y` folder, then
OhMyOrch's `validate-test-report` on each report when OhMyOrch is installed.
