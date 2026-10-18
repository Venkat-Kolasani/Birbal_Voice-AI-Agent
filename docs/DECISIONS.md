# Decisions

One entry per decision that changes the plan. Newest at the bottom.

Template:

```
## D-NNN — <decision>  (YYYY-MM-DD)
- Context: <why a choice was needed>
- Decision: <what>
- Alternatives: <considered, and why not>
- Consequence: <what this commits us to>
```

---

## D-001 — Challenge 2, product named Birbal  (2026-10-17)
- Context: needed a name that is easy to say and relate to, and India-centric.
- Decision: "Birbal" (Akbar–Birbal stories: the truth is found by asking the right question). Tags: Dekha/Suna/Socha/Chahiye.
- Alternatives: Tearline, Panchnama, Sanjaya, Khulasa: either harder to relate to or police/mythology-heavy.
- Consequence: the stick story opens the demo; the research (Cognitive Interview, Admiralty Code, tearlines) is the backing.

## D-002 — Cascade voice pipeline (Pipecat) instead of Gemini Live  (2026-10-17)
- Context: the user wants a human Indian voice; Gemini Live native-audio models support only the AUDIO modality, so the voice can't be swapped.
- Decision: Pipecat cascade: Deepgram STT → Gemini Flash Talker → Sarvam bulbul:v3 TTS. Talker + Scribe split.
- Alternatives: Gemini Live (simpler, sub-second, but fixed voice) is kept as Plan B; Vapi ($10 trial, US numbers); ElevenLabs Agents (~15 free min); Maya1 (English-only, 16 GB GPU, no hosted API).
- Consequence: ~1 s per-turn latency; the 90-minute gate decides between cascade and Plan B.

## D-003 — ₹0 stack  (2026-10-17)
- Context: the user can't pay beyond an existing Claude subscription.
- Decision: Gemini free tier, Deepgram $200 credit (official: no card, no expiry, covers Aura), Sarvam ₹100 credit, Groq free tier, ElevenLabs free tier (10k credits/month; commercial licence only on paid plans). Pipecat (BSD-2).
- Consequence: Gemini free-tier data may be used by Google; say so in the pitch.

## D-004 — Verified free-tier limits  (fill in at Step 0)
| Service | Limit seen in dashboard | Date checked |
|---|---|---|
| Gemini `gemini-3.8-flash` RPM / RPD | | |
| Gemini Live (Plan B) sessions / RPD | | |
| Deepgram credit balance | | |
| Sarvam credit balance | | |
| Groq `openai/gpt-oss-120b` RPM / TPM / TPD | | |
| ElevenLabs credits | | |

## D-005 — Minimalist, enterprise-grade UI  (2026-10-17)
- Context: industry leaders will try the product live.
- Decision: three plain HTML pages sharing one token-based stylesheet: neutral palette with one accent, Inter/system font, light and dark themes, WCAG AA. Full spec in AGENTS.md §7b.
- Alternatives: Pipecat's example client UI as-is (fine for the gate, but looks like a dev tool); a React/Vite app (adds a build step for a solo one-day build).
- Consequence: after the gate, the interview page is rebuilt on Pipecat's JS client from a CDN, styled to match.

## D-006 — Build before the event; 4-hour event = test and rehearse  (2026-10-17)
- Context: the event is 4 hours and pre-written code is allowed; judges care most about an enterprise-grade demo.
- Decision: build the full product beforehand (AGENTS.md §7). Use the event for workbook mapping, unseen-input testing, polish and rehearsal (AGENTS.md §7c).
- Consequence: the 90-minute gate still applies to the pre-event spike.

