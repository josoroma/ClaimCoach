# Design: US-1.4 Quality Gate and Test Harnesses

## Context

See proposal.md. Two scenarios test the gate itself (`make check` passes; a type error fails it).
Running those inside `make check` would recurse.

## Decisions

1. **Gate self-tests carry `@pytest.mark.gate`** and `make check` runs `-m "not models and not
   gate"`. `make verify` runs `check` and then the gate tests. The gate test invokes
   `make check` with the same marker filter, so there is no recursion.
2. **Type-error injection through `MYPY_EXTRA`.** The failing-gate test writes a bad module to a
   temp dir and runs `make check MYPY_EXTRA=<file>`; mypy runs before biome, tsc and pytest so the
   failure is fast and names the error. The real tree is never modified.
3. **Socket guard at the `socket` layer.** An autouse fixture wraps `socket.socket.connect`,
   `connect_ex`, and `socket.getaddrinfo`; only loopback addresses, `localhost`, and `AF_UNIX`
   pass. A `@pytest.mark.allow_network` marker exists for future `models` tests and is refused
   unless the `models` marker is also set.
4. **Fake model server in a thread.** uvicorn on `127.0.0.1:0` inside a daemon thread, exposed as
   a session fixture. Canned responses are deterministic and keyed by request `model`.
5. **Node module hooks instead of a bundler.** `module.registerHooks` (Node ≥ 22.15) maps
   `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime` to fakes under `desktop/tests/fakes/`.
   The fake `react` runs hooks synchronously so component functions can be called directly and
   their element trees asserted, which is what lets `plugin.js` reach 100% coverage without a DOM.
6. **SDK types by hand, React types from `@types/react`.** The SDK is not published to npm, so
   `types/hermes-plugin-sdk.d.ts` declares only the surfaces ClaimCoach uses, citing
   `website/docs/developer-guide/desktop-plugin-sdk.md` in Hermes v0.22.5.

## Risks / Trade-offs

- [The `.d.ts` drifts from the real SDK] → the header names the doc and version it was checked
  against; US-10.x revisits it when they add surfaces.
- [100% coverage invites trivial tests] → tests assert behavior from the specs; `# pragma: no
  cover` is not allowed (a test greps for it).
