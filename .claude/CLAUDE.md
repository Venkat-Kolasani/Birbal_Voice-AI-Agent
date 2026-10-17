# Birbal — Claude Code instructions

@../AGENTS.md

The import above holds the project rules, requirements, constraints and build order. This file adds only the Claude Code specifics.

## Skills: when to invoke which

Invoke the skill **before** starting the matching work.

| When | Skill / agent |
|---|---|
| Any coding task (default mode for the whole build) | `ponytail:ponytail` |
| Before finishing a build step, to check for over-engineering | `ponytail:ponytail-review` |
| End of day, or before the demo: list every `# shortcut:` marker | `ponytail:ponytail-debt` |
| Writing Python modules (`brain/`, `bot.py`) | `ecc:python-patterns` |
| Writing tests (controller, leak check, redaction) | `ecc:python-testing` |
| FastAPI endpoints (`api.py`) | `ecc:fastapi-patterns` |
| Looking up Pipecat / Gemini / Deepgram / Sarvam APIs: never from memory | WebFetch the official docs (`docs.pipecat.ai`, `ai.google.dev`, `developers.deepgram.com`, `docs.sarvam.ai`). Use `ecc:documentation-lookup` / the `ecc:docs-lookup` agent only if Context7 MCP is connected |
| Leak check, number normalisation, sensitive-span matching | `ecc:regex-vs-llm-structured-text` |
| Talker / Scribe prompts | `ecc:prompt-optimizer` |
| Free-tier budgets, call counts, Scribe cadence | `ecc:cost-aware-llm-pipeline` |
| Turn latency, streaming, barge-in tuning | `ecc:latency-critical-systems` |
| Timeouts, fallbacks, never-crash-the-call | `ecc:error-handling` |
| Any bug or failing run | `ecc:build-fix` first; log it in `docs/ISSUES.md` |
| Writing a `docs/DECISIONS.md` entry | `ecc:architecture-decision-records` |
| End of each build step: prove it works | `ecc:verification-loop` |
| Keys, `.env`, export endpoint, redaction | `ecc:security-review`, then the `ecc:security-reviewer` agent |
| Review of a finished step | the `ecc:python-reviewer` and `ecc:silent-failure-hunter` agents |
| Designing the UI direction and tokens (`web/app.css`) | `ecc:frontend-design-direction`, then `impeccable:impeccable` |
| Polishing UI details (spacing, states, motion) | `ecc:make-interfaces-feel-better` |
| Accessibility pass on every page | `ecc:frontend-a11y` |
| Testing `index.html` / `board.html` / `review.html` in a browser | `ecc:browser-qa` |
| Recording the backup demo video | `ecc:ui-demo` |
| Context getting long or switching sessions | `ecc:save-session` / `ecc:resume-session` |

If a skill conflicts with `AGENTS.md`, `AGENTS.md` wins. Ponytail's "smallest complete change" never overrides the never-cut list in AGENTS.md §3, or the security and approval constraints in §1.

## Working rules for Claude

- **Logs first.** After each build step, append to `docs/IMPLEMENTATION_LOG.md`. When an error appears, add it to `docs/ISSUES.md` right away, with the exact error text. Do not batch log entries until the end.
- **Gate check.** 90 minutes after step 1 starts (keys in step 0 don't count), stop and report pass/fail to the user. If it failed, propose Plan B and log the decision.
- **Verify, don't assume.** Look up model IDs, Pipecat class names and free-tier limits in docs, or test them with a real call. Record real limits in `docs/DECISIONS.md`.
- **Use the advisor** before committing to an approach on each build step, and before declaring the build done.
- **Subagents** only for independent research or review. Don't spawn subagents for small edits.
- **Commits:** suggest one after each completed step; commit only when the user says so.
- **Secrets:** never print `.env` contents, and never paste keys into logs or docs.
