# Test Report: US-13.1 Shared ClaimCoach Logo on the Plugin Pages

Change: us-13-1-shared-logo
Story: US-13.1
Verdict: pass
Coverage: 4/4 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 for `make validate`; no live Hermes Desktop

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "One logo file is the source of the mark: Then it is a self-contained SVG with a title, a viewBox, and no script, external reference, or embedded image" | PASS | `test_us_13_1_logo_file_self_contained`: root attributes are exactly `viewBox, width, height, role, aria-labelledby`, title `ClaimCoach`, every drawn element a childless `rect` or `path`, double quotes only. The shared check refuses 16 unsafe inputs (`test_us_13_1_check_refuses_unsafe_svg`: script, `href`, event handler, quoted/uppercase/protocol-relative/`style`/`<style>` `url()`, `@import`, `xml-stylesheet`, DOCTYPE, an XHTML element) and allows local `url(#…)` (`test_us_13_1_check_allows_local_references`) |
| 2 | "The plugin pages show the shared logo: Then each shows the ClaimCoach logo next to its heading" | PASS | node `test_us_13_1_pages_show_logo`: CasePane `h2`, DashboardPage `h1`, SettingsPage `h2` each lead with `ClaimCoachLogo` and keep their text (`ClaimCoach`, `ClaimCoach dashboard`, `ClaimCoach`). Rendered with the fake ctx, not a live Hermes Desktop (see Notes) |
| 3 | "The plugin pages show the shared logo: And the logo's shapes and colors are the ones in plugin/assets/claimcoach-logo.svg" | PASS | node `test_us_13_1_logo_matches_file`: the file is read exhaustively (root attributes, title, each shape's whole attribute text; anything left over fails) and equals `LOGO` shape for shape, attribute for attribute. `test_us_13_1_logo_match_refuses_extra_content` shows an added non-self-closing red `<path>`, a single-quoted `opacity`, a restyled root, and a wrapping `<g>` each fail. Visual: the file rendered in the browser pane as a teal tile, white document with a folded corner, two text lines, and an amber check |
| 4 | "The logo does not repeat the heading to screen readers: Then the logo is hidden from it and the heading names the page" | PASS | node `test_us_13_1_logo_hidden_from_screen_readers`: on all three pages the drawn `svg` has `aria-hidden="true"`, `focusable="false"`, no `aria-label`, no `role` |

## Evidence Commands

```bash
make evidence STORY=US-13.1
node --import ./plugin/desktop/tests/register-fakes.mjs --test --test-name-pattern=us_13_1 plugin/desktop/tests/
make validate
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
===================== 18 passed, 1808 deselected in 1.38s ======================
  ✔ test_us_13_1_pages_show_logo (2.321625ms)
  ✔ test_us_13_1_logo_matches_file (2.336916ms)
  ✔ test_us_13_1_logo_match_refuses_extra_content (1.597666ms)
  ✔ test_us_13_1_logo_hidden_from_screen_readers (0.242042ms)
Validation passed.
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 250.31s (0:04:10) ================
ℹ tests 191
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-13.1/junit.xml`, `evidence/US-13.1/junit-node.xml`

## Failures

None.

## Notes

- The pages were rendered through plugin.js with the fake `ctx` and fake `react/jsx-runtime`, as every desktop story's tests are. How a live Hermes Desktop draws the inline SVG beside each heading was not seen.
- `plugin/assets/` ships in the package: `make validate` passes with it present.
- Review fixes (see review.md): the logo match and the self-contained SVG check were made exhaustive, with a regression test per bypass the reviewer found.
