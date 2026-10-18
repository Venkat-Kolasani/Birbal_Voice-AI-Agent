"""Deterministic interview controller: merges Scribe output into the ledger and picks the next focus."""
from .schema import DIMENSIONS, GapReport, Ledger, ScribeOutput

READBACK_AFTER_MIN = 8.0


def merge(ledger: Ledger, out: ScribeOutput, turn: int) -> Ledger:
    """Fold one Scribe result into the ledger (mutates and returns it)."""
    for c in out.claims:
        c.turn = turn  # always ours; never trust an LLM-supplied turn/id
        c.id = f"c{len(ledger.claims) + 1}"
        ledger.claims.append(c)
    known = {s.span.lower() for s in ledger.sensitive}
    for s in out.sensitive:
        if s.span.lower() not in known:
            s.turn = turn
            ledger.sensitive.append(s)
            known.add(s.span.lower())
    for ch in out.owner_choices:
        for s in ledger.sensitive:
            if s.span.lower() == ch.span.lower():
                s.choice, s.decided_turn = ch.choice, turn
    ledger.contradictions.extend(out.contradictions)
    for dim in out.resolved_contradictions:
        for c in ledger.contradictions:
            if c.dimension == dim:
                c.resolved = True
    ledger.unknowns.extend(out.unknowns)
    ledger.parked.extend(p for p in out.parked_topics if p not in ledger.parked)
    ledger.owner_done = ledger.owner_done or out.owner_done
    return ledger


def score(ledger: Ledger, dim: str) -> int:
    """0 = nothing, 1 = only guesses/hearsay/adjectives, 2 = observed + anchored."""
    if dim == "confidential":
        if not ledger.sensitive:
            # Nothing flagged yet: counts as clear only once the rest of the picture exists.
            return 2 if score(ledger, "current_state") == 2 else 0
        return 2 if all(s.choice for s in ledger.sensitive) else 1
    claims = [c for c in ledger.claims if c.dimension == dim]
    if not claims:
        # An unknown with a lead is an answer too: we know who to ask.
        return 1 if any(u.dimension == dim for u in ledger.unknowns) else 0
    if dim == "success_test":
        return 2 if any(c.anchored for c in claims) else 1
    if dim == "constraints" and any("none known" in c.value.lower() for c in claims):
        return 2
    return 2 if any(c.kind == "observed" and c.anchored for c in claims) else 1


def _settled(ledger: Ledger, dim: str) -> bool:
    """A dimension is settled when clear, or when the owner doesn't know and gave a lead."""
    return score(ledger, dim) == 2 or any(u.dimension == dim for u in ledger.unknowns)


def gap_report(ledger: Ledger, minutes_elapsed: float) -> GapReport:
    scores = {d: score(ledger, d) for d in DIMENSIONS}
    pending = [s for s in ledger.sensitive if s.choice is None]
    open_contra = [c for c in ledger.contradictions if not c.resolved]
    common = dict(pending_consent=pending, contradictions=open_contra, parked=ledger.parked,
                  scores=scores, minutes_elapsed=round(minutes_elapsed, 1))

    if pending:
        s = pending[0]
        return GapReport(focus="consent", why=f'"{s.span}" was mentioned; checking if builders may see it', **common)
    if open_contra:
        c = open_contra[0]
        return GapReport(focus="contradiction", why=f'"{c.a}" vs "{c.b}"', **common)
    if ledger.owner_done or minutes_elapsed >= READBACK_AFTER_MIN or all(_settled(ledger, d) for d in DIMENSIONS):
        return GapReport(focus="readback", why="coverage complete or time up", ready_for_readback=True, **common)
    if scores["current_state"] < 2:
        return GapReport(focus="current_state", why="need one concrete recent incident, step by step", **common)
    # First unsettled dimension in brief order: deepen a vague answer right away, then move on.
    for d in DIMENSIONS:
        if not _settled(ledger, d):
            why = "nothing recorded yet" if scores[d] == 0 else \
                "only a guess or an adjective so far; needs something they saw, or a number"
            return GapReport(focus=d, why=why, **common)
    return GapReport(focus="readback", why="coverage complete", ready_for_readback=True, **common)
