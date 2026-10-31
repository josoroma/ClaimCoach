# Tasks

## 1. Checks

- [x] 1.1 Contribution and control label test; verify `node --test` `test_us_7_3_no_send_contribution`
- [x] 1.2 Route table, pinned route set, and loopback-only case flow; verify `test_us_7_3_no_transmitting_route`, `test_us_7_3_case_routes_reach_only_loopback`
- [x] 1.3 Source scan for mail and HTTP clients; verify `test_us_7_3_http_clients_only_in_loopback_modules`
- [x] 1.4 BR-4 in module docstrings; verify `test_us_7_3_docstrings_cite_br_4`

## 2. Evidence

- [x] 2.1 Record `evidence/US-7.3/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
