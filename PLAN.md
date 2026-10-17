# BIRBAL — a voice agent that debriefs problem givers

*"Akbar had Birbal. Now every builder does."* · *Problem bolo, Birbal samjhega.*

Challenge 2: Problem Intake Agent. AI Garage × Paytm Voice AI Buildathon, Bengaluru. **Solo build.**

Budget: **₹0**. Free tiers and signup credits only. Every "verify tonight" item must be checked by actually signing up, not by searching.

---

## 0. Names (use these everywhere: UI, demo, pitch)

| Piece | Name in the UI and pitch | Internal / code name |
|---|---|---|
| Product + voice agent | **Birbal** | Talker |
| Background note-taker | **Birbal's Notes** | Scribe |
| Picks the next question | (not shown) | Controller |
| Claim ledger | **Birbal's Notes** board | Ledger |
| Output | **Birbal Brief** | Brief |
| Three versions | **For me** / **For builders** / **For everyone** | owner / builder / public |
| Redaction choice | **Share as is** / **Hide name** / **Remove** | keep / generalise / remove |
| Leak check | **Safe to share ✓** / **Secret found ✗** | leak check |

**Claim tags on the board.** Every chip shows the Hindi word and the English meaning, because some judges may not speak Hindi:

| Chip | Data value | Meaning |
|---|---|---|
| **Dekha · Seen** | `observed` | Saw it themselves |
| **Suna · Heard** | `hearsay` | Someone told them |
| **Socha · Guessed** | `inferred` | Their own conclusion |
| **Chahiye · Wished** | `aspiration` | What they want |

Every item always appears in **For me**. The redaction choice only controls **For builders** and **For everyone**: **Share as is** shows it unchanged, **Hide name** swaps in a generalisation ("a partner bank"), and **Remove** drops it.

---

## 1. The story (open the demo with this)

**The hook: Birbal and the sticks.** Something was stolen. Birbal gives each suspect a stick and says the thief's stick will grow an inch overnight. In the morning, one stick is an inch shorter: the guilty man cut his. Birbal found the truth through a clever question, not an accusation. *"Birbal doesn't accept what people claim. He finds what actually happened. That's what a builder needs from a problem owner."*

The research behind the method (say this after the hook, briefly):


