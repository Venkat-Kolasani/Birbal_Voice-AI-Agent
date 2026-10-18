"""Data model for Birbal: claims, the ledger, Scribe output, gap reports."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Dimension = Literal[
    "current_state", "who", "workaround", "impact", "frequency",
    "constraints", "attempted", "confidential", "success_test",
]
DIMENSIONS: list[str] = list(Dimension.__args__)

DIMENSION_LABELS = {
    "current_state": "Current state",
    "who": "Who",
    "workaround": "Workaround",
    "impact": "Why it matters",
    "frequency": "Frequency",
    "constraints": "Constraints",
    "attempted": "Already tried",
    "confidential": "Confidential",
    "success_test": "Success test",
}

Kind = Literal["observed", "hearsay", "inferred", "aspiration"]
# UI labels; data stays in English.
KIND_LABELS = {
    "observed": "Dekha · Seen",
    "hearsay": "Suna · Heard",
    "inferred": "Socha · Guessed",
    "aspiration": "Chahiye · Wished",
}

Category = Literal[
    "person_name", "org_or_partner_name", "customer_data",
    "business_metric", "internal_system", "unreleased_plan_or_legal",
]
Choice = Literal["keep", "generalise", "remove"]


class Sensitive(BaseModel):
    span: str
    category: Category
    generalisation: str = ""
    choice: Optional[Choice] = None
    turn: int = 0
    decided_turn: Optional[int] = None


class Claim(BaseModel):
    id: str = ""
    turn: int = 0
    dimension: Dimension
    value: str
    kind: Kind
    source: str = "owner"
    evidence_quote: str = ""
    confidence: float = 0.5
    # True when the claim has a concrete anchor: a number, a named role or a specific incident.
    anchored: bool = False


class Contradiction(BaseModel):
    dimension: Dimension
    a: str
    b: str
    resolved: bool = False


class Unknown(BaseModel):
    dimension: Dimension
    question: str
    who_might_know: str = ""


class OwnerChoice(BaseModel):
    span: str
    choice: Choice


class ScribeOutput(BaseModel):
    """What the Scribe LLM returns for one owner turn."""
    claims: list[Claim] = Field(default_factory=list)
    sensitive: list[Sensitive] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    resolved_contradictions: list[Dimension] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)
    parked_topics: list[str] = Field(default_factory=list)
    owner_choices: list[OwnerChoice] = Field(default_factory=list)
    owner_done: bool = False


class Turn(BaseModel):
    role: Literal["birbal", "owner"]
    text: str
    t: float = 0.0  # seconds since interview start


class Ledger(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    sensitive: list[Sensitive] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)
    parked: list[str] = Field(default_factory=list)
    transcript: list[Turn] = Field(default_factory=list)
    owner_done: bool = False


class GapReport(BaseModel):
    focus: str  # a dimension key, "consent", "contradiction" or "readback"
    why: str
    pending_consent: list[Sensitive] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    parked: list[str] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    minutes_elapsed: float = 0.0
    ready_for_readback: bool = False
