"""
Tests for server-side token accounting.

These lock the two failure modes the module exists to catch, both of which
actually happened and neither of which the harness reported:

1. A client under-counting its own request until the server refuses it.
2. A floor that silently exceeds the compaction trigger, so compaction fires
   on every turn with nothing to reduce and the session loops forever.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json

import pytest

from ai_bunker.budget import (
    CHARS_PER_TOKEN,
    MIN_WORKING_TOKENS,
    Counter,
    load_request,
    measure_request,
    split_system,
)


@pytest.fixture
def counter():
    """A ratio counter: deterministic, no server, no model download."""
    return Counter(allow_ratio=True)


def _skills(count: int = 59, tokens_each: int = 300) -> str:
    """A skill block sized in tokens, as the harness actually injects it.

    Calibrated on the measured incident: 59 locally-installed skills whose
    descriptions came to 17,754 tokens, 68% of a 26,226-token floor. Sizing the
    fixture in tokens rather than in characters means the test asserts the
    shape of the real failure instead of whatever a guessed string length
    happens to produce.
    """
    body = "d" * int(tokens_each * CHARS_PER_TOKEN)
    inner = "".join(f"<name>s{i}</name>{body}" for i in range(count))
    return f"<skill>{inner}</skill>"


def _tokens(n: int) -> str:
    """A filler string worth roughly ``n`` tokens under the ratio counter."""
    return "d" * int(n * CHARS_PER_TOKEN)


def _incident_request(skill_tokens: int = 17_754) -> dict:
    """The 2026-09-28 request, rebuilt from its published breakdown.

    The post-fix floor was itemised as: tool schemas 3,164 · client system
    prompt 2,345 · charter 905 · knowledge index 353 = 6,767 tokens. Before the
    fix, 59 injected skill descriptions added 17,754 on top, for a floor of
    26,226 against a declared context of 26,000 -- so compaction fired on turn
    one with nothing to reduce.

    Rebuilding the fixture from those line items, rather than from a guessed
    string length, is what makes the assertions below about the *shape* of the
    failure rather than about this file's arithmetic.
    """
    charter = "# Context discipline\n" + _tokens(905 - 6)
    index = "## House knowledge\n" + _tokens(353 - 5)
    skills = ""
    if skill_tokens:
        per = skill_tokens // 59
        skills = (
            "<skill>" + "".join(f"<name>s{i}</name>{_tokens(per)}" for i in range(59)) + "</skill>"
        )
    return (
        {
            "messages": [{"role": "system", "content": _tokens(2345) + skills + charter + index}],
            # One schema per tool, as a harness sends them. The JSON envelope
            # (keys, braces, quoting) costs ~27 tokens per tool on top of the
            # description, which is itself part of what a client really sends, so
            # the descriptions are sized to leave room for it and hit ~3,164 total.
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": f"tool{i}",
                        "description": _tokens(425),
                        "parameters": {"type": "object"},
                    },
                }
                for i in range(7)
            ],
        },
        charter,
        index,
    )


def _request(system: str = "", tools: list | None = None, user: str = "") -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if user:
        messages.append({"role": "user", "content": user})
    return {"messages": messages, "tools": tools or []}


# ---------------------------------------------------------------------------
# The counter must never hide which backend produced a number.
# ---------------------------------------------------------------------------


def test_ratio_backend_is_labelled_inexact(counter):
    assert counter.backend == "ratio"
    assert counter.exact is False


def test_a_gate_can_refuse_to_run_on_an_estimate():
    """A deployment gate that passes on a guess is worse than no gate."""
    with pytest.raises(AssertionError, match="No tokenizer available"):
        Counter(allow_ratio=False)


def test_the_estimate_is_at_least_self_consistent(counter):
    text = "x" * 400
    assert counter.count(text) == pytest.approx(400 / CHARS_PER_TOKEN, rel=0.01)
    assert counter.count("") == 0


def test_an_unreachable_server_falls_back_rather_than_crashing():
    """A budget report must still render when the GPU is down."""
    c = Counter(base_url="http://127.0.0.1:1/v1", model="nope", allow_ratio=True)
    assert c.backend == "ratio"
    assert c.count("hello") > 0


def test_the_backend_is_recorded_in_the_result(counter):
    b = measure_request(_request("hello"), counter=counter, served_context=32768)
    assert b.backend == "ratio"
    assert b.exact is False
    assert any("ratio" in w for w in b.warnings)


# ---------------------------------------------------------------------------
# Attribution: a floor nobody can decompose is a floor nobody can reduce.
# ---------------------------------------------------------------------------


def test_slices_are_disjoint_and_cover_the_whole_prompt():
    charter = "# Charter\n" + "rule. " * 50
    index = "## Index\n- default: a.md\n"
    skills = "<skill><name>a</name>blah</skill>"
    system = "Client prompt. " * 20 + skills + charter + index

    slices = split_system(system, charter, index)
    assert sum(len(body) for _, _, body in slices) == len(system)
    assert {name for name, _, _ in slices} == {
        "agent skills (1)",
        "charter",
        "knowledge index",
        "client system prompt",
    }


def test_our_own_contributions_are_attributed_to_us():
    charter = "# Charter\n" + "rule. " * 50
    index = "## Index\n- default: a.md\n"
    slices = split_system("Client. " * 10 + charter + index, charter, index)
    owners = {name: owner for name, owner, _ in slices}
    assert owners["charter"] == "ai-bunker"
    assert owners["knowledge index"] == "ai-bunker"
    assert owners["client system prompt"] == "client"


def test_skill_blocks_are_counted_not_just_detected():
    skills = "<skill>" + "".join(f"<name>s{i}</name>body" for i in range(59)) + "</skill>"
    slices = split_system("prompt" + skills)
    names = [name for name, _, _ in slices]
    assert "agent skills (59)" in names


def test_unpassed_charter_is_not_silently_claimed():
    """Without being told what the charter is, we must not take credit for it."""
    system = "# Charter\nrule.\nClient prompt."
    slices = split_system(system)
    assert all(owner == "client" for _, owner, _ in slices)


def test_itemised_tokens_sum_to_the_floor(counter):
    charter = "# Charter\n" + "rule. " * 80
    system = "Client prompt. " * 40 + charter
    b = measure_request(
        _request(system, tools=[{"name": "read", "description": "d" * 400}]),
        counter=counter,
        served_context=32768,
        charter=charter,
    )
    assert sum(i.tokens for i in b.items) == b.floor_tokens


def test_items_are_ordered_by_cost(counter):
    skills = "<skill>" + "<name>a</name>" + "x" * 5000 + "</skill>"
    b = measure_request(
        _request("short prompt" + skills, tools=[{"name": "t", "description": "y" * 100}]),
        counter=counter,
        served_context=32768,
    )
    assert [i.tokens for i in b.items] == sorted((i.tokens for i in b.items), reverse=True)
    assert b.biggest is b.items[0]


def test_conversation_turns_are_not_part_of_the_floor(counter):
    """Compaction can reduce a conversation; counting it would hide the problem."""
    bare = measure_request(_request("prompt"), counter=counter, served_context=32768)
    chatty = measure_request(
        _request("prompt", user="a very long user message " * 500),
        counter=counter,
        served_context=32768,
    )
    assert bare.floor_tokens == chatty.floor_tokens


# ---------------------------------------------------------------------------
# Failure mode 1: declared context not below served context.
# ---------------------------------------------------------------------------


def test_declaring_the_full_served_context_is_flagged(counter):
    b = measure_request(
        _request("prompt"),
        counter=counter,
        served_context=32768,
        declared_context=32768,
    )
    assert any("not below the served context" in w for w in b.warnings)


def test_the_default_declaration_leaves_a_margin(counter):
    b = measure_request(_request("prompt"), counter=counter, served_context=131072)
    assert b.declared_context < b.served_context
    assert not any("not below the served context" in w for w in b.warnings)


# ---------------------------------------------------------------------------
# Failure mode 2: the floor exceeds the compaction trigger.
# ---------------------------------------------------------------------------


def test_the_measured_floor_matches_its_published_breakdown(counter):
    """With the skills removed, the floor must come back to its itemised 6,767."""
    request, charter, index = _incident_request(skill_tokens=0)
    b = measure_request(
        request,
        counter=counter,
        served_context=32768,
        declared_context=26000,
        compaction_reserve=6000,
        charter=charter,
        knowledge_index=index,
    )
    by_name = {i.name: i.tokens for i in b.items}
    assert by_name["tool schemas (7)"] == pytest.approx(3164, rel=0.03)
    assert by_name["client system prompt"] == pytest.approx(2345, rel=0.02)
    assert by_name["charter"] == pytest.approx(905, rel=0.02)
    assert by_name["knowledge index"] == pytest.approx(353, rel=0.02)
    assert b.floor_tokens == pytest.approx(6767, rel=0.03)

    # 13,233 tokens of conversation on a 32k model: the session works, and it
    # has no slack. "tight" is the honest verdict, and the fix that produced
    # these numbers was a rescue, not a comfortable deployment.
    assert b.working_tokens == pytest.approx(13_233, rel=0.03)
    assert b.verdict == "tight"


def test_a_floor_above_the_compaction_trigger_predicts_the_loop(counter):
    """The incident itself: 59 injected skills put the floor over the trigger.

    The session compacted on turn one, had nothing to compact -- a floor is not
    in the conversation -- and looped `build -> compact -> build` forever,
    returning 8 tokens per turn while occupying the GPU.

    One honest caveat about the fixture. The historical floor was 26,226, built
    on a 8,472-token baseline; the baseline here is the later, tightened 6,767
    (a dropped tool schema and rewritten tool descriptions accounted for the
    difference). So this reproduces 17,754 tokens of skills on top of the
    *fixed* baseline: ~24,500, which stays under the 26,000 declared context
    and is still far over the 20,000 compaction trigger. That is the point --
    the loop needs only the second condition, so tightening the tool schemas
    would not have saved the session while the skills were still being
    injected.
    """
    request, charter, index = _incident_request()
    b = measure_request(
        request,
        counter=counter,
        served_context=32768,
        declared_context=26000,
        compaction_reserve=6000,
        charter=charter,
        knowledge_index=index,
    )
    skills = next(i for i in b.items if i.name.startswith("agent skills"))
    assert skills.tokens == pytest.approx(17_754, rel=0.02), "fixture drifted"
    assert b.floor_tokens == pytest.approx(24_500, rel=0.03)
    assert skills.tokens / b.floor_tokens > 0.70, "skills must dominate the floor"

    # The two facts that made the session unusable, asserted separately so a
    # regression says which one came back.
    assert b.floor_tokens > b.compaction_starts_at, "compaction could never help"
    assert b.working_tokens < 0, "there was negative room to work"
    assert b.verdict == "unusable"
    assert any("nothing to reduce" in w for w in b.warnings)
    assert any("loops and never answers" in w for w in b.warnings)


def test_the_culprit_is_named_not_merely_totalled(counter):
    """A number without a cause cannot be acted on."""
    request, charter, index = _incident_request()
    b = measure_request(
        request,
        counter=counter,
        served_context=32768,
        declared_context=26000,
        compaction_reserve=6000,
        charter=charter,
        knowledge_index=index,
    )
    assert b.biggest is not None
    assert "agent skills" in b.biggest.name
    assert b.biggest.owner == "client", "the blame must land on the harness, not on us"
    assert any("agent skills" in w for w in b.warnings)
    assert any("start there" in w for w in b.warnings)


def test_our_own_guardrails_are_cheap(counter):
    """The published claim: charter plus index cost under 5% of the window."""
    request, charter, index = _incident_request(skill_tokens=0)
    b = measure_request(
        request,
        counter=counter,
        served_context=32768,
        declared_context=26000,
        compaction_reserve=6000,
        charter=charter,
        knowledge_index=index,
    )
    ours = sum(i.tokens for i in b.items if i.owner == "ai-bunker")
    assert ours / b.declared_context < 0.05


def test_a_healthy_session_gets_a_clean_verdict(counter):
    b = measure_request(
        _request(
            "You are a coding agent. " * 30, tools=[{"name": "read", "description": "d" * 300}]
        ),
        counter=counter,
        served_context=262144,
        compaction_reserve=16000,
    )
    assert b.verdict == "ok"
    assert b.working_tokens > MIN_WORKING_TOKENS * 3
    assert not any("nothing to reduce" in w for w in b.warnings)


@pytest.mark.parametrize(
    "skill_tokens, expected",
    [(0, "tight"), (17_754, "unusable")],
)
def test_the_verdict_tracks_the_remaining_space(counter, skill_tokens, expected):
    """ok / tight / unusable must follow the one number that matters.

    Held at the incident's 26,000-declared / 6,000-reserved budget and varied
    only by how much the harness injects, since that is the variable a
    deployment can actually change.
    """
    request, charter, index = _incident_request(skill_tokens)
    b = measure_request(
        request,
        counter=counter,
        served_context=32768,
        declared_context=26000,
        compaction_reserve=6000,
        charter=charter,
        knowledge_index=index,
    )
    assert b.verdict == expected, f"{b.working_tokens:,} tokens left"


def test_the_working_space_arithmetic_is_the_one_documented(counter):
    b = measure_request(
        _request("prompt " * 100),
        counter=counter,
        served_context=131072,
        declared_context=104000,
        compaction_reserve=16000,
    )
    assert b.compaction_starts_at == 104000 - 16000
    assert b.working_tokens == b.compaction_starts_at - b.floor_tokens


def test_max_output_does_not_reduce_conversation_space(counter):
    """It is covered by the declared-vs-served gap; subtracting it twice was a bug."""
    small = measure_request(
        _request("prompt"), counter=counter, served_context=131072, max_output=1024
    )
    large = measure_request(
        _request("prompt"), counter=counter, served_context=131072, max_output=32768
    )
    assert small.working_tokens == large.working_tokens


# ---------------------------------------------------------------------------
# Loading.
# ---------------------------------------------------------------------------


def test_a_captured_request_round_trips(tmp_path, counter):
    path = tmp_path / "req.json"
    path.write_text(json.dumps(_request("prompt", tools=[{"name": "t"}])), encoding="utf-8")
    loaded = load_request(path)
    assert measure_request(loaded, counter=counter, served_context=32768).floor_tokens > 0


def test_a_missing_capture_says_so(tmp_path):
    with pytest.raises(AssertionError, match="No captured request"):
        load_request(tmp_path / "absent.json")


def test_a_non_object_capture_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(AssertionError, match="not a JSON object"):
        load_request(path)
