# ClaimCoach English product walkthrough

Editable 1920 × 1080, 30 fps Taster composition for prospective billers and startup reviewers. The film explains how to enable ClaimCoach in Hermes Desktop, connect a local model, bring in a fictional denial, review its fields, diagnose, prepare a draft, and use the Hermes command, skill, and tool loop.

Delivered: **2 minutes 6.9 seconds**, H.264 video with AAC English narration, 17,092,738 bytes. `delivery.json` records the final hashes. The corrected intake instruction explicitly includes **Attach pasted text**.

The desktop footage consists of actual screenshots with guided crops and pans. It is not a continuous screen recording. Case scenes carry a **Fictional training sample** label. The film does not imply Y Combinator acceptance or endorsement, measured billing results, compliance certification, or a successful appeal.

## Files

- `claimcoach-walkthrough.en.mp4`: final encoded deliverable.
- `index.html` / `preview.mjs`: responsive, seekable browser preview.
- `composition/`: self-contained HTML/CSS/JavaScript composition, local fonts, captures and voice clips.
- `script.en.json`: editable chapter copy, narration and screenshot focus coordinates.
- `claimcoach.en.srt`: English subtitles timed from the narration segments.
- `qa/verification.json`: browser behavior, cut and deterministic-seek checks.
- `qa/video-verification.json`: decoded deliverable metadata, audio and frame checks.

Source inputs live one directory above: `screenshots/`, `audio/`, `demo-inputs/` and `product-evidence.md`.

## Reproduce

Run in this directory with Node.js 22+, FFmpeg and Google Chrome installed:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm run verify
npm run check
npm run render
npm run verify:video
npm start
```

The local preview opens at `http://127.0.0.1:4189`. It does not autoplay. Use Play/Pause, the position slider, chapter buttons, Space, left/right arrow keys, or Home. It pauses when hidden. All exported motion is reconstructed from absolute time; the separate preview owns the playback clock.

The rendering wrapper pins **Hyperframes 0.8.171**, matching the user's tested Taster video example. Its complete rendering invocation is:

```sh
npx --yes --package hyperframes@0.8.171 -- hyperframes render --fps 30 --quality looks --workers 2 --output ../claimcoach-walkthrough.en.mp4
```

Run that low-level command from `composition/`. `node build.mjs --draft` can author with missing assets but is not a delivery build. A final build refuses missing screenshots, missing audio, and narration text mismatches.

## Provenance and scope

The workflow and deterministic composition contract come from the user's `/Users/josoroma/sites/taster` checkout, revision `f937d8fd6f5c61941a3b3a8b5d3f5daef30aeba8`, with its license retained in `TASTER-LICENSE.txt`. Rendering follows the [official Hyperframes CLI workflow](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes-cli/SKILL.md). No hosted renderer or publishing service is used.

The narration is synthetic English made with the exact local `~/Models/chatterbox-multilingual-v3` weights and their bundled default voice; no reference voice was cloned. The audio directory includes the generator, model revision, settings, hashes, timings, normalization metadata and local transcription checks. The model's watermark is retained.

The ClaimCoach logo is the product's existing `plugin/assets/claimcoach-logo.svg`. DM Sans is bundled with its SIL Open Font License in `composition/assets/DM-Sans-OFL.txt`.

The recording machine is an **Apple M3 Pro Mac with 36 GiB unified memory**. Local-model hardware needs depend on the selected weights and quantization. This demonstration does not establish that every configured model runs on every consumer laptop. Consult the parent runtime artifacts for the exact live model and worker configuration used.

The fictional Northstar Demo Health example is a CO-197 denial. It does not establish that authorization exists. The biller must verify missing evidence; every generated draft requires human review. The film ends at preparation and review, without claiming a payer accepted an appeal.

The live diagnosis generated an unsupported suggestion that authorization completed after service might be accepted before appeal. The source screenshot is retained unchanged. The film emphasizes the code, checklist and verification against the fictional payer rule card, with an explicit verification overlay. This run does not validate diagnosis quality. The demonstrated draft was edited by the assistant operator through the actual desktop UI to remove an unsupported assertion that documents were attached and to state that authorization evidence was missing. That edit is an example review step, not approval by a clinician or billing professional.

The actual reviewed-example PDF and DOCX exports were separately rendered and checked as one-page files. Their renders are retained in `../outputs/qa/final-pdf/` and `../outputs/qa/final-docx/`; the film shows the real export controls.

The recorded Hermes chat reports five tool calls and one failed call. That indicator is retained in the film: the agent initially omitted the payer argument, Hermes rejected the invalid call before invoking the tool, and the agent corrected it and retrieved two payer rule cards. The completed answer is shown as the outcome of that actual recovery.

Final verification passed Hyperframes lint, runtime, layout, motion and contrast checks, browser controls and deterministic reverse seeking. Forty decoded video frames cover each scene's midpoint and ending, alternate captures, and both sides of every cut. Those frames and the cut contact sheet were inspected. The encoded narration is nonempty, with mean level −20.0 dB and peak −1.5 dB; source speech was also checked by local automatic transcription. No manual listening review is claimed.
