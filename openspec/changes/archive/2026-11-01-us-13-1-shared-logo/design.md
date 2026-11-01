# Design: US-13.1 Shared ClaimCoach Logo on the Plugin Pages

## Context

PC-3 makes `desktop/plugin.js` plain ESM with no build step, importing only the SDK and React. It
cannot import an SVG file, and the gateway serves no static assets for the desktop half.

## Goals / Non-Goals

- Goals: one source for the mark; the same shapes and colors on every page and README.
- Non-Goals: a wordmark, favicons, or a Hermes sidebar icon (the SDK's nav item takes a codicon
  name only).

## Decisions

1. **The file is the source; plugin.js mirrors it and a test pins the two.** `LOGO` copies the
   file's shapes with the file's attribute names, and `test_us_13_1_logo_matches_file` parses the
   file and compares tag by tag, attribute by attribute. Rejected: fetching the file through a
   gateway route (a new route for a static asset, and a broken image while the worker is down);
   a data URL in plugin.js (a second copy no test could compare structurally).
2. **The logo is decorative.** It sits inside the heading with `aria-hidden="true"` and
   `focusable="false"`, so the heading's text alone names the page. Rejected: `role="img"` with a
   label, which would make screen readers announce "ClaimCoach ClaimCoach".
3. **The file lives in `plugin/assets/`.** It ships with the package that draws it, and the READMEs
   reference the same path. Rejected: `docs/assets/`, which does not ship with the plugin.

## Risks / Trade-offs

- [The file changes and plugin.js does not] → the match test fails `make check`.
- [A future logo uses gradients or text] → the file test allows only `rect` and `path`, so the
  change is a conscious one in both places.
