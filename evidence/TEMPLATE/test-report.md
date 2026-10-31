# Test Report: <US-x.y> <story title>

Change: <change-id>
Story: <US-x.y>
Verdict: <pass | fail>
Coverage: <evaluated>/<total> acceptance criteria evaluated
Date: <YYYY-MM-DD>
Tester: <who ran the checks>
Environment: <machine, OS, Python, Node, Hermes version>

## Acceptance Criteria Evaluated

Quote each Gherkin scenario from SPECS.md. `Result` is `PASS`, `FAIL`, or `UNVERIFIED`. A criterion
that was not exercised is `UNVERIFIED`, never `PASS`.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "<Scenario name>: <Then clause>" | <PASS/FAIL/UNVERIFIED> | `<test id or command>` → <observed output> |

## Evidence Commands

```bash
<the exact commands that were run>
```

```text
<their actual output, trimmed to the relevant lines>
```

Artifacts: `evidence/<US-x.y>/junit.xml`

## Failures

<None, or for each FAIL: the criterion, what was observed, what was expected. A FAIL returns the
change to the Implementer, and any code change is reviewed again before retesting.>

## Notes

<UNVERIFIED reasons, environment caveats, open questions.>
