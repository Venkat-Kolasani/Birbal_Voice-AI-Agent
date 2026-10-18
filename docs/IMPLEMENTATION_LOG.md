# Implementation log

Append one entry per build step, newest at the bottom.

Template:

```
## YYYY-MM-DD HH:MM — Step N: <title>
- Built: <what>
- Files: <paths>
- Verified: <command / action> → <result>
- Shortcuts added: <`# shortcut:` markers, or none>
- Next: <step>
```

---

## 2026-10-17 — Step −1: Planning
- Built: PLAN.md (full plan), AGENTS.md (build rules + UI spec §7b), .claude/CLAUDE.md (skills map), docs logs, .gitignore, .env.example. Pushed to github.com/Venkat-Kolasani/Voice-AI, one commit per file.
- Files: PLAN.md, AGENTS.md, .claude/CLAUDE.md, docs/*.md, .gitignore, .env.example
- Verified: n/a (no code yet)
- Next: Step 0, create keys and record the real free-tier limits in DECISIONS.md.

## 2026-10-17 — Step −1b: Event-format update + UI design
- Built: switched the plan to building before the event (4-hour event, pre-written code allowed); added docs/UI.md (wireframes, tokens, states); two-page UI.
- Files: AGENTS.md, .claude/CLAUDE.md, PLAN.md, docs/UI.md, docs/DECISIONS.md
- Verified: n/a (docs only)
- Next: Step 0, keys and free-tier limits.

## 2026-10-17 23:00–23:50 — Pre-event build (steps 0–7 except key-dependent checks)
Status per module. **Verified** = covered by tests (31 passing) and/or a Chrome check. **Unverified** = needs API keys.

| File | What | Status |
|---|---|---|
| pyproject.toml, uv.lock | deps; pipecat-ai[deepgram,google,groq,sarvam,elevenlabs,silero,webrtc,runner]==1.12.0 | verified (`uv sync`) |
| server/brain/schema.py | Claim, Sensitive, Ledger, ScribeOutput, GapReport; Hinglish kind labels | verified |
| server/brain/controller.py | merge, score 0/1/2, priority (consent > contradiction > current_state > first unsettled > readback) | verified (test_controller) |
| server/brain/brief.py | canonical brief, code redaction, number normalisation (k/lakh/crore), leak check, 3 versions, Markdown | verified (test_brief) |
| server/brain/prompts.py | Talker system prompt, controller note, Scribe prompt (compact example), extras prompt | unverified (needs LLM) |
| server/brain/llm.py | Gemini → Groq JSON + text completion, timeouts, never raises | unverified (needs keys) |
| server/brain/scribe.py | Scribe call + salvage of partially valid JSON; brief extras | unverified (needs keys) |
| server/brain/session.py | transcript, background Scribe, state(), brief(), overrides, replay | verified (test_replay) |
| server/fixtures/demo_interview.json | 13-turn fictional Kaveri Bank interview; focus matches every turn | verified |
| server/api.py | state/start/replay/turn/end/brief/choice/edit/approve/export; server-side leak block; /api/offer | verified except /api/turn and /api/offer (need keys) |
| server/bot.py | Pipecat pipeline, ControllerNote, StatusTap, TTS switch, idle nudge | import + construction + rewrite test verified; live voice unverified |
| web/app.css, common.js | tokens per docs/UI.md, light/dark, icons, helpers | verified in Chrome |
| web/index.html | start screen, split live view, Notes panel with "Asking because", text composer, keyboard | verified in Chrome via replay |
| web/review.html | versions, private-item toggles, leak badge, editable problem, quote popover, approve dialog, export | verified in Chrome |
| web/voice.js | minimal SmallWebRTC client, mic level, mute | unverified (needs keys) |

- Shortcuts: `MIN_LEAK_NUMBER` (brief.py), no ICE trickle (voice.js).
- Next (event day): keys → `/api/turn` text test → voice gate → prompt tuning on 5 unseen problems → Sarvam voice → rehearse.

## 2026-10-17 23:50–00:30 — Real product + interview quality
| File | What | Status |
|---|---|---|
| server/brain/session.py | session id, to_dict/from_dict, SessionStore (atomic JSON, id validation), redacted summary titles, extras cached per turn count | verified (test_api: isolation, restart, malicious id) |
| server/api.py | every route per session; /api/health, /api/sessions, /api/mode; voice offer routed by request_data.session | verified except /api/offer (needs keys) |
| web/index.html | session in URL, resume on refresh, Type instead mid-voice (T), readiness line, recent briefs | verified in Chrome (demo + home) |
| web/review.html | per-session calls, New interview link, not-found state | verified in Chrome |
| web/voice.js | sends session id | unverified (needs keys) |
| server/brain/prompts.py | echo / vocabulary / funnel / no-why / one-? rules, exemplar question shapes, Last noted, Scribe context window | rules present (test_prompts); quality unverified |
| server/brain/llm.py | provider routing (Talker=groq, Scribe=gemini), temperature 0.4, gpt-oss reasoning low | unverified (needs keys) |
| server/bot.py | VAD stop_secs, min-words barge-in, Sarvam STT option, talker provider | construction verified; live unverified |
| server/simulate.py, fixtures/personas.json | persona-driven interview eval with scorecard | import verified; run needs keys |
| .env.example | every setting documented | — |

38 tests pass.

## 2026-10-18 00:30–01:10 — Speed, failover, languages
| File | What | Status |
|---|---|---|
| server/brain/keys.py | key pools, round-robin, 60 s cooldown on rate limits | verified (test_keys) |
| server/brain/llm.py | `_try`: every key of every provider; healthy provider first | verified (test_keys, mocked) |
| server/bot.py | per-language STT/TTS/LLM selection, key pools, `on_pipeline_error` → status error, VAD 0.4 | construction verified for auto/en/hi/kn; live unverified |
| server/brain/prompts.py | native Hindi/Kannada opening lines; spoken-style rule | unverified (needs TTS) |
| server/api.py | lang on start/voice; /api/health shows key counts; error cleared on switching to typing | verified (tests pass) |
| web/index.html, app.css | language selector; auto-switch to typing on voice error | selector verified in Chrome; auto-switch unverified |

42 tests pass.

## 2026-10-18 00:10–00:40 — Motion, share link, autosave, LAN
| File | What | Status |
|---|---|---|
| server/brain/session.py | dirty flag + autosave, share token mint/lookup (constant-time compare), interim transcript, replay simulates live transcription | verified (test_api: share, revoke, restart mid-interview) |
| server/api.py | /b/<token>, /api/shared/<token> (builder + public only), autosave task, token revoked on edit/choice | verified |
| server/bot.py | TranscriptTap (interim → UI); Auto mode follows language switches in Roman script | construction verified; live unverified |
| web/index.html, app.css | live transcript with caret, speaking ripples, thinking spinner, word reveal, keyed rows with upgrade flash | verified in Chrome (replay) |
| web/review.html | Copy share link; read-only shared mode | verified in Chrome |
| scripts/serve_lan.sh | self-signed HTTPS on the LAN IP | verified with `curl -k` from the laptop; phone not tested |

44 tests pass.

## 2026-10-18 — Advisor review fixes
- `server/bot.py`: the note goes on the last user message; the idle nudge is user-role; errors switch to typing only on fatal or 2 in 10 s; a stray duplicate handler was removed (ISS-011). Construction verified; live unverified.
- `server/brain/llm.py`: Talker default is Gemini.
- `server/brain/session.py`: `retract_owner`; a restored session's status is listening.
- `server/api.py`: retract on a failed turn.
- `.env.example`: notes on TALKER_PROVIDER and BARGE_IN_MIN_WORDS.
- `AGENTS.md`: voice-test checklist; test count corrected.

46 tests pass.

## 2026-10-18 event day — Key tests with real providers
- Verified: Deepgram (200), Sarvam TTS (200, audio), Supabase `sessions` and `board` tables reachable (200), Groq (0.6–0.8 s), Gemini flash-lite (0.9–1.6 s). Typed turn through `/api/turn`: 3.6 s, good question, Scribe rows filled. Simulator (vague persona): 8/9 coverage in 6 turns, consent asked in-turn, readback correct, no bad questions.
- Changed: `GEMINI_TALKER_MODEL` (flash-lite) separate from `GEMINI_MODEL`; both now flash-lite. Generalisation guard. Simulator prints leaks and saves sessions to `data/sim/`.
- Unverified still: voice end to end (needs the mic at the venue).
- 47 tests pass.

## 2026-10-18 — Landing page, routes, providers
- Built: `web/landing.html` at `/` (hero, self-playing interview example, four grades, privacy features, benchmark stats); the app moved to `/start`; links updated.
- Providers set: Talker Groq gpt-oss-120b; Scribe Command Code gpt-5.6-luna; Gemini flash-lite in the chain. Benchmark 27/28 (96%).
- Verified: all routes 200; landing checked in Chrome at 1440 px. 51 tests pass.
