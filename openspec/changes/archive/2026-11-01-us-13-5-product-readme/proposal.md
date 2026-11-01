# Proposal: US-13.5 Product README for Y Combinator

## Why

README.md opened with a package layout and make targets. An investor or a practice owner should read the product first and find the engineering one link away (SPECS.md US-13.5).

## What Changes

- `README.md` as the product page: the shared logo, the one-line promise, the problem, what ClaimCoach does, who it is for, why it runs on the Mac, the v1 targets, status, and links to README-DEV.md, the PRD, the backlog, runbooks, and ADRs. It shows the user and stakeholder diagrams and has no commands.
- `tests/test_us_13_5_product_readme.py`: the sections, the targets against PRD §4, the shared logo in every README, and every relative link and anchor resolving.

## Capabilities

### New Capabilities
- `product-readme`: the product README and the README link and logo checks.

### Modified Capabilities
- None.

## Impact

- Docs and tests only. The engineering content of the old README now lives in README-DEV.md.
