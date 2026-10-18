"""Benchmark: how well does the Scribe grade claims as Dekha / Suna / Socha / Chahiye?

Run (needs an LLM key):  uv run python server/bench_kinds.py [--provider groq|gemini|alt]
~28 LLM calls. Prints accuracy and a confusion table. Labelled set: server/fixtures/kind_bench.json.
"""
import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ap = argparse.ArgumentParser()
ap.add_argument("--provider", default=None)
ap.add_argument("--batch", type=int, default=4)
ap.add_argument("--pause", type=float, default=2.0)
args = ap.parse_args()
if args.provider:
    os.environ["SCRIBE_PROVIDER"] = args.provider

from brain import scribe  # noqa: E402
from brain.schema import Ledger  # noqa: E402

KINDS = ["observed", "hearsay", "inferred", "aspiration"]
LABEL = {"observed": "Dekha", "hearsay": "Suna", "inferred": "Socha", "aspiration": "Chahiye"}


async def grade(item):
    out = await scribe.run(Ledger(), "What's going wrong?", item["said"])
    if not out.claims:
        return None
    # The grade of the main claim: the most common kind among claims, ties -> first claim's kind
    counts = Counter(c.kind for c in out.claims)
    top = max(counts.values())
    return next(c.kind for c in out.claims if counts[c.kind] == top)


async def main():
    items = json.loads((Path(__file__).parent / "fixtures" / "kind_bench.json").read_text())
    results = []
    for i in range(0, len(items), args.batch):  # small batches: stay under per-minute limits (Groq: 8K TPM -> --batch 2 --pause 20)
        results += await asyncio.gather(*(grade(x) for x in items[i:i + args.batch]))
        await asyncio.sleep(args.pause)
    conf = Counter()
    ok = 0
    for item, got in zip(items, results):
        conf[(item["kind"], got or "none")] += 1
        ok += got == item["kind"]
        if got != item["kind"]:
            print(f"  MISS expected {LABEL[item['kind']]:<8} got {LABEL.get(got, 'none'):<8} | {item['said']}")
    n = len(items)
    print(f"\nScribe grade accuracy: {ok}/{n} = {100 * ok / n:.0f}%  (provider={os.getenv('SCRIBE_PROVIDER', 'default')})")
    print("\nconfusion (rows = expected, cols = got)")
    print(f"{'':10}" + "".join(f"{LABEL[k]:>9}" for k in KINDS) + f"{'none':>9}")
    for e in KINDS:
        print(f"{LABEL[e]:10}" + "".join(f"{conf[(e, g)]:>9}" for g in KINDS) + f"{conf[(e, 'none')]:>9}")
    per = {e: (sum(conf[(e, e)] for _ in [0]), sum(v for (x, _), v in conf.items() if x == e)) for e in KINDS}
    print("\nper kind: " + "  ".join(f"{LABEL[e]} {c}/{t}" for e, (c, t) in per.items()))


if __name__ == "__main__":
    asyncio.run(main())
