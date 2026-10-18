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


def test_context_window_keeps_recent_turns_only():
    msgs = []
    for i in range(12):
        msgs += [{"role": "assistant", "content": f"q{i}"}, {"role": "user", "content": f"a{i}"}]
    out = rewrite(msgs, "[controller] N", None, keep=6)
    assert len(out) <= 6 and out[0]["role"] == "user" and out[-1]["content"].startswith("a11")


def test_non_dict_context_messages_are_preserved():
    class Opaque:  # stands in for pipecat's LLMSpecificMessage
        pass
    o = Opaque()
    msgs = [{"role": "user", "content": "hi"}, o, {"role": "assistant", "content": "q"}, {"role": "user", "content": "a"}]
    out = rewrite(msgs, "[controller] N", None)
    assert o in out and out[-1]["content"] == "a\n\n[controller] N"
