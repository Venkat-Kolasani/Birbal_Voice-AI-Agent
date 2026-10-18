from brain.controller import gap_report, merge, score
from brain.schema import Claim, Contradiction, Ledger, OwnerChoice, ScribeOutput, Sensitive, Unknown


def claim(dim, kind="observed", anchored=True, value="x"):
    return Claim(dimension=dim, value=value, kind=kind, anchored=anchored)


def test_empty_ledger_asks_for_incident():
    assert gap_report(Ledger(), 0).focus == "current_state"


def test_scores_guess_vs_observed():
    led = Ledger(claims=[claim("who", kind="inferred")])
    assert score(led, "who") == 1
    led.claims.append(claim("who"))
    assert score(led, "who") == 2
    assert score(led, "frequency") == 0


def test_adjective_only_observed_is_partial():
    led = Ledger(claims=[claim("frequency", anchored=False)])
    assert score(led, "frequency") == 1


def test_consent_beats_everything():
    led = Ledger(sensitive=[Sensitive(span="Kaveri Bank", category="org_or_partner_name")],
                 contradictions=[Contradiction(dimension="frequency", a="40/day", b="1,200/week")])
    gr = gap_report(led, 1)
    assert gr.focus == "consent" and "Kaveri Bank" in gr.why


def test_contradiction_before_dimensions():
    led = Ledger(contradictions=[Contradiction(dimension="frequency", a="40/day", b="1,200/week")])
    assert gap_report(led, 1).focus == "contradiction"


def test_merge_choice_and_resolution():
    led = Ledger()
    merge(led, ScribeOutput(sensitive=[Sensitive(span="Kaveri Bank", category="org_or_partner_name")],
                            contradictions=[Contradiction(dimension="frequency", a="a", b="b")]), 2)
    merge(led, ScribeOutput(owner_choices=[OwnerChoice(span="kaveri bank", choice="generalise")],
                            resolved_contradictions=["frequency"]), 3)
    assert led.sensitive[0].choice == "generalise" and led.sensitive[0].decided_turn == 3
    assert led.contradictions[0].resolved
    assert score(led, "confidential") == 2


def test_duplicate_sensitive_span_ignored():
    led = Ledger()
    s = Sensitive(span="Kaveri Bank", category="org_or_partner_name")
    merge(led, ScribeOutput(sensitive=[s]), 1)
    merge(led, ScribeOutput(sensitive=[s.model_copy()]), 2)
    assert len(led.sensitive) == 1


def test_first_unsettled_in_brief_order():
    led = Ledger(claims=[claim("current_state"), claim("who", kind="inferred")])
    # who is only a guess -> deepen it before moving on
    gr = gap_report(led, 2)
    assert gr.focus == "who" and "guess" in gr.why
    led.claims.append(claim("who"))
    assert gap_report(led, 2).focus == "workaround"


def test_unknown_with_lead_settles_dimension():
    led = Ledger(claims=[claim(d) for d in ["current_state", "who", "workaround", "impact", "frequency",
                                             "constraints", "success_test"]],
                 unknowns=[Unknown(dimension="attempted", question="what was tried?", who_might_know="platform team")])
    assert gap_report(led, 3).focus == "readback"


def test_readback_on_time_or_done():
    assert gap_report(Ledger(), 8.0).ready_for_readback
    assert gap_report(Ledger(owner_done=True), 1).focus == "readback"
