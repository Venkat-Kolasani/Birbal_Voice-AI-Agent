# Birbal: architecture and system design

*"Akbar had Birbal. Now every builder does."*

Birbal interviews a problem owner by voice or text. It grades every claim as it goes (Dekha, Suna, Socha or Chahiye), asks for consent the moment something private is said, and writes a brief that has been redacted by code into three versions. Nothing is shared until the owner approves.

---

## 1. System overview

```mermaid
flowchart LR
    subgraph Browser["Browser (plain HTML + JS)"]
        UI1["index.html<br/>Start · Live split view"]
        UI2["review.html<br/>Brief · Redaction · Approve"]
        UI3["/b/token<br/>Read-only shared brief"]
        VJS["voice.js<br/>WebRTC client"]
    end

    subgraph Server["Python server (FastAPI + Pipecat, one process)"]
        API["api.py<br/>REST + WebRTC offer"]
        BOT["bot.py<br/>Voice pipeline"]
        subgraph Brain["brain/ (transport-agnostic)"]
            SES["session.py<br/>Session + Store"]
            CTL["controller.py<br/>Scoring + next focus"]
            SCR["scribe.py<br/>Birbal's Notes"]
            BRF["brief.py<br/>Redaction + leak check"]
            PRM["prompts.py"]
            LLM["llm.py + keys.py<br/>Failover"]
        end
        DISK[("data/sessions/*.json")]
    end

    subgraph Providers["External AI services"]
        DG["Deepgram<br/>STT nova-3 multi · TTS Aura"]
        SV["Sarvam<br/>STT saaras · TTS bulbul:v3"]
        GM["Google Gemini<br/>Talker + Scribe"]
        GQ["Groq<br/>Failover LLM"]
    end

    UI1 -- "poll /api/state" --> API
    UI2 -- "/api/brief, /api/approve" --> API
    UI3 -- "/api/shared/token" --> API
    VJS <-->|"audio (WebRTC)"| BOT
    API --> SES
    BOT --> SES
    SES --> CTL & SCR & BRF
    SCR --> LLM
    BOT --> DG & SV & GM
    LLM --> GM & GQ
    SES <--> DISK
```

---

## 2. One voice turn (the hot path)

```mermaid
flowchart TD
    A["Owner speaks"] --> B["Silero VAD + smart-turn<br/>(end of sentence?)"]
    B --> C["STT: Deepgram multi / Sarvam codemix"]
    C -- "interim words" --> T["TranscriptTap → UI 'You · live' line"]
    C -- "final turn" --> D["User aggregator"]
    D -- "on_user_turn_stopped" --> S["session.add_owner()"]
    S -.->|"background task, never awaited"| SC["Scribe LLM<br/>claims · kinds · secrets · contradictions"]
    SC -.-> L["Merge into the claim ledger"]
    L -.-> K["Controller recomputes the gap report"]
    D --> N["ControllerNote<br/>attach [controller] note to last user message"]
    K -.->|"used on the next turn"| N
    N --> E["Talker LLM (Gemini; Groq failover)<br/>one question ≤ 25 words, echoes one detail"]
    E --> F["TTS: Sarvam bulbul:v3 / Aura / ElevenLabs"]
    F --> G["Owner hears Birbal<br/>(barge-in after 2 words)"]
    E -- "on_assistant_turn_stopped" --> H["session.add_birbal()"]
```

**Why the Talker never waits for the Scribe:** the Scribe is off the hot path and lags one turn. The Talker always sees the raw latest answer, plus the controller note built from everything up to the previous turn. Latency equals STT + one LLM call + TTS, never two LLM calls.

---

## 3. One turn as a sequence

```mermaid
sequenceDiagram
    autonumber
    participant O as Owner
    participant P as Pipecat (VAD/STT)
    participant S as Session
    participant SC as Scribe (async)
    participant C as Controller
    participant T as Talker LLM
    participant V as TTS
    O->>P: speech
    P-->>S: interim text (live line in UI)
    P->>S: final turn → add_owner()
    S-)SC: run in background
    S->>C: gap report (ledger as of last turn)
    C->>T: transcript + [controller] FOCUS / CONSENT / CONTRADICTION / READBACK
    T->>V: one short question
    V->>O: Birbal speaks
    SC--)S: claims, secrets, contradictions → merge → ledger
```

