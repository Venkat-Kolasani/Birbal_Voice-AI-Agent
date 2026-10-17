# Birbal UI design

**Direction:** quiet confidence. It should feel like Linear, Stripe Dashboard or Vercel, not like an AI demo. The live notes are the hero; everything else stays out of the way.

## Principles
1. **Show the thinking, not the AI.** No chat bubbles with robot avatars. Judges watch Birbal's Notes fill and grade claims live, which is the proof that it understands.
2. **One primary action per screen:** Start interview, then End & review, then Approve.
3. **Traceable by default.** Every line in the brief can be clicked to show the exact quote and the moment it was said. That is the enterprise "audit trail" signal.
4. **Privacy is visible.** Private items are always listed, with their state and who chose it.
5. **Calm motion.** 150 ms fades and slides only; honour `prefers-reduced-motion`.

## Design tokens (`web/app.css`, `:root` + dark theme)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | #FAFAF9 | #0C0C0D | page |
| `--surface` | #FFFFFF | #151517 | panels |
| `--border` | #E7E5E4 | #26262A | 1 px hairlines |
| `--text` | #1C1917 | #EDEDED | body |
| `--muted` | #78716C | #8B8B93 | labels, meta |
| `--accent` | #0F766E (peacock teal) | #2DD4BF | primary button, focus ring, "asking now" |
| `--seen` | #15803D | #4ADE80 | Dekha · Seen chip |
| `--heard` | #0369A1 | #38BDF8 | Suna · Heard chip |
| `--guessed` | #7C3AED | #A78BFA | Socha · Guessed chip |
| `--wished` | #57534E | #A8A29E | Chahiye · Wished chip (outline) |
| `--private` | #B45309 | #FBBF24 | lock chip, private items |
| `--ok` / `--danger` | #15803D / #B91C1C | #4ADE80 / #F87171 | Safe to share ✓ / Secret found ✗ |

The accent is a peacock teal: a quiet India nod, and not the indigo every SaaS uses.

**Chips:** each is a 10% tint of its colour, with text in the full colour.

**Type:**
- **Inter** for the UI, with `font-variant-numeric: tabular-nums` for counts and timers.
- **Source Serif 4** for the Brief body only, so the output reads like an official record.
- **Scale:** 12 / 14 / 16 / 20 / 28.

**Layout and icons:**
- **Spacing:** 4/8 px grid.
- **Radius:** 8 px for panels, 6 px for controls.
- **Shadows:** none, except the popover.
- **Icons:** Lucide SVG inline, 16 px, stroke 1.5. No emoji.

## Screen 1: Start (`index.html`, idle)
```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ Birbal                                              ◐ theme   Help │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│     Tell Birbal about a problem.                                     │
│     It asks the right questions and writes a brief builders          │
│     can act on. You approve before anything is shared.               │
│                                                                      │
│     [ ● Start interview ]        Language  Auto · English · हिंदी     │
│                                                                      │
│     ⌂ Nothing leaves this device until you approve.                  │
│     ~8 minutes · You can stop anytime                                │
└──────────────────────────────────────────────────────────────────────┘
```

## Screen 2: Live interview (`index.html`, active): the demo hero
```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ Birbal   Interview · 03:12        ● Live   [M] Mute  [ End & review ]│
├────────────────────────────────┬─────────────────────────────────────┤
│                                │ BIRBAL'S NOTES          6 of 9 clear │
│        ╭─────────╮             │ ▰▰▰▰▰▰▱▱▱                            │
│        │  ◉ ring │ Listening   │                                      │
│        ╰─────────╯ ▁▂▅▇▅▂▁     │ ● Current state         [Dekha·Seen] │
│                                │   Verification spins after PAN upload│
│ BIRBAL                         │ ● Who                 [Socha·Guessed]│
│ Walk me through the last time  │   Small retail merchants             │
│ a merchant got stuck.          │ ◐ Frequency               asking now │
│                                │   "a lot" — needs a number           │
│ YOU                            │ ○ Workaround                         │
│ Yesterday a kirana owner       │ ○ Constraints                        │
│ called support…                │ ○ Already tried                      │
│                                │ ○ Success test                       │
│                                ├─────────────────────────────────────┤
│                                │ PRIVATE   ⌂ Kaveri Bank  → Hidden    │
│                                │ OPEN      Who tried before? → platform│
│                                │ PARKED    App speed · QR flow        │
└────────────────────────────────┴─────────────────────────────────────┘
```