> Every builder has received a problem like this: *"Our merchants find onboarding confusing."*
> That sentence has no facts in it. It doesn't say who, how often, or compared to what. It doesn't say what was tried, or what is secret.
>
> Problems reach builders the way intelligence reaches analysts. It comes secondhand and partial, and it mixes what someone *saw* with what they *concluded*. Some of it can't be shared.
> Intelligence services and forensic interviewers solved this decades ago, with three habits:
>
> 1. **Debrief, don't survey.** Ask the person to walk through *the last time it happened*. Generic questions get opinions. Specific past incidents get facts. (Cognitive Interview meta-analysis: 42 studies, ~2,500 people. Correct details rose sharply (d=0.87). Incorrect details also rose a little (d=0.28), and accuracy stayed flat at 85% vs 82%. The Mom Test and JTBD "switch" interviews apply the same idea to product discovery.)
> 2. **Grade every claim.** An analyst never writes "X is true". They write "X, reported by a source who saw it" or "X, hearsay". (NATO's Admiralty Code, from STANAG 2511 / AJP-2.1, rates source reliability A–F and information credibility 1–6 separately.)
> 3. **Write above and below the tearline.** A classified report has a dashed line. Above it is the full report with sources. Below it is a sanitized version that keeps the substance, so it can go to a wider audience (US ICD 209).
>
> A real debrief has two people: one who **talks** and one who **takes notes**. Birbal works the same way. **Birbal** (the Talker) runs the conversation, and **Birbal's Notes** (the Scribe) grades every claim in the background as Dekha / Suna / Socha / Chahiye.
>
> Incident recall gets you *more* material at about the same accuracy. More raw material needs grading, so habit 2 is not optional. That's why every claim in the ledger carries a kind and an evidence quote.

**Don't overclaim.** Say "the forensic research shows incident recall beats open questions". Do not say "our agent is 87% better". Davin (Cookiy AI) runs AI-moderated qualitative research and will know this literature.

---

## 2. Requirements audit (every line of the brief → where it's satisfied)

| Requirement (from the brief / judges' email) | How Birbal satisfies it | Status |
|---|---|---|
| What is happening today? | Dimension `current_state`. Counts as sufficient only once one concrete recent incident has been walked through | ✅ |
| Who experiences the problem? | `who`: a role or segment plus a rough count | ✅ |
| How is it currently solved? | `workaround`, including its cost | ✅ |
| Why does it matter? | `impact`, in numbers or a named downstream effect | ✅ |
| How frequently? | `frequency` as a number per time unit; adjectives get re-probed | ✅ |
| Constraints? | `constraints`, or an explicit "none known" | ✅ |
| What was attempted? | `attempted`, plus why it stalled | ✅ |
| What is confidential? | Consent asked at the moment of disclosure, plus the Review screen | ✅ |
| Useful outcome? | `success_test`: "we'd know it worked if…" | ✅ |
| Follow-ups, not a questionnaire | Controller picks the next focus from gaps each turn; the Talker never sees a question list | ✅ |
| Structured brief another builder can **start investigating** | Builder brief includes **"Where to start"** (first 3 investigations + data to request from the owner) and **open questions with leads** | ✅ (added in v2) |
| Bonus: identify missing info | Gap report + "Open questions for the builder" | ✅ |
| Bonus: facts vs assumptions | Ledger `kind`: observed / inferred / hearsay / aspiration, each with its evidence quote | ✅ |
| Bonus: detect sensitive info | The Scribe flags spans in 6 categories (below) | ✅ |
| Bonus: help redact | Keep / generalise / remove asked in conversation, toggled on Review, enforced by code, leak-checked | ✅ |
| Bonus: versions per audience | For me / For builders / For everyone, all from one ledger | ✅ |
| Human approval before anything is shared | Review screen; export only after Approve | ✅ |
| Judge: usability / friction | One conversation; the owner never types the brief | ✅ |
| Judge: conversation experience | Human Indian voice (Sarvam), one question per turn, acknowledgements, read-back | ✅ |
| Judge: edge cases (ambiguity, missing info, interruptions, unexpected answers, not knowing enough) | Re-probe, `mark_unknown` + "who would know", barge-in via Pipecat VAD, parked topics, contradiction naming, off-topic redirect | ✅ |
| Judge: use-case innovation | Debrief method + claim ledger + three-version brief | ✅ |
| "Realistically use after the event" | Markdown + JSON export works today. A hosted link is **not** promised for the demo (see section 11) | ⚠️ partial — be upfront |

---

## 3. What makes it different from the many other submissions

Most teams will build *a questionnaire read aloud, then an LLM summary*. The five bonus points are usually built as five separate add-ons. In Birbal, **all five come out of one data structure**, the claim ledger:

| # | Differentiator | Bonus |
|---|---|---|
| 1 | **Claim ledger.** Every fact is stored as `{value, kind, evidence_quote, confidence, sensitivity}`. Each brief line links back to the speaker's exact words. | facts vs assumptions |
| 2 | **Gap-driven probing.** A deterministic controller scores the 9 dimensions and hands the Talker one focus per turn. | missing info; follow-ups |
| 3 | **Consent at the moment of disclosure.** *"You mentioned Kaveri Bank by name. Should that stay internal?"* | detect + redact |
| 4 | **Code-enforced redaction (the tearline idea).** Spans are replaced *before* lower versions are generated, then a leak check blocks any hit. | redact; versions |
| 5 | **Three audiences from one ledger.** | versions |
| 6 | **Read-back.** *"Here's what I heard. Correct me."* Unknowns become leads, not failures. | missing info; edge cases |
| 7 | **Talker + Scribe split.** This is the two-person debrief done by software. It also keeps voice latency low, because the Talker never waits on extraction. | conversation quality |

---

## 4. Interview method (this is the product)

### Dimension scoring (the controller uses it)
Each of the 9 dimensions scores 0, 1 or 2:
- `0` = nothing recorded.
- `1` = only `inferred`/`hearsay` claims, or only adjectives.
- `2` = an `observed` claim **plus** a concrete anchor: a number, a named role, or a specific incident.

`confidential` scores 2 when every flagged span has an owner choice. `success_test` scores 2 when the test is observable.

### Controller priority (each turn picks exactly one focus)
1. A pending consent question (a sensitive span flagged, with no choice yet).
2. An open contradiction.
3. `current_state` while it is below 2. Everything else builds on the incident.
4. The lowest-scoring remaining dimension, taken in brief order.
5. If every dimension is at 2, **or** after 8 minutes, **or** the owner says "that's all": move to read-back.

### Follow-up heuristics (in the Talker's system prompt)
- **Specific past over general future.** Turn "users usually…" into "Tell me about the last time that happened."
- **Numbers over adjectives.** Turn "a lot" into "Roughly how many last week?"
- **Saw vs concluded.** Turn "they don't trust the app" into "What did you see that makes you think that?"
- **Who would disagree?** "Who in your org would describe this differently?"
- **Unknowns.** If the owner says "I don't know", ask "Who would know?" Record a lead and move on. Never push twice.
- **One problem at a time.** Park the extras ("I've noted those") and go deep on the most painful one.
- **Contradictions.** Name them gently: "Earlier you said weekly, now daily. Which is closer?"
- **Off-topic.** Give one sentence of acknowledgement, then bridge back to the focus.
- **Style.** One question per turn, at most 25 words. Briefly acknowledge the answer. Never say dimension names. Mirror the owner's language: if they speak Hinglish, reply in Hinglish.

### Sensitive categories the Scribe flags
`person_name`, `org_or_partner_name`, `customer_data`, `business_metric` (revenue, conversion, counts), `internal_system`, `unreleased_plan_or_legal`.

### Sample interview (shows each heuristic firing)
```
T: Namaste, I'm Birbal. I help turn a problem into a brief a builder can act on. What's going wrong?
O: Merchants find our onboarding really confusing, a lot of them drop off.
   [scribe: who=merchants (inferred), impact="drop off" (inferred, adjective) → current_state 0]
T: Got it. Walk me through the last time a merchant got stuck. What happened, step by step?   ← incident recall
O: Yesterday a kirana owner called support... he'd uploaded PAN, then the bank verification with Kaveri Bank just spun.
   [scribe: current_state=observed; flag org_or_partner_name "Kaveri Bank"]
T: That's useful. You mentioned Kaveri Bank by name. Should that stay internal, or can a builder see it?   ← consent at disclosure
O: Keep it internal.
   [owner_choice=generalise → "a partner bank"]
T: Noted. How many merchants hit that verification step and don't finish, say, last week?   ← numbers over adjectives
O: Around 40 a day I think... actually our weekly report said 1,200.
   [scribe: contradiction 40/day×7=280 vs 1,200/week]
T: Earlier you said about 40 a day, and the weekly report says 1,200. Which one is closer?   ← contradiction
O: The report. 1,200. And that number is confidential.
   [frequency=observed(report); business_metric flagged, choice=generalise → "over a thousand a week"]
T: Understood, I'll keep it internal. What do merchants do today when it spins?   ← workaround
O: They call support, agents do manual verification. Also our app is slow in general, and the QR flow—
T: I've noted the app speed and the QR flow. Let's stay with verification for now. What's been tried to fix it?   ← park extras
O: I don't know, that was before I joined.
T: No problem. Who would know?   ← unknown → lead
O: Probably Ravi on the platform team.
   [unknown: attempted → lead "platform team lead" (person_name flagged)]
...
T: Here's what I heard: [read-back]. What did I get wrong?   ← read-back
```

---

## 5. Architecture (v2: cascade, so we get a human voice)

**Why the change from v1:** Gemini Live's native-audio models support **only the `AUDIO` response modality**. Their voice cannot be swapped for Sarvam or ElevenLabs. A human Indian voice needs a cascade: STT → LLM → TTS. The cascade also removes v1's biggest unverified risk, which was whether non-blocking tool responses steer the model's next question. In a cascade, every turn is a discrete LLM call with a prompt we control.

```
Browser ──WebRTC (Pipecat SmallWebRTCTransport, local P2P)──► Python Pipecat server
                                                              │
  mic ─► Silero VAD (barge-in) ─► STT (Deepgram Nova-3 multi) ─┤
                                                              ▼
                                   user turn text ──► TALKER (Gemini 3.8 Flash, short prompt)
                                         │                 ▲  reads: gap report + ledger summary + last 6 turns
                                         │                 │
                                         └──► SCRIBE (async, background) ──► LEDGER ──► CONTROLLER ──► gap report
                                              (LLM, JSON schema)            (JSON)     (deterministic)
                                                              │
  speaker ◄─ TTS (Sarvam bulbul:v3 for demo / Deepgram Aura for dev) ◄─ Talker text
                                                              │
  Board page ◄── polls GET /ledger every 1 s (FastAPI) ───────┘
  Review page ◄── POST /brief → canonical brief → redaction → leak check → 3 versions → Approve → export
```

### Per-turn flow
1. VAD detects end of speech, and STT emits the user's text.
2. **Talker** runs immediately. Its prompt is the static system prompt (persona + heuristics), plus the latest gap report, a ledger summary of at most 300 tokens, the last 6 turns, and the new utterance. The output is one question of at most 25 words, streamed to TTS.
3. **Scribe** runs in parallel on the same utterance, async. Output schema:
   `{claims[], sensitive[], contradictions[], unknowns[], parked_topics[], owner_choices[]}`. It is merged into the ledger.
4. **Controller** recomputes the scores and writes the next gap report.
5. The Scribe lags one turn behind, by design. The Talker still sees the raw new utterance, so a fresh consent or contradiction can be raised a turn late, never missed. If the Scribe flags something urgent, the gap report puts it first on the next turn.

### Gap report shape (what the Talker sees)
```json
{"focus": "frequency",
 "why": "only adjective 'a lot'; no number",
 "pending_consent": [{"span": "Kaveri Bank", "category": "org_or_partner_name"}],
 "contradictions": [],
 "parked": ["app speed", "QR flow"],
 "minutes_elapsed": 3.2,
 "ready_for_readback": false}
```

### Ledger entry
```json
{"id": "c7", "turn": 7, "dimension": "frequency",
 "value": "Over 1,000 merchants/week abandon at bank verification",
 "kind": "observed", "source": "weekly ops report (cited by owner)",
 "evidence_quote": "The report. 1,200.",
 "confidence": 0.8,
 "sensitivity": {"category": "business_metric", "span": "1,200",
                 "choice": "generalise", "generalisation": "over a thousand a week"}}
```

### Interruptions and edge cases in the cascade
- **Barge-in:** Pipecat's VAD plus interruption handling cancels TTS when the owner starts speaking. Test this in the first 90 minutes; it is part of the gate.
- **Latency:** expect about 1 s per turn, versus under a second on Gemini Live. In an interview, a short pause before a follow-up reads as listening. Keep the Talker prompt under about 1.5k tokens and stream TTS.
- **Silence over 8 s:** the Talker gives a gentle nudge ("Take your time, or we can skip this one").

### Voice choice (asked: Sarvam, ElevenLabs, Maya Research)
| Option | Verdict |
|---|---|
| **Sarvam `bulbul:v3`** (`SarvamTTSService`, WebSocket, ~250 ms first byte vendor-claimed) | **Demo voice.** Indian voices, native Hinglish/code-switching, 11 Indian languages, `pace` 0.5–2.0. Fits the room and the story. |
| **ElevenLabs Flash v2.5** | **Alternate.** Very natural, but the free tier is about 20k chars/month on Flash, needs attribution and is non-commercial. A one-line swap if Sarvam disappoints in testing. |
| **Maya Research Maya1** | **Not viable.** English-focused, needs a GPU with ≥16 GB VRAM, and has no hosted API. |
| Deepgram Aura | **Dev-loop voice only**, covered by the same signup credit. It protects the small Sarvam budget. |

### The 90-minute gate (solo safety rule)
Build day starts with the cascade spike: mic → STT → Talker → TTS → speaker, **with barge-in working**. **If it isn't working at 1:30, revert to v1** (Gemini Live `gemini-3.8-live`, native voice, tools + gap report, session resumption). The brain is transport-agnostic: prompts, ledger, controller and brief pipeline are plain Python/JSON. Only the transport changes. The voice stack must not eat the time needed for the ledger and the three-version brief, which are the actual pitch.

---

## 6. Free stack and budget

One interview is about 8 min and about 40 owner turns. That means about 80 LLM calls (Talker + Scribe), about 10 RPM, and about 2.5k characters of agent speech.

| Need | Choice | Free terms | Per-interview cost | Verify tonight |
|---|---|---|---|---|
| Orchestration | Pipecat (open source), `SmallWebRTCTransport` | Free | — | Pin version; `settings=` not `params=` (≥0.0.105) |
| STT | Deepgram Nova-3 multilingual (streaming) | $200 signup credit, no card, no expiry (official pricing page) | ~$0.07 | Hindi+English code-switch quality |
| STT fallback | Groq Whisper large-v3 (segment-based behind VAD) | Free tier | ₹0 | Key works |
| Talker LLM | Gemini 3.8 Flash | Free tier | ₹0 | **RPM/RPD at `aistudio.google.com/rate-limit`** |
| Scribe LLM | Gemini Flash (primary); Groq `openai/gpt-oss-120b` fallback | Free tier. Groq official: 30 RPM, 1K RPD, **8K TPM**, 200K TPD | ₹0 | 8K TPM ≈ 3 Scribe calls/min, so on Groq run the Scribe every 2nd turn |
| TTS demo | Sarvam `bulbul:v3` | ₹100 credits (docs; pricing page says ₹1,000) | ~₹7.5 → ~12–15 interviews | Actual credit on the dashboard |
| TTS dev | Deepgram Aura-2 | Same $200 (Deepgram says the credit covers Aura); $0.030/1k chars ≈ 6.7M chars | ~$0.08 | — |
| TTS alternate | ElevenLabs Flash v2.5 | 10k credits/month (~20k chars) | ~1/8 of the monthly quota | — |
| Hosting | Laptop | Free | — | — |

If LLM limits are tight, run the Scribe every second turn and put the Talker and Scribe on different providers.

**Honesty note for the pitch:** free-tier Gemini content may be used to improve Google's products. Say it up front: *"In production this runs on paid tiers where data isn't used for training. The redaction layer is what makes the output safe to share either way."*

---

## 7. The output: sample Birbal Brief, "For builders" version

```
───────────────────── BIRBAL BRIEF · FOR BUILDERS ─────────────────────
Problem: Small merchants abandon onboarding at the bank-account verification
step with a partner bank. Over a thousand a week fall back to manual support.

Who: Small retail merchants (kirana-type), self-onboarding on mobile.   [observed]
Today: Upload PAN → bank verification spins → merchant calls support →
       agent verifies manually.                                         [observed, incident 16 Oct]
Frequency: over a thousand a week (ops report).                        [observed, cited]
Why it matters: support load + lost activations.                       [inferred — no number yet]
Constraints: must use partner bank's verification API; RBI KYC norms.  [hearsay]
Already tried: unknown → lead: platform team lead.                     [open]
Success test: verification completes in-app for most merchants
              without a support call.                                   [aspiration — needs a target %]

Where to start
 1. Get verification API latency/error logs for the last 30 days.
 2. Shadow 5 support calls about stuck verification.
 3. Ask the platform team what was tried and why it stopped.
Data to request from the owner: funnel by step; API SLA; support ticket tags.

Open questions: target success rate? cost per manual verification?
Parked by owner: app speed; QR flow.
Redacted: 1 partner name (generalised), 1 metric (generalised), 1 person (role only).
──────────────────────────────────────────────────────────────────────────
```
**For me** (the owner version) has the same layout with real names, numbers and evidence quotes. **For everyone** (the public teaser) is 3 lines: problem, who, and what success looks like.

### Redaction pipeline
1. **Approved replacements:** the ledger holds approved spans and their replacements.
2. **Code redaction first:** replace spans in the canonical brief JSON using code, *before* any LLM sees text for the lower versions.
3. **LLM wording pass:** the LLM polishes wording for the audience, seeing only redacted text.
4. **Leak check:** case-insensitive substring match, with numbers normalised ("1,200" = "1200" = "1.2k"). A hit blocks the version and highlights it. **Known limit:** paraphrases ("about twelve hundred") are not caught. That's why step 2 happens first.

---

## 8. Solo build-day timeline (~7 h; re-cut when the 10 AM workbook lands)

**Tonight (prep; check the event rules on pre-written code):**
- [ ] Sign up and record the real numbers: Gemini key + `aistudio.google.com/rate-limit`, Deepgram (credit shown?), Sarvam (₹100 or ₹1,000?), Groq, ElevenLabs.
- [ ] In the Sarvam playground, pick a `bulbul:v3` voice and `pace` that sound like a calm interviewer.
- [ ] Clone `pipecat-examples` and confirm the p2p-webrtc example runs (if the rules allow).
- [ ] Write the Talker system prompt, the Scribe JSON schema and the 3 persona cards for testing (vague, chatty, secretive).
- [ ] Print 2 persona cards for judges (section 9).

| Time | Block | Done when |
|---|---|---|
| 0:00–1:30 | **Gate:** Pipecat example → Deepgram STT + Gemini Talker + Aura TTS; barge-in | You interrupt it and it stops talking. **If not → v1 Gemini Live** |
| 1:30–3:00 | Scribe + ledger + controller; `/ledger` endpoint; Board page (9 rows coloured by kind) | Rows fill and the focus changes as you talk |
| 3:00–3:45 | Prompt tuning on 3 personas | It probes, parks topics, asks consent, names contradictions |
| 3:45–4:45 | `/brief` + redaction + leak check + 3 versions | A planted secret is caught |
| 4:45–5:30 | Review page (Markdown + per-item toggles) + Approve → export; switch TTS to Sarvam | Approve → `.md` + `.json` download |
| 5:30–6:15 | Buffer / text-mode fallback / read-back polish | — |
| 6:15–7:00 | Rehearse the demo 3×; record a backup video | Under 4 min |

**Cut order:** public teaser, then text fallback, then anything cosmetic. **Never cut:** ledger kinds, consent at disclosure, leak check, read-back, the 90-minute gate.

---

## 9. Solo demo script (~4 min). The judge is the problem giver.

1. **Hook (30 s):** the Birbal stick story, then the "merchants find onboarding confusing" line, then Birbal + Birbal's Notes.
2. **You play a persona (60–90 s)** from a card, to hit the planted moments on cue:
   - the vague claim gets an incident probe, and the Board row turns from `inferred` to `observed`;
   - "Kaveri Bank" triggers the consent question and a lock chip appears;
   - 40/day vs 1,200/week gets named as a contradiction;
   - "I don't know" gets "Who would know?" and an open-question lead;
   - you interrupt mid-question to show barge-in.
3. **Hand the mic to a judge (2 min):** "Tell it a real problem you've seen." The brief says judges will test with unseen inputs, so this *is* the demo. Have 2 printed persona cards ready in case they want a prompt (one school, one clinic).
4. **Read-back + Birbal Brief (40 s):** show **For me** and **For builders** side by side. Type the hidden bank name into the For builders text by hand: **Secret found ✗** blocks export. Undo it: **Safe to share ✓**. (Switching an item to Share as is is the owner's own choice, so it does not trigger the check.)
5. **Close (10 s):** *"Builders shouldn't need five calls to understand a problem. They need one good debrief and a report they're allowed to read."*

Rehearse the handover. Mute your own mic when the judge speaks.

---

## 10. Judging criteria → what they'll see

| Criterion | Evidence in the demo |
|---|---|
| Usability / friction removed | One conversation produces a shareable brief; redaction happens inside the conversation, no form to fill |
| Conversation experience | Human Indian voice, Hinglish mirroring, incident follow-ups, read-back, barge-in |
| Edge cases | Judge's unseen problem, contradictions named, unknowns become leads, parked topics, silence nudge |
| Use-case innovation | Claim ledger with Dekha/Suna/Socha/Chahiye tags and evidence quotes, Birbal + Birbal's Notes debrief, code-enforced redaction |

---

## 11. Honest limits (say them before a judge finds them)

- **After-event use:** export works now. A hosted phone link isn't promised: WebRTC through venue NAT needs TURN. Deploy path: a Pipecat transport with managed rooms (e.g. Daily) on a small host.
- **Latency:** about 1 s per turn on the cascade.
- **Leak check:** catches exact and number-normalised matches, not paraphrases. Code redaction runs first for that reason.
- **Free tier:** Gemini free-tier data may be used by Google.
- **Credits:** Sarvam credit is small; rehearsals use Aura.

---

## Sources
- Gemini API pricing (free tier): https://ai.google.dev/gemini-api/docs/pricing
- Live API guide (native audio is AUDIO-only; models; async calls): https://ai.google.dev/gemini-api/docs/live-guide
- Live API session management: https://ai.google.dev/gemini-api/docs/live-session
- Pipecat supported services (Sarvam STT/TTS, ElevenLabs, Deepgram, Google, Groq): https://docs.pipecat.ai/api-reference/server/services/supported-services
- Pipecat Sarvam TTS: https://docs.pipecat.ai/api-reference/server/services/tts/sarvam
- Pipecat SmallWebRTCTransport: https://docs.pipecat.ai/server/services/transport/small-webrtc
- Sarvam pricing (₹100 new-user credit, bulbul v3 ₹30/10k chars): https://docs.sarvam.ai/api/pricing
- Sarvam TTS (latency, Hinglish): https://www.sarvam.ai/tts-v2
- ElevenLabs free tier (secondary): https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/
- Maya1 (secondary): https://www.centron.de/en/tutorial/maya1-tts-model-emotional-ai-voice-generation/
- Deepgram credit (secondary): https://agentdeals.dev/vendor/deepgram
- Groq free limits (secondary): https://eesel.ai/blog/groq-pricing
- Admiralty Code / source grading: NATO AJP-2.1 and STANAG 2511 (doctrine; cite by name)
- Cognitive Interview meta-analysis (Köhnken et al., 1999): https://www.academia.edu/16394117/The_cognitive_interview_A_meta_analysis
- Tearlines (DCID 1/7, ICD 209): https://irp.fas.org/offdocs/dcid1-7.html , https://fas.org/publication/tearlines
- Cookiy AI (judge context): https://www.research-live.com/article/news/insights-startup-cookiy-ai-secures-funding/id/5143643
