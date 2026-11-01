# Review: US-13.1

Change: us-13-1-shared-logo
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes (the logo inside a live Hermes Desktop stays UNVERIFIED: no live Desktop here)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | The plugin.js-to-file match read the file with a regex that saw only self-closing `rect`/`path` with double-quoted attributes and ignored the root, so an added `<path …></path>`, a single-quoted `opacity`, or a root `style` passed | `readLogo` reads the file exhaustively (anything left over fails), `readAttributes` must consume each attribute text, and the root's attributes are pinned in both suites; `test_us_13_1_logo_match_refuses_extra_content` covers each bypass. The Python test walks every element and requires childless `rect`/`path` and double quotes only |
| medium | `self_contained_svg` missed quoted, uppercase, protocol-relative, `style`, and `<style>` `url()`s, `<?xml-stylesheet?>`, and non-SVG-namespace elements | Moved to `tests/svg_checks.py` (shared with US-13.4): refuses any `url()` not starting with `#` in attributes and element text, `xml-stylesheet`, DOCTYPE, ENTITY, `@import`, and any element outside the SVG namespace; 16 cases in `test_us_13_1_check_refuses_unsafe_svg`, plus `test_us_13_1_check_allows_local_references` |
| low | No evidence recorded yet | `evidence/US-13.1/` recorded after the fixes |
| info | An assertion on hook count after the page loop proved nothing | Removed |
| info | `make check` coverage was 99.92% in the reviewer's sandbox (subprocess `__main__` lines) | Not reproduced: `make check` and `make verify` report 100% here |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 244.06s (0:04:04) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
ok   US-13.1
ok   US-13.2
ok   US-13.3
ok   US-13.4
ok   US-13.5
================ 2 passed, 1824 deselected in 248.32s (0:04:08) ================
```

The first `make verify` run failed once in its nested `make check` (the gate's self-test):
`test_us_2_2_group_members_are_stopped_with_the_leader` raised `PermissionError` from `os.killpg` in
`_group_alive` (`plugin/claimcoach/models/manager.py`, EPIC-2), which catches only
`ProcessLookupError`. It passed 5 of 5 runs alone and on the second `make verify`. This change does
not touch that code; it is reported to the user as a separate follow-up.
