# AGENTS.md — Birbal build instructions

You are building **Birbal**, a voice agent that interviews a problem owner and produces a structured, redacted problem brief that builders can act on. It is for Challenge 2 (Problem Intake Agent) at the AI Garage × Paytm Voice AI Buildathon. The build is **solo**. The event is **4 hours** and pre-written code is allowed, so the product is built **before** the event; the 4 hours are for integration, unseen-input testing and rehearsal. Judges care most about an **enterprise-grade demo**.

Tagline: *"Akbar had Birbal. Now every builder does."* · *Problem bolo, Birbal samjhega.*

**Read order:** this file, then `PLAN.md` (full plan: story, sample interview, sample brief, budgets, demo script), then `docs/DECISIONS.md`, `docs/ISSUES.md` and `docs/IMPLEMENTATION_LOG.md`. If this file and `PLAN.md` disagree, this file wins. Log the conflict in `docs/ISSUES.md`.

---

## 0. Run (built before the event; see docs/IMPLEMENTATION_LOG.md for what is verified)

```bash
uv sync                                                    # install (Python ≥3.11, pipecat-ai 1.12.0 pinned)
cp .env.example .env                                       # add keys; never commit .env
uv run uvicorn api:app --app-dir server --port 8000        # app at http://localhost:8000
uv run pytest -q                                           # 46 tests, no keys needed
uv run python server/simulate.py --turns 12                # interview-quality scorecard (needs LLM keys)
```
- `/` is the landing page; the app is at `/start`; the public board is at `/board`.
- Each interview is its own session, `/start?s=<id>`, saved to `data/sessions/<id>.json` (gitignored). A refresh resumes the interview; the start screen lists recent briefs, with redacted titles.
- In voice mode, **Type instead** (`T`) switches to typing mid-interview without losing anything.
- Interviews in progress autosave every 5 s. Approving creates a read-only share link, `/b/<token>`, with the builder and public versions only.
- From a phone or another laptop: `./scripts/serve_lan.sh` (HTTPS on the LAN IP, port 8443). Use a phone hotspot.
- `http://localhost:8000/start?demo=1` shows **Play demo**: replays `server/fixtures/demo_interview.json` with no keys. This is the demo fallback.
- **Type instead** needs `GOOGLE_API_KEY` or `GROQ_API_KEY`.
- **Start interview** (voice) also needs `DEEPGRAM_API_KEY`, plus the key for the chosen `TTS_PROVIDER`.

## 1. Hard constraints (never violate)

1. **₹0 spend.** Use only free tiers and signup credits: Gemini free tier, Deepgram $200 credit, Sarvam ₹100 credit, Groq free tier, ElevenLabs free tier. Never add a paid service or one that needs a card.
2. **Secrets live only in `.env`.** `.env` is gitignored, and `.env.example` lists the variable names. The browser never sees an API key.
3. **No real company, bank or person names** in prompts, fixtures, tests or the demo. Use fictional ones: "Kaveri Bank", "Ravi on the platform team".
4. **The owner approves before anything leaves the app.** Export happens only after the owner clicks Approve on the Review page.
5. **Redaction is enforced by code, not by asking an LLM.** Lower versions are generated only from already-redacted text.
6. **The 90-minute gate.** The cascade voice spike must have mic → STT → Talker → TTS → speaker with barge-in working within **90 minutes from the start of step 1**. If not, switch to Plan B (Gemini Live, see `PLAN.md` §5) and log it in `docs/DECISIONS.md`.
7. **Credit budget.** Sarvam TTS is for the final demo and rehearsals only. Use Deepgram Aura-2 while developing.
8. **Solo, built before the event.** The smallest complete thing wins. **Our** pages (`index.html`, `review.html`) are plain HTML + JS with no build step and no framework. The voice connection uses the client page that ships with Pipecat's SmallWebRTC example (or the `pipecat-ai-small-webrtc-prebuilt` package; verify the name). Never hand-write a WebRTC client.

## 2. Requirements (acceptance checklist; all must pass)

The interview must progressively cover all 9 dimensions, using follow-ups and **never** reading out a questionnaire:

| key | Dimension | Sufficient (score 2) when |
|---|---|---|
| `current_state` | What is happening today | one concrete recent incident has been walked through |
| `who` | Who experiences it | a role or segment plus a rough count |
| `workaround` | How it's solved today | what they do, plus its cost |
| `impact` | Why it matters | a number or a named downstream effect |
| `frequency` | How often | a number per time unit |
| `constraints` | Constraints | concrete constraints, or an explicit "none known" |
| `attempted` | What was tried | what was tried, plus why it stalled |
| `confidential` | What's secret | every flagged span has an owner choice |
| `success_test` | Useful outcome | an observable test: "we'd know it worked if…" |

