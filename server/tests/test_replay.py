import asyncio

from brain.session import Session


def run_demo():
    s = Session()
    asyncio.run(s.replay(pace=0))
    return s


def test_replay_reaches_readback_and_full_coverage():
    s = run_demo()
    st = s.state()
    assert st["ended"]
    assert s.gap().focus == "readback"
    assert st["clear"] >= 8, [(r["key"], r["score"]) for r in st["rows"]]


def test_replay_contradiction_resolved_and_choices_made():
    s = run_demo()
    assert s.ledger.contradictions and all(c.resolved for c in s.ledger.contradictions)
    assert {x.span: x.choice for x in s.ledger.sensitive} == {
        "Kaveri Bank": "generalise", "1,200": "generalise", "Ravi": "generalise"}


def test_replay_brief_builder_version_safe():
    s = run_demo()
    v = asyncio.run(s.brief())
    assert v["builders"].safe, v["builders"].leaks
    md = v["builders"].markdown
    for secret in ["Kaveri", "1,200", "Ravi"]:
        assert secret not in md
    assert "a partner bank" in md and "platform team lead" in md
    assert "Kaveri Bank" in v["me"].markdown
    oq = [o.question for o in v["builders"].brief.open_questions]
    assert sum("tried" in q.lower() for q in oq) == 1, oq


def test_controller_mid_interview_asks_consent_after_bank():
    from brain.schema import ScribeOutput
    import json
    from brain.session import FIXTURES
    turns = json.loads((FIXTURES / "demo_interview.json").read_text())["turns"]
    s = Session()
    s.start()
    for t in turns[:2]:
        s.add_birbal(t["birbal"])
        s.add_owner(t["owner"], ScribeOutput.model_validate(t["scribe"]))
    assert s.gap().focus == "consent"
    assert "CONSENT" in s.note() and "Kaveri Bank" in s.note()
