"""Birbal's Notes: turns one owner answer into structured notes. Never raises."""
import logging

from pydantic import ValidationError

from . import llm
from .prompts import EXTRAS_SYSTEM, SCRIBE_SYSTEM, extras_user, scribe_user
from .schema import Ledger, ScribeOutput

log = logging.getLogger("birbal.scribe")


async def run(ledger: Ledger, birbal_said: str, owner_said: str) -> ScribeOutput:
    data = await llm.complete_json(SCRIBE_SYSTEM, scribe_user(ledger, birbal_said, owner_said))
    if data is None:
        return ScribeOutput()
    try:
        return ScribeOutput.model_validate(data)
    except ValidationError as e:
        # Keep the valid parts: drop invalid list items one by one.
        log.warning("Scribe output invalid, salvaging: %s", e.errors()[:3])
        clean = {}
        for field, f in ScribeOutput.model_fields.items():
            if field not in data:
                continue
            try:
                ScribeOutput.model_validate({field: data[field]})
                clean[field] = data[field]
            except ValidationError:
                if isinstance(data[field], list):
                    ok = []
                    for item in data[field]:
                        try:
                            ScribeOutput.model_validate({field: [item]})
                            ok.append(item)
                        except ValidationError:
                            pass
                    clean[field] = ok
        return ScribeOutput.model_validate(clean)


async def extras(redacted_lines: list[tuple[str, str, str]]) -> dict:
    """LLM-written problem / where to start / data to request, from already-redacted lines."""
    data = await llm.complete_json(EXTRAS_SYSTEM, extras_user(redacted_lines))
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in ("problem", "where_to_start", "data_to_request") if data.get(k)}
