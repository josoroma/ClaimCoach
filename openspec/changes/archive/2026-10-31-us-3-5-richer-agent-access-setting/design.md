# Design: US-3.5 Richer Agent Access (setting only)

## Context

Two open questions in SPECS.md US-3.5: what richer access allows (unredacted fields? whole
documents?), and how ClaimCoach knows the Hermes model is local (and what happens if it switches
to a cloud provider while the setting is on). Both decide what PHI the agent may see, so they are
the Product Manager's call, not an implementation default.

## Goals / Non-Goals

**Goals:** the two acceptance scenarios; no change to what the agent can see.

**Non-Goals:** any richer access itself; detecting a local Hermes model.

## Decisions

1. **Open questions resolved conservatively: the setting grants nothing in v1.** It exists,
   defaults off, and is displayed; the US-3.2 guards ignore it. `test_us_3_5_setting_grants_
   nothing_yet` lists the only files allowed to read it (settings, the route, its response
   model, `plugin.js`). *Alternative:* define richer access now (e.g., unredacted codes and payer
   names) — rejected, it widens the PHI boundary on a guess.
2. **Fail toward off.** `load_settings()` returns the defaults when Hermes is absent or the
   stored values do not validate (`extra="forbid"`), and the statusbar treats anything but an
   explicit `true` as off.
3. **The gateway reads the setting, not the worker.** Hermes stores plugin settings in its
   config; `GET /settings` needs no worker, so the statusbar is right even when the worker is
   stopped.
4. **The tooltip says results are still redacted**, so a user who turned it on is not misled.
5. **Strict boolean, refreshed display** (review findings). `StrictBool`: `"yes"`, `1`, or a
   YAML string `"true"` is invalid and reads as off. The statusbar re-reads `/settings` every
   15 s, so turning the setting on or off in Settings shows without a reload. Validation is all
   or nothing, with a fixed warning; the legacy `config` subtree is not read.

## Risks / Trade-offs

- [A visible setting that does nothing yet] → the description and tooltip say so; the follow-up
  is tracked by the open questions in SPECS.md.
