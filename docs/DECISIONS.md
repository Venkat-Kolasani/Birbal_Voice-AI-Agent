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
