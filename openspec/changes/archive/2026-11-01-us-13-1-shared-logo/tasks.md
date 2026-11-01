# Tasks

## 1. Logo

- [x] 1.1 Create `plugin/assets/claimcoach-logo.svg`; verify `test_us_13_1_logo_file_self_contained`
- [x] 1.2 Move the self-contained SVG check to `tests/svg_checks.py` and refuse every external `url()`, non-SVG element, processing instruction, DOCTYPE, and entity; verify `test_us_13_1_check_refuses_unsafe_svg` (16 cases) and `test_us_13_1_check_allows_local_references`
- [x] 1.3 Add `LOGO` and `ClaimCoachLogo` to `plugin.js` and draw it in the pane, dashboard, and settings headings; verify `test_us_13_1_pages_show_logo`, `test_us_13_1_logo_matches_file`, `test_us_13_1_logo_match_refuses_extra_content`, `test_us_13_1_logo_hidden_from_screen_readers`
- [x] 1.4 Check the package still validates; verify `make validate`

## 2. Evidence

- [x] 2.1 Record `evidence/US-13.1/test-report.md` and `junit.xml`; verify `make evidence-check`
