from brain.brief import Brief, BriefLine, leak_check, numbers, redact, versions
from brain.schema import Claim, Ledger, Sensitive, Unknown

BANK = Sensitive(span="Kaveri Bank", category="org_or_partner_name", generalisation="a partner bank",
                 choice="generalise")
METRIC = Sensitive(span="1,200", category="business_metric", generalisation="over a thousand",
                   choice="generalise")


def ledger():
    return Ledger(
        claims=[
            Claim(dimension="current_state", kind="observed", anchored=True, turn=2,
                  value="Bank verification with Kaveri Bank spins after PAN upload",
                  evidence_quote="the bank verification with Kaveri Bank just spun"),
            Claim(dimension="frequency", kind="observed", anchored=True, turn=4,
                  value="1,200 merchants a week abandon", evidence_quote="The report. 1,200."),
            Claim(dimension="who", kind="inferred", value="Small retail merchants"),
        ],
        sensitive=[BANK, METRIC],
        unknowns=[Unknown(dimension="attempted", question="What was tried before?", who_might_know="Ravi")],
    )


def test_numbers_normalise():
    vals = {v for v, _ in numbers("1,200 or 1200 or 1.2k or 2 lakh or 3 crore")}
    assert {1200.0, 200000.0, 30000000.0} <= vals


def test_builder_version_is_redacted_and_safe():
    v = versions(ledger())
    b = v["builders"]
    assert b.safe, b.leaks
    assert "Kaveri" not in b.markdown and "1,200" not in b.markdown
    assert "a partner bank" in b.markdown and "over a thousand" in b.markdown


def test_owner_version_keeps_everything():
    md = versions(ledger())["me"].markdown
    assert "Kaveri Bank" in md and "1,200" in md and "consent log" in md


def test_leak_check_catches_variants():
    for text in ["Kaveri said no", "about 1200 a week", "nearly 1.2k merchants", "KAVERI BANK"]:
        b = Brief(audience="builders", problem=text)
        assert leak_check(b, [BANK, METRIC]), text


def test_small_list_numbers_do_not_false_positive():
    b = Brief(audience="builders", where_to_start=["1. Get logs", "2. Shadow 5 calls"])
    assert not leak_check(b, [METRIC])


def test_remove_drops_lines():
    led = ledger()
    led.sensitive[1] = METRIC.model_copy(update={"choice": "remove"})
    b = versions(led)["builders"].brief
    assert all("1,200" not in l.text and "thousand" not in l.text for l in b.lines)
    assert not any(l.dimension == "frequency" for l in b.lines)


def test_pending_choice_fails_closed():
    led = ledger()
    led.sensitive[0] = BANK.model_copy(update={"choice": None})
    v = versions(led)["builders"]
    assert "Kaveri" not in v.markdown and v.safe


def test_keep_is_shared():
    led = ledger()
    led.sensitive[0] = BANK.model_copy(update={"choice": "keep"})
    assert "Kaveri Bank" in versions(led)["builders"].markdown


def test_everyone_is_teaser_only():
    b = versions(ledger())["everyone"].brief
    assert {l.dimension for l in b.lines} <= {"who", "success_test"}
    assert not b.where_to_start and not b.open_questions


def test_polisher_cannot_see_secrets():
    seen = []

    def spy(b):
        seen.append(b.model_dump_json())
        return b
    versions(ledger(), polish=spy)
    assert seen and all("Kaveri" not in s and "1,200" not in s for s in seen)


def test_person_lead_redacted():
    led = ledger()
    led.sensitive.append(Sensitive(span="Ravi", category="person_name", generalisation="the platform team lead",
                                   choice="generalise"))
    md = versions(led)["builders"].markdown
    assert "Ravi" not in md and "platform team lead" in md


def test_handtyped_secret_blocks():
    b = redact(versions(ledger())["me"].brief, [BANK, METRIC], "builders")
    b.lines.append(BriefLine(dimension="impact", label="Why it matters", text="Kaveri Bank SLA breach"))
    assert leak_check(b, [BANK, METRIC])