## D-007 — Two-page UI with a split live view  (2026-10-17)
- Context: the strongest demo moment is the notes filling while someone talks; separate pages would hide it.
- Decision: `index.html` (start + live split view: conversation and Birbal's Notes) and `review.html`. Peacock-teal accent, Inter + Source Serif 4. Spec in docs/UI.md.
- Alternatives: three pages (board separate): needs two windows during the demo.

## D-008 — Pipecat 1.12 wiring (found in source; voice path UNTESTED)  (2026-10-17)
- Context: Pipecat 1.12.0 is newer than prior knowledge; the API was read from the installed package and v1.12.0 examples.
- Decision:
  - **Pipeline:** `transport.input → DeepgramSTT → user_agg → ControllerNote → LLM → TTS → transport.output → StatusTap → assistant_agg`.
  - **Aggregators:** `LLMContextAggregatorPair(LLMContext(), user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer(), user_idle_timeout=8.0))`.
  - **Events:** `on_user_turn_stopped(agg, strategy, message)` calls `session.add_owner`, which starts the Scribe as an asyncio task (never awaited in the pipeline). `on_assistant_turn_stopped(agg, message)` calls `session.add_birbal`. `on_user_turn_idle` sends a one-time `LLMMessagesAppendFrame` nudge.
  - **Controller note:** `ControllerNote` intercepts the downstream `LLMContextFrame` and swaps last turn's note for a fresh one via `context.set_messages` (`bot.rewrite`). The Gemini adapter turns non-initial developer messages into `user` role (`gemini_adapter.py` ~l.480).
  - **Opening line:** `TTSSpeakFrame(OPENING_LINE)`. Its `append_to_context` defaults to True, so there is no LLM call and no manual `add_message`.
  - **Transport:** a `SmallWebRTCRequestHandler` runs in-process in `api.py` (`POST`/`PATCH /api/offer`), so the bot shares the single `Session`.
  - **Browser client:** a minimal client in `web/voice.js`. It does not use the prebuilt client, to avoid a CDN dependency.
  - **STT:** `DeepgramSTTService.Settings(model="nova-3", language="multi")` for Hinglish.
- Alternatives: the Pipecat runner process with the prebuilt `/client` was rejected; it needs a second process and can't share the session.
- Consequence: verify first thing once keys exist, as gate step 1. Unknowns: whether Deepgram accepts `language="multi"` via Settings, Gemini handling of consecutive user messages, and barge-in feel.

## D-009 — Controller picks the first unsettled dimension in brief order  (2026-10-17)
- Context: the "zeros first" rule jumped away from vague answers. It also made the demo replay show a focus that didn't match Birbal's question.
- Decision: after consent, contradiction and current_state, focus on the first dimension in table order that is not settled (score < 2 and no unknown-with-lead). This follows "numbers over adjectives": a vague answer is deepened right away.
- Consequence: the fixture was reordered to follow the brief order; the focus matches Birbal's question on every turn.

## D-010 — Replay mode as built-in demo fallback  (2026-10-17)
- Decision: `/?demo=1` shows **Play demo**, which drives the live UI from a scripted fixture with pre-baked Scribe output. No keys or network needed (except Google Fonts).
- Consequence: if venue wifi or keys fail, the full split-view and review flow still demos.

## D-011 — Interview quality: listening, questions, understanding  (2026-10-17, unverified until keys)
- **Listening:**
  - Every reply opens by echoing one concrete detail in the owner's own words. This is a reflective-listening signal, and it also surfaces STT mishearings of numbers.
  - The Talker reuses the owner's vocabulary.
  - The controller note carries "Last noted:" so the echo is precise.
  - Voice turn-taking is patient: `VADParams(stop_secs=0.8)`, Pipecat's default smart-turn stop strategy, and barge-in only after `MinWordsUserTurnStartStrategy(min_words=2)` to ignore noise.
  - `STT_PROVIDER=sarvam` (saaras:v3, codemix) is available for Hinglish-heavy speakers.
- **Questions:**
  - Hard rules: one question mark, ≤25 words, no leading questions, never open with "Why".
  - Questions go deeper in a funnel: open, then narrow, then confirm.
  - The note carries 2–3 exemplar question shapes per dimension, using incident recall and context reinstatement from the Cognitive Interview research.
  - Readback is one fact per sentence, so the owner can object.
- **Understanding:**
  - The Scribe sees the earlier conversation, not just the last exchange, so it can resolve "that number".
  - The Scribe runs on the stronger model (Gemini) off the hot path; the Talker runs on the faster one (Groq, `reasoning_effort=low`) at temperature 0.4.
- **Measurement:** `server/simulate.py` runs 3 personas (vague, chatty Hinglish, secretive with a contradiction). It scores coverage, turns to 8/9, secrets caught, builder-version safety, and question hygiene (long, double, "why"-first, empty acknowledgement).
- Consequence: run the simulator in the first 30 minutes of the event; tune one prompt change at a time.

## D-012 — Real multi-session product, not a single demo  (2026-10-17)
- Decision:
  - **Sessions:** each interview has an id, and every API route takes `?s=<id>`.
  - **Storage:** finished sessions are saved atomically to `data/sessions/<id>.json`.
  - **Voice:** the WebRTC offer carries `request_data.session`, so voice attaches to the right interview.
  - **Recovery:** a refresh resumes; mid-interview switching to typing is supported.
  - **Start screen:** recent briefs, with titles from the redacted builder version, plus a readiness line for voice and AI.
- Consequence: several judges can run interviews back to back without overwriting each other, and briefs survive a restart.

## D-013 — Speed, failover, human voice, languages  (2026-10-17, voice parts unverified until keys)
- **Smart-turn is active.** Pipecat's default stop strategy is `LocalSmartTurnAnalyzerV3`, and its ONNX model ships in the package (`audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx`), so there's no download on venue wifi. Because it judges whether a sentence is finished, `VAD_STOP_SECS` dropped from 0.8 to 0.4 (Pipecat default 0.2) for faster replies.
- **Latency:** `enable_metrics` logs TTFB per service. During the gate, read STT final → LLM TTFB → TTS TTFB and move only the biggest number (usually the Talker provider/model). Other levers: Groq gpt-oss `reasoning_effort=low`, Talker temperature 0.4, a deterministic opening line (no LLM call), and the Scribe kept off the hot path.
- **Failover:**
  - **Key pools:** `brain/keys.py` holds comma-separated pools per provider (`GOOGLE_API_KEYS`, `GROQ_API_KEYS`, …). A rate-limited key (429 / RESOURCE_EXHAUSTED / quota) rests 60 s.
  - **Text mode:** text and Scribe calls try every key of every provider in order.
  - **Voice:** each interview picks the currently healthy provider and key. Any pipeline error (`on_pipeline_error`) sets status `error`, and the UI switches to typing in the same interview.
- **Terms:** Google APIs ToS §2(d) says *"You agree to, and will not attempt to circumvent, such limitations documented with each API."* Groq §6.3(d)(iii) bans use *"in a manner intended to avoid incurring Fees"*, and §7 allows suspension. Pooling keys from several accounts risks suspension. Provider diversity (Gemini + Groq) plus degrade-to-typing is the terms-clean protection. The user decides what goes in `.env`.
- **Human-like voice:**
  - Pick the Sarvam `bulbul:v3` speaker by ear in the Sarvam playground, and set `SARVAM_VOICE` / `SARVAM_PACE`.
  - The Talker prompt adds spoken style: contractions, no lists or markdown, numbers under twenty as words.
- **Languages:**
  - **Selector:** the start screen offers Auto / English / हिंदी / ಕನ್ನಡ (Kannada, since the event is at Paytm Bengaluru).
  - **Talker:** a "Conduct the interview in …" line, with native script so Sarvam TTS pronounces it well. The opening lines are written natively.
  - **TTS:** hi/kn switch Aura to Sarvam automatically.
  - **STT:** kn uses Sarvam STT (saaras auto-detect); hi/auto use Deepgram `multi`.
  - **The brief is always in English** (Scribe `value` in English, quotes verbatim). Pitch line: *"Interview in Kannada, brief in English."*
- Follow-up (not built): per-turn automatic language switching, using runtime TTS settings updates (see Pipecat's Sarvam example).

## D-014 — Motion, share link, autosave, other devices, deployment, language switching  (2026-10-18)
- **Motion** (verified in Chrome via replay):
  - **Live transcript:** a "You · live" line with a caret while the owner speaks, fed by `TranscriptTap` after STT using `InterimTranscriptionFrame`. Replay simulates it word by word.
  - **Orb states:** ripples and a pulse while Birbal speaks, a dashed spinner while thinking, breathing while listening.
  - **Replies:** Birbal's newest reply reveals word by word.
  - **Notes rows:** created once and patched in place, flashing only when a row upgrades (score or kind). `prefers-reduced-motion` is honoured.
- **Share link:**
  - **Creation:** Approve mints `secrets.token_urlsafe(16)`, and `/b/<token>` is a read-only view.
  - **What it shows:** only the builder and public versions. Never the owner version or the private list, and only while those versions are leak-free.
  - **Revocation:** any change after approval (a choice or an edit) revokes the link. **Anyone with the URL can read the builder brief.**
- **Autosave:** sessions carry a `dirty` flag, and a background task saves changed live sessions every 5 s. In-progress interviews survive a restart and resume by typing.
- **Other devices:** `scripts/serve_lan.sh` serves HTTPS on the laptop's LAN IP with a 7-day self-signed certificate (browsers need HTTPS for the mic off localhost). `curl -k` to the LAN IP works from the laptop. Not yet tested from a phone.
  - **Conditions:** the other device must be on the same network. A phone hotspot is recommended, since guest wifi often blocks device-to-device traffic. Without TURN, WebRTC only works when both are on the same network.
  - **Fallback:** typed interviews work over plain LAN HTTP too.
- **Deployment (evaluated, not built):**
  - **Typed mode** is plain HTTP + Python and deploys anywhere that runs a long-lived Python process (a small VM, Render, Fly.io, Railway; check each free tier). Set `BIRBAL_DATA` to a persistent disk.
  - **Voice over the internet** needs WebRTC through NAT, so it needs TURN. Options: (1) switch the transport to Daily (Pipecat `DailyTransport`; Daily has a free tier, verify current minutes) and run the bot on any VM; (2) Pipecat Cloud; (3) self-host coturn next to SmallWebRTC.
  - **Production must-dos:** auth on owner routes; per-session secrets (the session id currently acts as the owner's capability); paid LLM tiers (free-tier data may be used for training); HTTPS.
  - **For the event:** laptop + hotspot.
- **Mid-interview language switching:** in Auto, the Talker follows a language switch but writes it in Roman script, so the `en-IN` Sarvam voice (Hinglish-native) stays natural. Explicit हिंदी/ಕನ್ನಡ use native script plus `hi-IN`/`kn-IN`. Switching the TTS locale per turn is not built.

## D-015 — Advisor review fixes  (2026-10-18)
- **Controller note:** it rides on the last user message in voice too, for provider-agnostic behaviour identical to text mode. No "developer" role reaches Groq.
- **Talker default:** Gemini. Voice resends the whole conversation, about 16–20K TPM versus Groq's published 8K. Groq is failover only, unless its dashboard shows ≥30K TPM.
- **Voice errors:** voice switches to typing only on a fatal `ErrorFrame` or 2 errors within 10 s. A single transient error is logged.
- **Failed typed turn:** it is retracted, so a retry isn't recorded twice.
- **Restored in-progress session:** its status is "listening".
- **One-word answers:** `MinWordsUserTurnStartStrategy(min_words=2)` replaces Pipecat's default start strategies, so a lone "Yes." may not start a turn. This goes into the voice test; the knob is `BARGE_IN_MIN_WORDS=1`.

## D-016 — Real free-tier measurements and model choice  (2026-10-18, event day)
- **Gemini free tier (measured):** `gemini-3.6-flash` and `gemini-3.5-flash` allow **20 requests/day per model** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit: 20). Both were exhausted after one simulator run. `gemini-3.8-flash` works but takes ~28 s per reply even with thinking off. `gemini-flash-lite-latest` answers in ~0.9–1.6 s and had quota left after ~60 calls (its daily cap is unknown).
- **Groq (measured):** `openai/gpt-oss-120b` 0.6 s per Talker reply, **8,000 tokens/min**, 1,000 requests/day. `llama-3.3-70b-versatile` returns 404 on this account.
- **Decision:** Talker and Scribe both on `gemini-flash-lite-latest`; Groq gpt-oss-120b as failover for both. Groq stays off the voice hot path because of the 8K TPM cap.
- **Observed with real models:** Scribe tags kinds sensibly (11 Dekha / 0 Suna / 3 Socha / 1 Chahiye on the vague persona), catches secrets with usable generalisations, and the Talker echoes a detail, asks consent within the same turn, reads back, and asks zero bad questions. One simulator run reached 8/9 coverage in 6 turns.
- **Fixed:** a Scribe-written generalisation can repeat the secret ("about 120 returns weekly"); `_safe_generalisation` now falls back to the generic placeholder. The leak check had already blocked the version.
- **Risk:** Gemini 503 "high demand" appeared 3 times in ~60 calls. Text mode fails over per key/provider; voice has no in-pipeline failover, so two errors in 10 s switch the UI to typing.

## D-017 — Third LLM provider: Command Code, model gpt-5.6-luna  (2026-10-18)
- Context: Gemini's free daily quota was spent by midday; Groq alone (8K TPM) collided with itself. Cerebras needs a card; Mistral's free workspace returned 429 with a 0 req/min limit.
- Measured on Command Code (OpenAI-compatible `https://api.commandcode.ai/provider/v1`), Talker / Scribe latency and grade quality on one tricky line:
  - `gpt-5.6-luna`: 3.9 s / 7.8 s, grades correct, $0.20/$1.20 per M tokens → **chosen fallback**
  - `deepseek/deepseek-v4.1-flash-fast`: 2.1 s / 14.1 s, grades mostly right
  - `deepseek/deepseek-v4.1-flash`: 4.6 s / 25 s, graded "hearsay" wrongly (reasoning model)
  - `z-ai/glm-5.3-flashx`: 5.6 s / 13.6 s, grades correct
  - `gpt-6-luna`: 3.4 s / 10.8 s, graded "hearsay" wrongly
  - `xiaomi/mimo-v2.6-flash` 9 s, `Qwen3.8-Flash` 7 s + Scribe timeout, `Qwen3.7-Flash` 20 s, `claude-haiku-5-5` 2.2 s then a 403/62 s stall (needs the Anthropic-format route)
- Order stays Gemini → Groq → Command Code. The alt provider is only hit when both free tiers are limited. Cost on a $10 plan: a full interview ≈ ₹2–5.
- Benchmark (Groq gpt-oss-120b, 28 labelled sentences): **27/28 = 96%** grade accuracy; the one miss graded an opinion ("drivers are lazy") as Seen.
