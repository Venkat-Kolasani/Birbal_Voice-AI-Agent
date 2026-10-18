from brain.controller import gap_report
from brain.prompts import TALKER_SYSTEM, controller_note, scribe_user, talker_messages
from brain.schema import Claim, Ledger, Turn


def test_note_carries_last_noted_and_clear():
    led = Ledger(claims=[Claim(dimension="current_state", value="verification spins after PAN", kind="observed", anchored=True)])
    note = controller_note(gap_report(led, 1), led)
    assert note.startswith("[controller]") and "Last noted: verification spins after PAN" in note
    assert "Already clear: Current state" in note
    assert len(note.split()) < 120


def test_scribe_sees_earlier_exchanges():
    led = Ledger(transcript=[Turn(role="birbal", text="Q1"), Turn(role="owner", text="the Kaveri one"),
                             Turn(role="birbal", text="Q2"), Turn(role="owner", text="that bank again")])
    u = scribe_user(led, "Q2", "that bank again")
    assert "Owner: the Kaveri one" in u and 'Owner answered: "that bank again"' in u


def test_talker_note_rides_on_last_owner_turn():
    msgs = talker_messages([Turn(role="birbal", text="hi"), Turn(role="owner", text="x")], "[controller] N")
    assert msgs[-1] == {"role": "user", "content": "x\n\n[controller] N"}


def test_talker_rules_present():
    for rule in ["echoing ONE concrete detail", "exactly one question mark", 'Never start a question with "Why"']:
        assert rule in TALKER_SYSTEM
