# Issues

Log every bug, error or surprise **when it happens**. Never delete an entry; set its status to resolved.

Template:

```
## ISS-NNN — <short title>  [open | resolved | wontfix]
- When: YYYY-MM-DD HH:MM, step N
- Symptom: <exact error text / observed behaviour>
- Cause: <root cause, or "unknown yet">
- Fix: <what changed, files>
- Verified: <how>
```

---

## ISS-001 — `hidden` attribute ignored on styled elements  [resolved]
- When: 2026-10-17, UI build
- Symptom: live-view panels and header pills showed on the start screen.
- Cause: `.btn`, `.pill` and `.live` set `display`, which overrides the UA `[hidden]` rule.
- Fix: `[hidden] { display: none !important; }` in web/app.css.
- Verified: Chrome screenshot.

## ISS-002 — `.live` class collision  [resolved]
- When: 2026-10-17, UI build
- Symptom: the "Live" pill stretched to 474 px with a giant ring artifact.
- Cause: the pill used `class="pill live"`, and `.live` was also the split-layout grid.
- Fix: renamed the layout class to `.split`.
- Verified: Chrome screenshot.

## ISS-003 — Interview timer kept running after the end  [resolved]
- When: 2026-10-17, review page
- Symptom: "Interview length" kept increasing on /review.
- Fix: `Session.finish()` records `ended_at`; `minutes()` uses it.
- Verified: replay → review.

## ISS-004 — Duplicate open question for a dimension with an unknown  [resolved]
- When: 2026-10-17, advisor review
- Cause: `canonical()` compared dimension keys against labels.
- Fix: compare keys.
- Verified: assertion in test_replay.

## ISS-005 — Consent question one turn late  [resolved by prompt]
- When: 2026-10-17, advisor review
- Cause: the Scribe lags one turn, so CONSENT reaches the Talker a turn late.
- Fix: a Talker rule to ask consent immediately when a specific name or figure is said.
- Verified: not yet. Needs a live test with keys.

## ISS-006 — ControllerNote would strip the opening and idle-nudge messages  [resolved]
- When: 2026-10-17, advisor review of bot.py
- Cause: notes were stripped by prefix.
- Fix: strip only the last injected note (`bot.rewrite`); the opening line is now a `TTSSpeakFrame`.
- Verified: test_bot.

## ISS-007 — Voice path untested  [open]
- When: 2026-10-17
- Symptom: no API keys tonight.
- Next: with keys, run gate step 1: Start interview → speak → interrupt.

## ISS-008 — No ICE trickle in web/voice.js  [open, by design]
- When: 2026-10-17
- Symptom: the client waits up to 2.5 s for full ICE gathering.
- Next: fine on localhost; add PATCH /api/offer trickle only if remote access is needed.

## ISS-009 — Voice disconnect ended the interview  [resolved]
- When: 2026-10-17, advisor review
- Symptom (would have): "Type instead" mid-voice gave 409 "interview has ended"; a refresh during voice jumped to review.
- Cause: `on_client_disconnected` called `session.finish()`.
- Fix: a disconnect only stops the pipeline and sets status to listening. Ending happens only via /api/end. /api/mode no longer cancels the task (pc.close() does it cleanly).
- Verified: code review; live check needs keys.

## ISS-010 — Recent-briefs list showed private names  [resolved]
- When: 2026-10-17, Chrome check
- Symptom: the start screen title contained "Kaveri Bank".
- Fix: the summary title comes from the redacted builder version.
- Verified: test_api asserts "Kaveri" is not in the title; Chrome.

## ISS-011 — Voice owner turns would never have been recorded  [resolved]
- When: 2026-10-18, found while applying advisor fixes
- Symptom (would have): in voice mode the transcript and notes would never get owner turns, because `on_user_turn` held a stray copy of the error handler.
- Cause: an earlier unchecked `str.replace` matched `idle_nudged = False` twice and inserted the error handler inside `on_user_turn`.
- Fix: removed the stray block. All later edits use assert-count-1 replacements.
- Verified: full read of run_bot; tests pass. Live voice still unverified.

## ISS-012 — Controller note as a "developer" message could break Groq  [resolved]
- Cause: Pipecat's OpenAI-compatible services send "developer" as-is (`supports_developer_role=True` in openai/base_llm.py).
- Fix: `bot.rewrite` attaches the note to the last user message (same as text mode); the idle nudge is user-role.
- Verified: test_bot.

## ISS-013 — Failed typed turn recorded twice  [resolved]
- Fix: `Session.retract_owner()` on a Talker failure.
- Verified: test_api.

## ISS-014 — Gemini flash models capped at 20 requests/day on the free tier  [resolved by model choice]
- When: 2026-10-18 event day, first simulator run
- Symptom: `429 RESOURCE_EXHAUSTED ... quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20` on gemini-3.6-flash and 3.5-flash.
- Fix: both roles on `gemini-flash-lite-latest`; Groq failover. Avoid any 3.x-flash call for the rest of the day.

## ISS-015 — Scribe generalisation repeated the secret  [resolved]
- When: 2026-10-18, simulator "vague" persona: builder version flagged unsafe by the leak check.
- Cause: the LLM wrote a generalisation containing the number it was meant to hide.
- Fix: `_safe_generalisation` in brief.py; test added.

## Known risks to watch (not yet issues)
- flash-lite daily quota unknown; if it 429s mid-event, Groq carries text mode (8K TPM is enough for typed turns and the Scribe) and voice degrades to typing.
- Pooling API keys from several accounts may breach provider terms (Google APIs ToS 2(d); Groq 6.3(d)(iii)). The risk is suspension on demo day.
- Hindi/Kannada: Sarvam TTS with `hi-IN`/`kn-IN` and LLM output in native script are untested. Romanised Hindi may sound off, so check during the gate.
- Kannada STT (Sarvam saaras auto-detect + codemix) is untested; Deepgram `multi` doesn't cover Kannada.
- Voice failover is per interview, not mid-stream. A provider failing mid-interview switches the UI to typing (by design).
- (Mitigated: Talker now defaults to Gemini.) Talker on Groq in the voice path has no automatic fallback (Pipecat's GroqLLMService). ~2k tokens/call × ~5 calls/min ≈ 10k TPM vs the published 8K TPM for gpt-oss-120b, so a voice interview could go silent mid-way. Check the dashboards at the event start; if Groq TPM ≤ 8K, set TALKER_PROVIDER=gemini.
- Interviews in progress are only saved on End/Approve. A server restart mid-interview loses that interview.
- Gemini free-tier RPM/RPD unknown until signup; one interview ≈ 80 LLM calls (~10 RPM).
- Groq `openai/gpt-oss-120b` published limit is 8K TPM, and may be lower on the free plan.
- Sarvam credit: docs say ₹100, the pricing page says ₹1,000.
- Deepgram Nova-3 quality on Hindi–English code-switching not tested.
- The cascade adds ~1 s latency per turn; barge-in must be tested inside the 90-min gate.
- WebRTC through venue NAT: demo from the laptop itself, not a judge's phone.
