from bot import rewrite


def test_note_rides_on_last_user_message_and_is_swapped():
    msgs = [{"role": "assistant", "content": "Namaste"}, {"role": "user", "content": "hi"}]
    m1 = rewrite(msgs, "[controller] A", None)
    assert m1[-1] == {"role": "user", "content": "hi\n\n[controller] A"}
    assert all(m["role"] != "developer" for m in m1)  # Groq-safe: no developer role
    m1 += [{"role": "assistant", "content": "Q?"}, {"role": "user", "content": "more"}]
    m2 = rewrite(m1, "[controller] B", "[controller] A")
    contents = [m["content"] for m in m2]
    assert contents == ["Namaste", "hi", "Q?", "more\n\n[controller] B"]
    assert msgs[1]["content"] == "hi"  # input not mutated


def test_note_without_user_turn_yet():
    assert rewrite([{"role": "assistant", "content": "Namaste"}], "[controller] A", None)[-1] == \
        {"role": "user", "content": "[controller] A"}