---

## 4. Controller: how Birbal picks the next question

```mermaid
flowchart TD
    Start(["After every owner turn"]) --> Q1{"Private item<br/>without a choice?"}
    Q1 -- yes --> R1["CONSENT: 'Fine for builders to see, or keep it internal?'"]
    Q1 -- no --> Q2{"Open contradiction?"}
    Q2 -- yes --> R2["CONTRADICTION: 'Earlier X, now Y. Which is closer?'"]
    Q2 -- no --> Q3{"All 9 settled, or 8 min,<br/>or owner says done?"}
    Q3 -- yes --> R3["READBACK: one fact per sentence, 'What did I get wrong?'"]
    Q3 -- no --> Q4{"Current state<br/>has a real incident?"}
    Q4 -- no --> R4["FOCUS current_state: 'Walk me through the last time…'"]
    Q4 -- yes --> R5["FOCUS = first unsettled dimension in brief order<br/>(with example question shapes)"]
```

**Scoring per dimension:** `0` = nothing; `1` = only Socha/Suna or adjectives; `2` = Dekha (observed) plus an anchor (a number, a role or an incident). An "I don't know" with a lead ("ask the platform team") counts as settled.

**The 9 dimensions:** current state · who · workaround · impact · frequency · constraints · already tried · confidential · success test.

---

## 5. Redaction pipeline (code first, AI second)

```mermaid
flowchart LR
    L[("Claim ledger<br/>+ private items + owner choices")] --> C["canonical brief (code)"]
    C --> M["For me<br/>everything + quotes + consent log"]
    C --> R["redact() (code)<br/>Share as is / Hide name / Remove<br/>pending = hidden (fail closed)"]
    R --> W["LLM wording pass<br/>sees ONLY redacted text"]
    W --> B["For builders"]
    W --> E["For everyone (3-line teaser)"]
    B & E --> LC{"Leak check (code)<br/>substring · distinctive tokens ·<br/>numbers 1,200 = 1200 = 1.2k · lakh/crore"}
    LC -- "secret found" --> X["Approve blocked (server-side 409)"]
    LC -- "safe" --> A["Approve → export .md/.json<br/>+ share link /b/token"]
```

Known limit, stated openly: a paraphrase ("about twelve hundred") isn't caught by the leak check. That's why redaction runs **before** any AI ever sees text meant for builders.

---

## 6. Reliability and failover

```mermaid
flowchart TD
    subgraph Text["Typed turn / Scribe / brief extras"]
        T1["Preferred provider<br/>(Talker: Gemini · Scribe: Gemini)"] --> T2["Each key in pool<br/>GOOGLE_API_KEYS=k1,k2"]
        T2 -- "429 / quota → rest key 60 s" --> T3["Next key"]
        T3 -- "all keys failed" --> T4["Next provider (Groq pool)"]
        T4 -- "all failed" --> T5["Clear error; owner retries;<br/>failed turn retracted (no duplicates)"]
    end
    subgraph Voice["Voice interview"]
        V1["Start: pick healthy provider + key"] --> V2["Pipeline running"]
        V2 -- "fatal error, or 2 errors in 10 s" --> V3["status = error"]
        V3 --> V4["UI auto-switches to typing<br/>same session, nothing lost"]
        V2 -- "page refresh / tab closed" --> V5["Disconnect ≠ end;<br/>resume by typing"]
    end
    subgraph Data["Data safety"]
        D1["Autosave every 5 s (dirty sessions)"] --> D2["Atomic write: tmp → rename"]
        D3["Server restart"] --> D4["Session restored from disk"]
    end
    subgraph Fallback["Last-resort demo"]
        F1["/start?demo=1 → replay fixture<br/>drives the real UI, no keys needed"]
    end
```

---

## 7. Data model

