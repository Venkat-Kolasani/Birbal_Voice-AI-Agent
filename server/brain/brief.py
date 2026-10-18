"""Birbal Brief: canonical brief from the ledger, code-enforced redaction, leak check, three versions."""
import re
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from .controller import score
from .schema import DIMENSION_LABELS, DIMENSIONS, KIND_LABELS, Claim, Ledger, Sensitive

Audience = Literal["me", "builders", "everyone"]

DEFAULT_GENERALISATION = {
    "person_name": "a team member",
    "org_or_partner_name": "a partner organisation",
    "customer_data": "[customer detail withheld]",
    "business_metric": "[figure withheld]",
    "internal_system": "an internal system",
    "unreleased_plan_or_legal": "[confidential plan]",
}
# Words too generic to count as a leak on their own ("Kaveri Bank" leaks via "Kaveri", not "Bank").
GENERIC = {"bank", "the", "team", "ltd", "limited", "pvt", "inc", "india", "on", "of", "and", "platform",
           "report", "weekly", "daily", "per", "week", "day", "a", "an"}


class BriefLine(BaseModel):
    dimension: str
    label: str
    text: str
    kind: str = ""
    kind_label: str = ""
    evidence_quote: str = ""
    turn: int = 0
    t: float = 0.0


class OpenQuestion(BaseModel):
    question: str
    lead: str = ""


class Brief(BaseModel):
    audience: Audience = "me"
    problem: str = ""
    lines: list[BriefLine] = Field(default_factory=list)
    where_to_start: list[str] = Field(default_factory=list)
    data_to_request: list[str] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    parked: list[str] = Field(default_factory=list)
    redaction_summary: str = ""
    coverage: int = 0


class Leak(BaseModel):
    span: str
    where: str
    snippet: str


class Version(BaseModel):
    brief: Brief
    leaks: list[Leak] = Field(default_factory=list)
    markdown: str = ""

    @property
    def safe(self) -> bool:
        return not self.leaks


# --- canonical brief -------------------------------------------------------

def _best(claims: list[Claim]) -> Claim:
    # Prefer observed + anchored, then the latest.
    return max(claims, key=lambda c: (c.kind == "observed" and c.anchored, c.kind == "observed", c.turn))


def _turn_time(ledger: Ledger, turn: int) -> float:
    owner = [t for t in ledger.transcript if t.role == "owner"]
    return owner[turn - 1].t if 0 < turn <= len(owner) else 0.0


def canonical(ledger: Ledger, extras: Optional[dict] = None) -> Brief:
    """Deterministic brief. `extras` (from the LLM, optional) may supply problem/where_to_start/data_to_request."""
    extras = extras or {}
    lines = []
    for d in DIMENSIONS:
        claims = [c for c in ledger.claims if c.dimension == d]
        if not claims:
            continue
        c = _best(claims)
        lines.append(BriefLine(dimension=d, label=DIMENSION_LABELS[d], text=c.value, kind=c.kind,
                               kind_label=KIND_LABELS[c.kind], evidence_quote=c.evidence_quote,
                               turn=c.turn, t=_turn_time(ledger, c.turn)))
    first = next((l.text for l in lines if l.dimension == "current_state"), "")
    gap_keys = [d for d in DIMENSIONS if d != "confidential" and score(ledger, d) < 2]
    gaps = [DIMENSION_LABELS[d] for d in gap_keys]
    open_q = [OpenQuestion(question=u.question, lead=u.who_might_know) for u in ledger.unknowns]
    open_q += [OpenQuestion(question=f"{DIMENSION_LABELS[d]}: not yet confirmed with evidence") for d in gap_keys
               if not any(u.dimension == d for u in ledger.unknowns)]
    where = extras.get("where_to_start") or [
        f"Talk to {u.who_might_know} about: {u.question}" for u in ledger.unknowns if u.who_might_know
    ][:3] or ["Reproduce the incident described under Current state."]
    return Brief(
        problem=extras.get("problem") or first,
        lines=lines,
        where_to_start=where[:3],
        data_to_request=extras.get("data_to_request") or [f"Evidence for: {g}" for g in gaps][:4],
        open_questions=open_q,
        parked=list(ledger.parked),
        coverage=sum(score(ledger, d) == 2 for d in DIMENSIONS),
    )


# --- numbers ---------------------------------------------------------------

_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|lac|crore|crores|cr|m|million|%|percent)?\b",
                  re.IGNORECASE)
_MULT = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7,
         "cr": 1e7, "m": 1e6, "million": 1e6}


def numbers(text: str) -> list[tuple[float, re.Match]]:
    """All numeric values in text, normalised: '1,200' = '1200' = '1.2k'; Indian lakh/crore supported."""
    out = []
    for m in _NUM.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        v *= _MULT.get((m.group(2) or "").lower(), 1)
        out.append((v, m))
    return out


# shortcut: numbers below 10 are not leak-matched (list numbering would false-positive); revisit if small metrics matter.
MIN_LEAK_NUMBER = 10


def _secret_numbers(span: str) -> set[float]:
    return {v for v, _ in numbers(span) if v >= MIN_LEAK_NUMBER}


