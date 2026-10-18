"""Interview-quality eval: an LLM plays a problem owner from a persona card; Birbal interviews in text mode.

Run (needs keys):  uv run python server/simulate.py [persona ...] [--turns 12]
Prints a scorecard per persona. Use it to tune prompts: change one thing, re-run, compare.
Budget: ~3 LLM calls per turn (owner, Talker, Scribe) -> 12 turns x 3 personas ~ 110 calls.
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brain import llm  # noqa: E402
from brain.controller import score  # noqa: E402
from brain.prompts import OPENING_LINE, TALKER_SYSTEM, talker_messages  # noqa: E402
from brain.schema import DIMENSIONS  # noqa: E402
from brain.session import Session  # noqa: E402

PERSONAS = json.loads((Path(__file__).parent / "fixtures" / "personas.json").read_text())

OWNER_SYSTEM = """You are role-playing a problem owner being interviewed. Stay in character. Answer only what you are asked, in 1-3 spoken sentences, the way a busy person talks (not a written essay). Use your persona's style. Never volunteer the whole story at once. If the interviewer reads back a summary that is correct, say it's right and that's everything.
Persona:
"""


def quality(question: str) -> dict:
    words = len(question.split())
    return {"long": words > 30, "double": question.count("?") > 1,
            "why_first": bool(re.search(r"(^|[.!]\s+)why\b", question, re.I)),
            "empty_ack": bool(re.match(r"\s*(got it|great|okay|ok|sure|understood)[.!,]", question, re.I))}


async def run(name: str, turns: int) -> dict:
    p = PERSONAS[name]
    s = Session()
    s.start("text")
    s.add_birbal(OPENING_LINE)
    flags = {"long": 0, "double": 0, "why_first": 0, "empty_ack": 0}
    first_full = None
    for i in range(turns):
        owner_view = [{"role": "user" if t.role == "birbal" else "assistant", "content": t.text} for t in s.ledger.transcript]
        said = await llm.complete_text(OWNER_SYSTEM + p["card"], owner_view)
        if not said:
            print(f"  [{name}] owner model failed at turn {i + 1}")
            break
        s.add_owner(said)
        await s.settle()  # sim only: let the Scribe finish so scores are deterministic per turn
        reply = await llm.complete_text(TALKER_SYSTEM, talker_messages(s.ledger.transcript, s.note()))
        if not reply:
            print(f"  [{name}] Talker failed at turn {i + 1}")
            break
        s.add_birbal(reply)
        for k, v in quality(reply).items():
            flags[k] += v
        clear = sum(score(s.ledger, d) == 2 for d in DIMENSIONS)
        if first_full is None and clear >= 8:
            first_full = i + 1
        print(f"  [{name}] {i + 1:>2} OWNER: {said}\n        BIRBAL: {reply}   ({clear}/9, focus={s.gap().focus})")
        if s.ledger.owner_done:
            break
    s.finish()
    v = await s.brief()
    planted = p.get("secrets", [])
    caught = [x for x in planted if any(x.lower() in z.span.lower() or z.span.lower() in x.lower() for z in s.ledger.sensitive)]
    kinds = {k: sum(c.kind == k for c in s.ledger.claims) for k in ("observed", "hearsay", "inferred", "aspiration")}
    return {"persona": name, "turns": len(s.ledger.transcript) // 2,
            "clear": sum(score(s.ledger, d) == 2 for d in DIMENSIONS), "turns_to_8": first_full,
            "secrets_caught": f"{len(caught)}/{len(planted)}", "builder_safe": v["builders"].safe,
            "claims": len(s.ledger.claims), "contradictions": len(s.ledger.contradictions),
            "dekha/suna/socha/chahiye": "/".join(str(kinds[k]) for k in ("observed", "hearsay", "inferred", "aspiration")),
            **flags}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("personas", nargs="*", default=list(PERSONAS))
    ap.add_argument("--turns", type=int, default=12)
    a = ap.parse_args()
    if not llm.available():
        raise SystemExit("Add GOOGLE_API_KEY and/or GROQ_API_KEY to .env first.")
    rows = []
    for name in a.personas:
        print(f"\n=== {name} ===")
        rows.append(await run(name, a.turns))
    print("\nSCORECARD (lower is better for long/double/why_first/empty_ack; "
          "if socha+suna are near 0 on 'vague', the Scribe is over-tagging Dekha)")
    keys = list(rows[0])
    print(" | ".join(keys))
    for r in rows:
        print(" | ".join(str(r[k]) for k in keys))


if __name__ == "__main__":
    asyncio.run(main())