```mermaid
classDiagram
    class Session {
        id
        mode: text|voice|demo
        lang: auto|en|hi|kn
        status
        approved
        share_token
        overrides
        extras
    }
    class Ledger {
        claims[]
        sensitive[]
        contradictions[]
        unknowns[]
        parked[]
        transcript[]
    }
    class Claim {
        dimension
        value
        kind: observed|hearsay|inferred|aspiration
        evidence_quote
        anchored
        turn
    }
    class Sensitive {
        span
        category
        generalisation
        choice: keep|generalise|remove|null
        decided_turn
    }
    class Brief {
        audience: me|builders|everyone
        problem
        lines[]
        where_to_start[]
        data_to_request[]
        open_questions[]
        parked[]
        redaction_summary
    }
    Session "1" --> "1" Ledger
    Ledger "1" --> "*" Claim
    Ledger "1" --> "*" Sensitive
    Session ..> Brief : versions()
```

Every bonus point comes from one structure, the ledger:
- **Missing info:** unscored dimensions plus unknowns.
- **Facts vs assumptions:** `kind`.
- **Sensitive info:** `sensitive[]`.
- **Help redact:** `choice`.
- **Per-audience versions:** `versions()`.

---

## 8. API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | readiness (AI, voice, key counts, TTS) |
| GET | `/api/sessions` | recent briefs (redacted titles) |
| POST | `/api/start?mode=text\|voice\|demo&lang=auto\|en\|hi\|kn` | new interview → `id` |
| GET | `/api/state?s=` | live state for the UI (rows, focus, why, interim, private, open, parked) |
| POST | `/api/turn?s=` | typed answer → Birbal's reply |
| POST | `/api/mode?s=&mode=text` | switch voice → typing mid-interview |
| POST | `/api/end?s=` | finish, wait for the Scribe, save |
| GET | `/api/brief?s=` | three versions + leaks + private items + share link |
| POST | `/api/choice?s=` | Share as is / Hide name / Remove (revokes the share link) |
| POST | `/api/edit?s=` | hand-edit the problem statement (leak-checked) |
| POST | `/api/approve?s=` | server-side leak gate → export + share token |
| GET | `/api/export/{audience}.{md\|json}?s=` | download (shareable versions only after approval) |
| GET | `/api/shared/{token}` · `/b/{token}` | read-only builder + public versions |
| POST/PATCH | `/api/offer` | WebRTC offer / ICE for voice (`request_data.session`) |

---

## 9. Design decisions at a glance

| Choice | Why |
|---|---|
| Cascade (STT → LLM → TTS) instead of an all-in-one voice model | a human Indian voice (Sarvam) needs a swappable TTS; every turn's prompt is under our control |
| Talker + Scribe split | low latency (one LLM call on the hot path) plus deep extraction in the background, like an interviewer and a note-taker |
| Deterministic controller | the interview adapts to unseen problems without a fixed question list; testable |
| Redaction in code before AI | confidentiality doesn't depend on asking an AI nicely; enforced server-side |
| Smart-turn + 0.4 s VAD + 2-word barge-in | patient listening without long pauses; noise doesn't interrupt |
| Key pools + provider failover + degrade to typing | the demo never dies on a rate limit or a mic failure |
| Sessions on disk, atomic writes, autosave | several judges, restarts and refreshes are all safe |
| Plain HTML/JS, one CSS token file | enterprise look with zero build step; light theme for projectors |
| ₹0 stack | Gemini / Groq free tiers, Deepgram $200 credit, Sarvam credit, open-source Pipecat |

---

## 10. Deployment

| Setting | How |
|---|---|
| Event demo | laptop: `uv run uvicorn api:app --app-dir server --port 8000` |
| Phone / other laptop | `./scripts/serve_lan.sh` (HTTPS on the LAN IP, self-signed certificate), over a phone hotspot |
| Public, typed only | any long-running Python host + persistent disk (`BIRBAL_DATA`) |
| Public, voice | needs TURN: Pipecat `DailyTransport` (Daily free tier), Pipecat Cloud, or SmallWebRTC + coturn |
| Production must-dos | owner auth, paid AI tiers (free tiers may use data for training), HTTPS, per-session secrets |

**Languages:** Auto (follows Hinglish), English, हिंदी, ಕನ್ನಡ. The interview runs in that language; **the brief is always in English.** Hindi and Kannada voice use Sarvam; Kannada speech recognition uses Sarvam.