def _distinctive_tokens(span: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", span)
    return [w for w in words if w.lower() not in GENERIC and len(w) > 2]


# --- redaction -------------------------------------------------------------

def _hidden(sensitive: list[Sensitive]) -> list[Sensitive]:
    # Fail closed: an item with no owner choice yet is treated as "generalise".
    return [s for s in sensitive if s.choice != "keep"]


def _replace(text: str, s: Sensitive) -> str:
    repl = s.generalisation or DEFAULT_GENERALISATION[s.category]
    text = re.sub(re.escape(s.span), repl, text, flags=re.IGNORECASE)
    for tok in _distinctive_tokens(s.span):
        text = re.sub(rf"\b{re.escape(tok)}\b", repl, text, flags=re.IGNORECASE)
    secret = _secret_numbers(s.span)
    if secret:
        for v, m in reversed(numbers(text)):
            if v in secret:
                text = text[:m.start()] + repl + text[m.end():]
    return text


def _contains(text: str, s: Sensitive) -> bool:
    low = text.lower()
    if s.span.lower() in low:
        return True
    if any(re.search(rf"\b{re.escape(t.lower())}\b", low) for t in _distinctive_tokens(s.span)):
        return True
    secret = _secret_numbers(s.span)
    return bool(secret) and any(v in secret for v, _ in numbers(text))


def redact(brief: Brief, sensitive: list[Sensitive], audience: Audience) -> Brief:
    """Code-enforced redaction. Runs BEFORE any LLM sees text for builders/everyone."""
    b = brief.model_copy(deep=True)
    b.audience = audience
    if audience == "me":
        return b
    hidden = _hidden(sensitive)
    removed = [s for s in hidden if s.choice == "remove"]
    swapped = [s for s in hidden if s.choice != "remove"]

    def fix(text: str) -> Optional[str]:
        if any(_contains(text, s) for s in removed):
            return None
        for s in swapped:
            text = _replace(text, s)
        return text

    b.problem = fix(b.problem) or "[problem statement withheld]"
    kept = []
    for line in b.lines:
        t = fix(line.text)
        if t is None:
            continue
        line.text = t
        line.evidence_quote = fix(line.evidence_quote) or ""
        kept.append(line)
    b.lines = kept
    b.where_to_start = [t for t in map(fix, b.where_to_start) if t]
    b.data_to_request = [t for t in map(fix, b.data_to_request) if t]
    b.open_questions = [OpenQuestion(question=q, lead=fix(o.lead) or "")
                        for o in b.open_questions if (q := fix(o.question))]
    b.parked = [t for t in map(fix, b.parked) if t]
    if audience == "everyone":
        keep = {"who", "success_test"}
        b.lines = [l for l in b.lines if l.dimension in keep]
        for l in b.lines:
            l.evidence_quote = ""
        b.where_to_start, b.data_to_request, b.open_questions, b.parked = [], [], [], []
    n_gen = sum(1 for s in swapped)
    b.redaction_summary = f"{len(hidden)} private item(s): {n_gen} generalised, {len(removed)} removed."
    return b


def _texts(b: Brief):
    yield "problem", b.problem
    for l in b.lines:
        yield l.label, l.text
        yield f"{l.label} (quote)", l.evidence_quote
    for i, t in enumerate(b.where_to_start, 1):
        yield f"Where to start {i}", t
    for t in b.data_to_request:
        yield "Data to request", t
    for o in b.open_questions:
        yield "Open question", f"{o.question} {o.lead}"
    for t in b.parked:
        yield "Parked", t


def leak_check(b: Brief, sensitive: list[Sensitive]) -> list[Leak]:
    if b.audience == "me":
        return []
    leaks = []
    for where, text in _texts(b):
        for s in _hidden(sensitive):
            if text and _contains(text, s):
                leaks.append(Leak(span=s.span, where=where, snippet=text[:120]))
    return leaks


# --- versions + markdown ---------------------------------------------------

Polisher = Callable[[Brief], Brief]


def identity(b: Brief) -> Brief:
    return b


def to_markdown(b: Brief, sensitive: list[Sensitive]) -> str:
    title = {"me": "For me", "builders": "For builders", "everyone": "For everyone"}[b.audience]
    md = [f"# Birbal Brief · {title}", "", f"**Problem:** {b.problem}", ""]
    for l in b.lines:
        q = f' — "{l.evidence_quote}"' if l.evidence_quote and b.audience == "me" else ""
        md.append(f"- **{l.label}:** {l.text} `{l.kind_label}`{q}")
    if b.where_to_start:
        md += ["", "## Where to start", *[f"{i}. {t}" for i, t in enumerate(b.where_to_start, 1)]]
    if b.data_to_request:
        md += ["", "## Data to request", *[f"- {t}" for t in b.data_to_request]]
    if b.open_questions:
        md += ["", "## Open questions",
               *[f"- {o.question}" + (f" (lead: {o.lead})" if o.lead else "") for o in b.open_questions]]
    if b.parked:
        md += ["", "## Parked by owner", *[f"- {t}" for t in b.parked]]
    if b.audience == "me" and sensitive:
        md += ["", "## Private items (consent log)",
               *[f"- {s.span} ({s.category}): {s.choice or 'pending → hidden'}" for s in sensitive]]
    elif b.redaction_summary:
        md += ["", f"_Redacted: {b.redaction_summary}_"]
    return "\n".join(md) + "\n"


def versions(ledger: Ledger, extras: Optional[dict] = None, polish: Polisher = identity) -> dict[str, Version]:
    base = canonical(ledger, extras)
    out = {}
    for aud in ("me", "builders", "everyone"):
        b = redact(base, ledger.sensitive, aud)
        if aud != "me":
            b = polish(b)  # the LLM only ever sees already-redacted text
        out[aud] = Version(brief=b, leaks=leak_check(b, ledger.sensitive), markdown=to_markdown(b, ledger.sensitive))
    return out