Score 0 = nothing recorded. Score 1 = only `inferred`/`hearsay` claims, or only adjectives. Score 2 = an `observed` claim **plus** an anchor (a number, a named role, or an incident).

The output and the bonus points (every one is required, not optional):
- [ ] **Structured brief** that another builder can start from. It must include "Where to start" (3 investigations), "Data to request", open questions with leads, and parked topics.
- [ ] **Missing info is identified.** Gaps and unknowns become "Open questions", each with a "who would know" lead.
- [ ] **Facts are separated from assumptions.** Every claim has a `kind` (`observed`/`hearsay`/`inferred`/`aspiration`) and an `evidence_quote`.
- [ ] **Sensitive info is detected** in 6 categories: `person_name`, `org_or_partner_name`, `customer_data`, `business_metric`, `internal_system`, `unreleased_plan_or_legal`.
- [ ] **The owner gets help redacting.** The consent question is asked *in the conversation* right after disclosure, and can be changed on the Review page.
- [ ] **Versions per audience** are built from one ledger: **For me** (everything, with quotes), **For builders** (redacted), **For everyone** (3-line teaser, redacted).
- [ ] **Edge cases are handled:** vague answers get re-probed, contradictions are named, "I don't know" gets "who would know?", extra problems get parked, off-topic answers get a bridge back, silence over 8 s gets a nudge, barge-in works, and read-back happens at the end.

Judges score four things: friction removed, conversation quality, edge-case handling, and use-case innovation. They **will** test with problems they bring themselves.

## 3. Uniqueness: never cut these (they are the pitch)

