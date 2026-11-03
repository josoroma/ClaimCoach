# ClaimCoach: apply to Y Combinator Winter 2027

Verified on **November 3, 2026**, using official YC pages. Local times below use **America/Costa_Rica**. This is an application guide; no account, upload or submission has been made for you.

**Apply through [YC's application portal](https://apply.ycombinator.com/home). You can apply as a solo founder. Winter 2027 is still accepting late applications.** YC's FAQ confirms that solo founders are eligible. [YC FAQ](https://www.ycombinator.com/faq)

The regular deadline was **November 2, 2026 at 8 p.m. Pacific**, equivalent to **10 p.m. in Costa Rica that day**. It has passed. The December 11 decision date applies to on-time applicants; late applicants have no promised reply date. The batch runs **January–March 2027, in person in San Francisco**. Apply promptly if you can participate. [Current YC application notice](https://www.ycombinator.com/apply)

## Where your idea, code and videos go

| Material | Where to submit it | What to prepare for ClaimCoach |
| --- | --- | --- |
| Startup idea and business | Written answers in the YC application | Customer, problem, product, progress, business model and your insight |
| Founder background | Your founder profile and application answers | Your real experience, achievements, commitment and ownership |
| Founder video | The application's founder-video field | A new one-minute recording of **you speaking** |
| Product demonstration | The separate demo field | The existing ClaimCoach walkthrough, hosted or uploaded as the live form instructs |
| Source code | Only an appropriate field or a specific request | A repository link if useful; do not assume a source-code ZIP or public repository is required |

YC explicitly separates the founder video from the product demo. **The existing Chatterbox-narrated walkthrough is a product demo; it does not satisfy the founder-video instructions.** [YC video instructions](https://www.ycombinator.com/video)

The authenticated application was not inspected. Its current field names, upload formats and demo limits take precedence over this guide. I found no requirement in the public instructions reviewed to publish your entire codebase. The portal is the application destination; publishing on GitHub or Hacker News alone does not submit an application.

## Steps to complete your application

1. **Open the official portal and sign in or create your account.** Start at [Apply to YC](https://www.ycombinator.com/apply), then choose Apply. Select **Winter 2027** and follow its late-application flow. If that batch is no longer available when you visit, check the current notice before choosing a later batch.

2. **Complete your founder profile as the sole founder.** Enter your actual background and ownership. Explain how you will cover engineering, customers and sales. YC accepts international applicants, expects full-time commitment after acceptance, and does not require incorporation before applying. [YC FAQ](https://www.ycombinator.com/faq)

3. **Prepare concise written answers.** Use the ClaimCoach drafts and factual checklist below. Replace every placeholder with verified information. Distinguish what works today from what you plan to build. YC's own writing guidance emphasizes direct descriptions and concrete evidence. [How to Apply](https://www.ycombinator.com/howtoapply)

4. **Record your founder video.** Make it one minute, with only you talking. Introduce yourself, explain ClaimCoach and why you are building it. Speak naturally from bullet points. Use your own voice; the synthesized demo narration should not stand in for you. [YC video instructions](https://www.ycombinator.com/video)

5. **Prepare a reviewer-accessible product demo.** Start with [the existing 2:07 English walkthrough](docs/video-artifacts/film/claimcoach-walkthrough.en.mp4). Follow the live form's hosting/upload instructions and check its current duration limit. Trim the demo if necessary. A local filesystem path or `localhost` URL will not work for YC reviewers. If using a hosted link, test it while signed out and confirm it does not request access. Keep the fictional-data and human-review labels visible.

6. **Add technical evidence where relevant.** Provide the demo first and a repository where requested or useful. Exclude credentials, local state and patient documents. YC's **optional Paxel builder report** supplies coding-session evidence; inspect what you would share before opting in. [YC FAQ](https://www.ycombinator.com/faq)

7. **Review and submit.** Check answers, links, numbers and videos. Submit one application per batch. Save YC's confirmation email and application copy. [YC FAQ](https://www.ycombinator.com/faq)

8. **Keep building and watch your inbox.** Use YC's designated update route for material changes; submissions are not continuously editable. [YC FAQ](https://www.ycombinator.com/faq) Most Winter interviews are expected in November and December, generally by video. [Application timeline](https://www.ycombinator.com/apply)

## Short answers for the current application form

These drafts follow the form you supplied. Confirmed founder facts: 25 years of software development experience; based in Puerto Viejo de Talamanca, Limón, Costa Rica; no medical-billing experience; post-YC location undecided. Replace remaining brackets before pasting. Pricing is a hypothesis; customer traction and legal status remain unconfirmed.

**Who writes code? Was any work done by a non-founder?**

I have 25 years of software development experience and am building ClaimCoach with Codex assistance, using open-source Hermes and local models. [Identify any other human contributors or contractors, or confirm none.]

**Are you looking for a cofounder?**

[Choose your actual preference. If yes: “Yes, ideally someone with medical billing expertise and experience selling to practices.” If no: “No. I am applying as a solo founder.”]

**Company name**

ClaimCoach

**Description — 43 characters**

Local AI guidance for denied medical claims

**Company URL / product link / login credentials**

[Use existing reviewer-accessible links, or leave optional fields blank. This prototype runs locally; localhost and filesystem paths are not public product links. Provide demo credentials only if needed.]

**Founder video**

Record a new one-minute video of yourself speaking. Your supplied form limits it to 100 MB.

**Product demo**

Upload [claimcoach-walkthrough.en.mp4](docs/video-artifacts/film/claimcoach-walkthrough.en.mp4). It is 126.9 seconds and 17,092,738 bytes, within the supplied form's three-minute / 100 MB limit. It is a product walkthrough, separate from the founder introduction.

**What is your company going to make?**

ClaimCoach helps entry-level medical billers understand denied claims, check payer rules and prepare appeal drafts. It runs inside Hermes Desktop using local models on the practice's Mac. Billers review, edit and export drafts before submission through their existing workflow.

**Where do you live now, and where would the company be based after YC?**

Puerto Viejo de Talamanca, Costa Rica / Undecided

**Explain your location decision.**

I currently live in Puerto Viejo de Talamanca, Limón, Costa Rica. I have not yet decided where to base the company after YC.

Your ability to attend the in-person batch is a separate question and remains unconfirmed; this answer does not imply a relocation commitment.

**How far along are you?**

I have a working prototype demonstrated in Hermes Desktop. A fictional denial went through intake, local-model analysis, appeal drafting, editing and PDF/DOCX export. The agent also used the triage skill and all three plugin tools. Real customer validation is [current status].

**How long have you worked on this? How much full-time?**

I started in [month/year] and have worked on ClaimCoach for [duration], including [duration] full-time.

**Tech stack, models and AI coding tools**

Python/FastAPI, a JavaScript/React Hermes Desktop plugin, and SQLite with encrypted case data and macOS Keychain keys. The demo uses local Bonsai 27B text inference through MTPLX and Qwen3 Embedding 8B through MLX. I use Codex for development assistance.

**Are people using your product?**

[Yes/No. Use No if usage is limited to your own testing; if Yes, describe actual users and usage.]

**Do you have revenue?**

[Yes/No, based on actual revenue.]

**Previous YC applications / changes or pivot**

[If true: “This is my first YC application.” Otherwise, state the previous idea/batch, what changed and what you learned.]

**Previous incubator or accelerator participation**

[None, if true; otherwise list the program, dates and commitments.]

**Why this idea? Domain expertise? Evidence of need?**

I have 25 years of software development experience and no medical-billing experience. Industry research documents a substantial denial-management problem: Experian's 2025 survey found that 82% of respondents prioritized reducing denials. My hypothesis is that local AI can help billers understand denials and prepare drafts for review. [Add any actual customer conversations or pilot evidence.]

Fact-check sources and their limits:

- **MGMA, March 2024:** 60% of respondents in a poll with 235 applicable responses reported increased practice claim-denial rates versus the same period in 2023. This supports the existence of a practice-level problem. [MGMA poll](https://www.mgma.com/mgma-stat/strategic-improvements-in-your-rcm-to-reduce-your-practices-claim-denials)
- **Experian Health, September 2025:** its survey of 250 healthcare professionals responsible for financial, billing or claims-management decisions found 82% prioritized reducing denials; 41% reported denial rates of at least 10%. This is vendor-sponsored, self-reported research, not a census of all practices. [Experian survey](https://www.experianplc.com/newsroom/press-releases/2025/experian-health-s-3rd-annual-state-of-claims-survey-finds-denial)
- These findings support investigating denial-management problems. They do not establish demand for ClaimCoach, willingness to pay, preference for local models, or compatibility with customers' hardware. Interviews and pilots must test those specific assumptions. Customer conversations have not yet been described here; do not claim either that they happened or that none happened without confirming.

**Competitors and your insight**

Competitors include Infinx, AKASA and outsourced billing services. My hypothesis is that smaller practices need a local tool that helps existing billers resolve denials. ClaimCoach focuses on explaining the evidence and preparing a reviewable next step, with the biller in control.

Research supporting the competitor names: [Infinx denial management](https://www.infinx.com/rcm-plus-accounts-receivable-recovery-and-denials-management-platform/) and [AKASA AI Advisor](https://akasa.com/solutions/ai-advisor/). The proposed differentiation is a hypothesis, not a claim that competitors lack similar features.

**How will you make money? How much could you make?**

Suggested hypothesis, only if you adopt it: I plan to sell subscriptions to practices and billing services, initially testing $300 per practice per month. At 10,000 paying practices, that would be $36 million in annual recurring revenue. Pricing and demand still need validation.

This is an illustrative revenue scenario, not a verified market-size estimate or forecast.

**Other ideas considered**

[List only ideas you actually considered, or “None.”]

**Have you formed any legal entity? Taken investment? Currently fundraising?**

[Answer each Yes/No from your actual circumstances. Do not infer these from the prototype's stage.]

**What convinced you to apply? Encouragement or YC events?**

YC's “The $15-an-Hour Expert” request aligns with ClaimCoach: helping entry-level billers perform more specialized work. I want to turn the prototype into a product customers pay for. [Add any actual encouragement or events, or state none.]

**How did you hear about YC?**

[Your actual source: a person, Hacker News, Startup School, YouTube, or another source.]

**Batch preference**

Winter 2027

**Before submitting**

Complete your founder profile, replace every bracket, upload your founder video and attach the separate demo. The form currently flags your founder profile and founder video as incomplete.

## Bullet points for your one-minute founder video

Use these as prompts for natural speech, not a script to recite:

| Approximate time | What to cover |
| --- | --- |
| 0–10 seconds | Your name, that you are the solo founder, and one relevant fact about your background |
| 10–25 seconds | Who the biller is and the specific problem you observed |
| 25–40 seconds | What ClaimCoach does and the working prototype you can demonstrate |
| 40–55 seconds | Your personal insight and real customer learning, if any |
| 55–60 seconds | The next concrete milestone you are pursuing |

Record a clear, simple English take. Your existing animated, synthesized-narration video remains the separate product walkthrough. The distinction follows [YC's founder-video guidance](https://www.ycombinator.com/video).

## Facts to fill in before submitting

| Missing information | Your answer |
| --- | --- |
| Founder name and strongest relevant achievement | 25 years of software development; [add name and one concrete achievement] |
| Current location and ability to attend in San Francisco | Puerto Viejo de Talamanca, Limón, Costa Rica; [confirm ability to attend] |
| Company location after YC | Undecided |
| Medical-billing experience | None; founder's expertise is software development |
| Current employment and full-time commitment date | [Fill in] |
| Company formation, ownership, prior funding and obligations | [Fill in accurately; unincorporated is a valid current status] |
| Number of customer interviews and what you learned | [Fill in] |
| Active users, pilots, paying customers and revenue, with dates | [Fill in; write zero where true] |
| First buyer, proposed pricing and acquisition approach | [Fill in; mark hypotheses] |
| Alternatives customers use and your specific advantage | [Fill in from actual research] |
| Founder-video URL | [Record and add] |
| Product-demo URL or upload | [Host/upload and add] |
| Company website or repository, where relevant | [Add only an existing working destination] |

You already have engineering evidence and a confirmed software-development background. Remaining inputs include a concrete founder achievement, customer learning and commercial evidence; those cannot be inferred from this repository.

## Use the prototype evidence accurately

- **Verified:** an actual local-model workflow, live Hermes Desktop captures, command and skill execution, successful tool calls, an edited draft, and PDF/DOCX exports. See [demo evidence and files](docs/video-artifacts/README.md).
- **Verified engineering checks:** 1,876 Python tests passed, one skipped because the live worker occupied its required port, 14 were deselected, and 191 JavaScript tests passed; application coverage was 100%. These checks do not measure clinical or billing accuracy. See [delivery receipt](docs/video-artifacts/delivery-receipt.json).
- **Not established:** paying customers, dollars recovered, improved overturn rates, real-case diagnosis accuracy, measured time savings, HIPAA compliance, or an independent zero-egress audit.
- **Observed limitations:** the first model output included unsupported statements; the draft was corrected by the demo operator and still needs professional review. Memory pressure required a retry after unloading an unused model. OCR and transcription were not exercised because their weights were absent. See [quality review](docs/video-artifacts/quality-review.md).
- **Use bounded model claims:** the demonstration used installed ternary Bonsai 27B and Qwen3 Embedding 8B weights on the specified Mac. Say “local open-weight models” and name tested hardware. Do not imply that all models are small, that every consumer laptop is supported, or that open weights alone establish every software/model license right.
- **Keep documentation aligned with evidence:** the root [README](README.md) now records the November 2 live-model/Desktop demonstration and its limits. PRD performance targets remain goals, and local routing is not a privacy or compliance certification; do not present either as measured production results.

## Understand participation and investment

Plan travel and full-time availability. YC connects accepted founders with immigration counsel when needed. [YC FAQ](https://www.ycombinator.com/faq)

YC's published standard investment is **$500,000**: **$125,000 for 7%**, plus **$375,000 on an uncapped SAFE with a most-favored-nation provision**, which adds equity on conversion. Review the actual documents before accepting. YC lists US, Canadian, Cayman and Singapore corporations as eligible investment entities and helps accepted founders with formation or restructuring. [YC standard deal](https://www.ycombinator.com/deal)

## Submission checklist

- [ ] Winter 2027 selected, with late-application status understood.
- [ ] Founder profile and company answers completed with real facts.
- [ ] All placeholders replaced; targets and hypotheses clearly labeled.
- [ ] One-minute founder-speaking video recorded and attached as instructed.
- [ ] ClaimCoach product demo provided separately and accessible to reviewers.
- [ ] Technical claims agree with the actual demo and its limitations.
- [ ] Live-form requirements and all links checked.
- [ ] Application submitted and confirmation email saved.

**Recommended next action:** open [the application portal](https://apply.ycombinator.com/home), fill the founder/customer facts, record the one-minute founder video, attach the separate product demo and submit the late Winter 2027 application when those essentials are ready.
