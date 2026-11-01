# Test Report: US-13.5 Product README for Y Combinator

Change: us-13-5-product-readme
Story: US-13.5
Verdict: pass
Coverage: 6/6 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 for `make validate`; no live Hermes Desktop

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "README.md is the product page: Then it shows the shared logo, the problem, who it is for, what it does, the v1 targets, and the privacy promise" | PASS | `test_us_13_5_readme_is_product_page`: the sections The problem, What ClaimCoach does, Who it's for, Why it runs on the Mac, v1 targets, and Status are non-empty; "PHI never leaves the Mac" is stated; `test_us_13_5_readmes_share_logo_and_links_resolve[README.md]` finds the shared logo |
| 2 | "README.md is the product page: And it shows the user flow diagram" | PASS | Same test: the image `docs/assets/flow-user.svg` with its alt text |
| 3 | "README.md is the product page: And it has no install or engineering steps, and links README-DEV.md for them" | PASS | Same test: no fences, no indented code blocks, no inline span that starts with a command word; links `README-DEV.md`. The status names what is not verified |
| 4 | "The product claims come from the PRD: Then each target equals the PRD's" | PASS | `test_us_13_5_targets_match_prd`: the README's v1 targets table equals PRD §4's five rows word for word (goal, metric, target) |
| 5 | "Every README uses the shared logo: Then it references plugin/assets/claimcoach-logo.svg" | PASS | `test_us_13_5_readmes_share_logo_and_links_resolve` for README.md and README-DEV.md: the only image whose path or alt says logo is `plugin/assets/claimcoach-logo.svg` (`test_us_13_5_images_finds_every_logo` covers Markdown and `<img>` forms) |
| 6 | "Every README uses the shared logo: And every relative link in it resolves to a file in the repository" | PASS | Same test: `broken_links` is empty for both READMEs. It resolves inside the repository with exact case and checks anchors in the same and other Markdown files; `test_us_13_5_link_check_finds_broken_links` shows a missing anchor, a fenced pseudo-heading, a missing file, a renamed cross-file heading, a path outside the root, a case mismatch, an `<img>`, and a reference-style link each reported |

## Evidence Commands

```bash
make evidence STORY=US-13.5
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
====================== 7 passed, 1819 deselected in 1.39s ======================
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 250.31s (0:04:10) ================
ℹ tests 191
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-13.5/junit.xml`

## Failures

None.

## Notes

- How GitHub renders the page was not seen; links are checked with GitHub's anchor rule.
- Review fixes (see review.md): the status now says no feature has run against the real local models or a live Hermes Desktop, the outbound-calls sentence names what the chat agent receives, the corrected claim is described as a list of corrections, the targets are PRD §4 verbatim with the still-to-source eval inputs named, and the link checker covers cross-file anchors.