1. **Claim ledger** with kind + evidence quote. The board shows chips: **Dekha · Seen**, **Suna · Heard**, **Socha · Guessed**, **Chahiye · Wished**.
2. **Consent at the moment of disclosure:** "You mentioned Kaveri Bank by name. Should that stay internal?"
3. **Code-enforced redaction + leak check:** **Safe to share ✓** / **Secret found ✗**.
4. **Read-back:** "Here's what I heard. What did I get wrong?"
5. **Talker + Scribe split** (Birbal + Birbal's Notes): the interviewer-plus-note-taker debrief.

**Cut order if behind:** For everyone teaser, then text-mode fallback, then anything cosmetic.

## 4. Architecture

```
Browser ─WebRTC (Pipecat SmallWebRTCTransport)─► Python server (Pipecat + FastAPI)
  mic ► Silero VAD (barge-in) ► Deepgram STT ► user text
        ├─► TALKER  (Gemini Flash; short prompt + gap report) ─► TTS (Aura-2 dev / Sarvam demo) ► speaker
        └─► SCRIBE  (async LLM, JSON) ─► LEDGER ─► CONTROLLER (pure code) ─► gap report for next turn
  index.html (Notes panel) ◄─ GET /ledger (poll 1 s)
  review.html ◄─ POST /brief → canonical brief → redact → LLM wording pass → leak check → 3 versions → POST /approve → export .md/.json
```

The Talker never waits for the Scribe. The Scribe lags one turn, and the Talker always sees the raw latest utterance.

**The architectural crux: verify it in the gate.**
- **Gap report into the Talker context.** Pipecat's context aggregator owns the message history. Find the current documented way to update or append a per-turn controller message (a context update or message-append frame) before building the Scribe.
- **Scribe off the hot path.** The Scribe fires as a background `asyncio` task from a frame processor and is never `await`ed inside the pipeline. Otherwise it stalls the Talker, which defeats the split.
- **Plan B has the same question.** Whether tool responses steer the next turn there is the same open question.

| Role | Default | Fallback | Env var |
|---|---|---|---|
| STT | Deepgram Nova-3 multilingual, streaming | Groq `whisper-large-v3` | `DEEPGRAM_API_KEY` / `GROQ_API_KEY` |
| Talker LLM | Gemini `gemini-3.6-flash` | Groq `openai/gpt-oss-120b` | `GOOGLE_API_KEY` |
| Scribe LLM | Gemini `gemini-3.6-flash` (JSON schema) | Groq `openai/gpt-oss-120b`, every 2nd turn (8K TPM limit) | `GROQ_API_KEY` |
| TTS | Deepgram Aura-2 (dev) | Sarvam `bulbul:v3` (demo), ElevenLabs Flash v2.5 (alternate) | `TTS_PROVIDER=aura\|sarvam\|elevenlabs`, `SARVAM_API_KEY`, `ELEVENLABS_API_KEY` |
| Plan B (all in one) | Gemini Live `gemini-3.8-live` | `gemini-2.5-flash-native-audio-preview-12-2025` | `BIRBAL_MODE=cascade\|live` |

Verify every model ID and Pipecat class name against current docs before use. Do not trust memory. Pin the Pipecat version that works in the spike (`uv lock`). Pipecat ≥0.0.105 uses `settings=` instead of `params=`.

## 5. Repo layout (create only what's needed)

```
server/
  bot.py          # Pipecat pipeline: transport, VAD, STT, Talker, TTS, Scribe hook
  api.py          # FastAPI: WebRTC offer, /ledger, /brief, /approve, /export, static web/
  brain/          # transport-agnostic; works unchanged in Plan B
    prompts.py    # Talker system prompt, Scribe prompt
    schema.py     # Pydantic: Claim, Sensitive, ScribeOutput, Ledger, GapReport, Brief
    controller.py # scoring + priority → GapReport (pure functions)
    brief.py      # canonical brief, redaction, leak check, 3 versions
  tests/          # controller + leak check + redaction unit tests; persona fixtures
web/  index.html  review.html  app.css
docs/ IMPLEMENTATION_LOG.md  ISSUES.md  DECISIONS.md
```

## 6. Core logic specs

**Controller priority** (picks exactly one `focus` per turn):
1. a pending consent question;
2. an open contradiction;
3. `current_state` while it is below 2;
4. the first unsettled dimension in table order (score < 2 and no unknown-with-lead), so a vague answer is deepened right away;
5. read-back, when every dimension is at 2, or after 8 minutes, or when the owner says they're done.

**GapReport:** `{focus, why, pending_consent[], contradictions[], parked[], minutes_elapsed, ready_for_readback}`

**ScribeOutput:** `{claims[], sensitive[], contradictions[], unknowns[], parked_topics[], owner_choices[]}`

**Claim:** `{id, turn, dimension, value, kind, source, evidence_quote, confidence, sensitivity?: {category, span, choice: keep|generalise|remove|null, generalisation}}`

**Talker rules** (system prompt; the full list is in `PLAN.md` §4):
- One question per turn, ≤25 words, with a brief acknowledgement.
- Prefer specific past incidents over general claims, and numbers over adjectives.
- Ask "what did you see?" for conclusions, and "who would disagree?".
- Park extra problems.
- Mirror Hinglish if the owner uses it.
- Never say dimension names.
- If there's a pending consent, ask it first.

**Redaction pipeline:**
1. Code replaces approved spans in the canonical brief JSON (`generalise` → the generalisation; `remove` → drop the sentence or field).
2. The LLM rewords the redacted JSON only.
3. Leak check: case-insensitive substring match of every non-`keep` span, with numbers normalised (`1,200` = `1200` = `1.2k`). Any hit blocks export for that version and highlights it.

Known limit, to state in the pitch: paraphrases are not caught, which is why step 1 happens first.

## 7. Build order (pre-event; each step has a "done when")

| # | Step | Done when |
|---|---|---|
| 0 | Keys in `.env`; record the real free limits in `docs/DECISIONS.md` | Every key works with a 1-line curl/SDK call |
| 1 | **Gate (≤90 min from the start of this step):** Pipecat SmallWebRTC example and its client page → Deepgram STT + Gemini Talker + Aura-2 TTS. In the last 10 min, prove the per-turn injection (below) | You talk, it answers, interrupting it stops it, and an injected controller line changes the next question |
| 2 | `brain/schema.py` + `controller.py` + tests | Scoring/priority unit tests pass |
| 3 | Scribe hook + `/ledger` + Notes panel in `index.html` (9 rows, chips) | Rows fill and the focus changes while talking |
| 4 | Prompt tuning on 3 personas: vague, chatty, secretive | It probes, parks, asks consent, names contradictions |
| 5 | `brief.py` + `/brief` + leak check + tests | A planted secret is blocked; tests pass |
| 6 | `review.html` + Approve + export; switch TTS to Sarvam | Approve → `.md` + `.json` download |
| 7 | Read-back, silence nudge, text fallback (if time) | — |
| 8 | Rehearse the demo 3×, record a backup video | Under 4 min |

## 7b. UI: minimalist, enterprise grade (industry leaders will use it)

**Pages.** There are two, sharing one stylesheet `web/app.css`:
- `index.html`: the start screen, then the live interview. The live interview is a split view: the conversation on the left, **Birbal's Notes** live on the right, so judges see the notes fill while they talk.
  - After the gate, replace Pipecat's example page with our own page built on Pipecat's JS client from a CDN (verify the package names and versions). Never hand-write WebRTC.
- `review.html`: the Birbal Brief, version switcher, private-item toggles, leak-check status, Approve, export.
- Full wireframes and design tokens are in `docs/UI.md`; that file is the UI source of truth.
- `review.html`: the Birbal Brief, with redaction toggles, Approve and export.

**Look.** Think Linear, Stripe Dashboard or Vercel:
- **Colour:** a neutral greyscale with **one** accent colour.
- **Type:** Inter or the system UI font, on a 4/8 px spacing grid.
- **Surfaces:** 1 px hairline borders, 6–8 px radius, no heavy shadows.
- **Never:** gradients, emoji, stock illustrations.

**Colours.** CSS variables defined on `:root`, with light and dark themes via `prefers-color-scheme`. Semantic colours are used only for meaning:
- the four claim chips (Dekha/Suna/Socha/Chahiye) get muted, distinct tones;
- **Safe to share ✓** is green, **Secret found ✗** is red;
- the lock chip is amber.

**Hierarchy.** Each page has one primary action (Start interview / Approve). Everything else is secondary or ghost. Show only what's needed. Use quiet states: skeleton rows, not spinners; plain-language empty states.

**Live feel.**
- The interview page shows mic state (listening / Birbal speaking / thinking), a subtle audio level, and a running transcript.
- Board rows animate in (≤150 ms, honour `prefers-reduced-motion`).
- The current focus is highlighted.

**Quality bar.**
- WCAG AA contrast; full keyboard use; visible focus rings; `aria-live` for transcript and status.
- Works from 1280 px down to 375 px wide.
- No layout shift as rows arrive.

**Copy.** Short, calm, professional. No AI hype words.

## 7c. Event day (4 hours)

| Time | Do |
|---|---|
| 0:00–0:20 | **Voice gate:** keys in `.env`; read Gemini and Groq free limits (Talker defaults to Gemini; use Groq only if it shows ≥30K TPM). Then, in order: (1) answer with one word, "Yes." (if it hangs, set `BARGE_IN_MIN_WORDS=1`); (2) interrupt Birbal mid-sentence; (3) Type instead mid-voice; (4) one Hinglish sentence; (5) one Hindi sentence with हिंदी selected; (6) End → review → Approve → open the share link. Read Pipecat's TTFB logs once and tune only the slowest step. |
| 0:20–0:40 | `uv run python server/simulate.py` once; read the workbook; network + mic check; hotspot ready |
| 0:40–2:00 | Unseen-input testing: 5 problems from outside fintech; fix prompts; log every issue |
| 2:00–3:00 | Polish only (no new features); switch TTS to Sarvam; final redaction checks |
| 3:00–4:00 | Rehearse the demo 3×; record the backup video; charge the laptop |

## 8. Coding rules

- Write the smallest change that fully works. Reuse Pipecat/FastAPI/Pydantic features before writing your own. Add no abstraction "for later".
- Non-trivial logic gets a small test: controller, scoring, redaction, leak check, number normalisation.
- Mark every shortcut: `# shortcut: <limit>, <when to upgrade>`.
- Validate LLM JSON with Pydantic. On a parse failure, log it and skip that Scribe turn. Never crash the call.
- Every external call has a timeout and a fallback path. A failed Scribe call must never block the Talker.
- Keep the Talker prompt under about 1.5k tokens. Stream TTS.

## 9. Docs discipline (mandatory, as you go)

- `docs/IMPLEMENTATION_LOG.md`: after each build step, append the date/time, what was built, files touched, how it was verified (the command and its result), and what's next.
- `docs/ISSUES.md`: for every bug, error or surprise, log it **when it happens** with an ID, the exact error text, the cause, the fix, and the status. Never delete entries; mark them resolved.
- `docs/DECISIONS.md`: log every choice that changes the plan (stack swaps, the gate result, cuts, real free-tier numbers) with the reason and the alternatives.

Plain prose. Exact errors, commands and model IDs. Write the log entry before moving to the next step.

## 10. Demo expectations (`PLAN.md` §9)

The demo is 4 minutes, solo:
1. The stick-story hook.
2. You play a persona from a card to hit the planted moments: a vague claim, "Kaveri Bank" consent, a 40/day vs 1,200/week contradiction, "I don't know", and a barge-in.
3. A judge talks to it with their own problem.
4. For me vs For builders side by side, then **Secret found ✗** when the hidden name is typed in by hand.

The free-tier data caveat must be said out loud.