**Orb states:**
- **Listening:** the accent ring breathes slowly, with a live level meter.
- **Thinking:** a soft shimmer, shown for ≤1 s.
- **Speaking:** a waveform in muted text colour.

The status text sits next to the orb and is announced through `aria-live`.

**Notes rows:**
- **Status markers:** `○` empty, `◐` partial (score 1), `●` clear (score 2).
- **Current focus:** the row Birbal is asking about gets an accent left border and an "asking now" label.
- **Upgrades:** when a claim upgrades (Socha → Dekha), the chip cross-fades. That is the moment judges notice.

**Consent moment:** when a private item is detected, a quiet amber row slides into PRIVATE with a "pending" state. The owner's spoken answer resolves it.

**Transcript:** only the last ~6 turns, with older turns fading out. The full transcript lives in For me.

## Screen 3: Review (`review.html`)
```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ Birbal   Review brief                 [ Download ▾ ]  [ Approve ▸ ]│
├──────────────────┬───────────────────────────────────────────────────┤
│ VERSION          │  Birbal Brief · For builders     ✓ Safe to share   │
│ ○ For me         │  ───────────────────────────────────────────────── │
│ ● For builders   │  Problem                                           │
│ ○ For everyone   │  Small merchants abandon onboarding at the bank-   │
│                  │  account verification step with a partner bank.    │
│ PRIVATE ITEMS (3)│                                                    │
│ Kaveri Bank      │  Who          Small retail merchants  [Dekha·Seen] │
│ [Share|Hide|Remove]│ Frequency   Over a thousand a week  [Dekha·Seen] ❝│
│ 1,200 / week     │  Impact       Support load            [Socha]      │
│ [Share|Hide|Remove]│                                                  │
│ Ravi (person)    │  Where to start                                    │
│ [Share|Hide|Remove]│ 1. Verification API error logs, last 30 days     │
│                  │  2. Shadow 5 support calls                         │
│ COVERAGE  7 / 9  │  3. Ask the platform team what was tried           │
│ OPEN QUESTIONS 2 │  Open questions · Parked · Redaction summary       │
└──────────────────┴───────────────────────────────────────────────────┘
   ❝ click → popover: "The report. 1,200."  · turn 7 · 03:41
```

**Approve:**
- Opens a confirm sheet: "Share For builders and For everyone? 3 private items are hidden or removed."
- The Approve button is disabled while any version shows **Secret found ✗**. In that case the offending line is highlighted in red with "Contains a private item".

**Download:** Markdown, JSON, or copy to clipboard.

## Enterprise signals (cheap, high impact)
- **Audit trail:** quote, turn number and timestamp on every brief line.
- **Consent log:** in For me, each private item shows its choice and when it was made.
- **Keyboard:** `M` mute, `E` end & review, `1/2/3` switch version, `⌘↵` approve.
- **States:** skeleton rows while the brief generates (no spinner). Plain-language empty and error states, e.g. "Mic blocked. Allow microphone in your browser to continue."
- **Accessibility:** WCAG AA contrast in both themes, visible focus rings, full keyboard use, `aria-live` for status and transcript.
- **Responsive:** split view at ≥1024 px; below that, a stacked layout with a Notes / Conversation tab switch.
- **No layout shift** as rows arrive (fixed row heights).

## Not doing
Landing page, login, settings, charts, avatars, mascot art, animations over 200 ms.
