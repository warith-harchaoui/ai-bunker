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
from pathlib import Path

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


def _tool_schemas(count: int, total_tokens: int) -> list[dict]:
    """``count`` tool schemas whose serialised form costs ``total_tokens``.

    Solved in CHARACTERS, which is what the budget actually measures: it
    serialises the whole list once (`json.dumps(tools)`) and counts that blob,
    so the envelope is per-list rather than per-tool and the relationship is
    linear in description length.

    Solving it is the point. This was once a hard-coded description size with
    "the envelope costs ~27 tokens per tool" in a comment -- true at 4.0
    characters per token, silently false at 2.5, because the envelope's
    character count is fixed while its token cost is not. A fixture that
    depends on a constant it does not name breaks when the constant is
    corrected, and then looks like the correction was wrong.
    """

    def build(description: str) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": f"tool{i}",
                    "description": description,
                    "parameters": {"type": "object"},
                },
            }
            for i in range(count)
        ]

    envelope = len(json.dumps(build(""), ensure_ascii=False))
    wanted = int(total_tokens * CHARS_PER_TOKEN)
    each = max(0, (wanted - envelope) // count)
    return build("d" * each)


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
            # Seven schemas costing the published 3,164 tokens in total,
            # solved rather than assumed -- see `_tool_schemas`.
            "tools": _tool_schemas(7, 3164),
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


def test_an_estimated_count_is_labelled_as_one_everywhere_it_surfaces(counter):
    """This module's whole subject. A ratio count is a guess, it is sometimes
    the only thing available, and the one unacceptable outcome is a guess that
    reads like a measurement.

    So the label travels: on the counter, on the measurement it produces, and
    in the warnings a reader sees. A deployment gate can refuse to run on one
    at all -- a gate that passes on a guess is worse than no gate. And when
    the engine is unreachable the fallback is the estimate rather than a
    crash, because a budget report has to render when the GPU is down, which
    is exactly when somebody is looking at it.
    """
    assert counter.backend == "ratio"
    assert counter.exact is False
    assert counter.count("x" * 400) == pytest.approx(400 / CHARS_PER_TOKEN, rel=0.01)
    assert counter.count("") == 0

    measured = measure_request(_request("hello"), counter=counter, served_context=32768)
    assert measured.backend == "ratio"
    assert measured.exact is False
    assert any("ratio" in w for w in measured.warnings)

    with pytest.raises(AssertionError, match="No tokenizer available"):
        Counter(allow_ratio=False)

    unreachable = Counter(base_url="http://127.0.0.1:1/v1", model="nope", allow_ratio=True)
    assert unreachable.backend == "ratio"
    assert unreachable.count("hello") > 0


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


def test_declaring_the_full_served_context_is_flagged_and_the_default_is_not(counter):
    """The margin is the only protection while a turn grows, so a deployment
    that declared the truth would be honest and broken. The default leaves
    one; declaring the full figure says so rather than letting the operator
    find out from a 413 at the worst moment."""
    flush = measure_request(
        _request("prompt"), counter=counter, served_context=32768, declared_context=32768
    )
    assert any("not below the served context" in w for w in flush.warnings)

    default = measure_request(_request("prompt"), counter=counter, served_context=131072)
    assert default.declared_context < default.served_context
    assert not any("not below the served context" in w for w in default.warnings)


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


def test_a_captured_request_round_trips_and_a_bad_one_says_what_is_wrong(tmp_path, counter):
    """The capture is how an operator measures a real session rather than a
    synthetic one, so it is read from a file somebody produced by hand or by
    copy-paste -- which means both ways of getting it wrong are routine, and
    neither may surface as a stack trace."""
    good = tmp_path / "req.json"
    good.write_text(json.dumps(_request("prompt", tools=[{"name": "t"}])), encoding="utf-8")
    loaded = load_request(good)
    assert measure_request(loaded, counter=counter, served_context=32768).floor_tokens > 0

    with pytest.raises(AssertionError, match="No captured request"):
        load_request(tmp_path / "absent.json")

    wrong_shape = tmp_path / "bad.json"
    wrong_shape.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(AssertionError, match="not a JSON object"):
        load_request(wrong_shape)


# ---------------------------------------------------------------------------
# The two engines this project names do not speak the same /tokenize dialect.
# ---------------------------------------------------------------------------


class _FakeEngine:
    """An engine that answers one dialect and silently ignores the other.

    This is not a contrivance. llama.cpp hands back ``{"tokens": []}`` when
    given vLLM's request body -- a zero, not an error -- which is how a
    llama.cpp deployment fell back to estimates while its operator believed
    the server was counting.
    """

    def __init__(self, speaks: str):
        self.speaks = speaks
        self.asked: list[str] = []

    def post(self, url, json=None, timeout=None):
        self.asked += [k for k in json if k != "model"]
        text = json.get(self.speaks)
        tokens = list(range(len(text.split()))) if text else []
        return _FakeResponse({"tokens": tokens})


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.parametrize("dialect", ["prompt", "content"])
def test_the_counter_finds_whichever_tokenize_dialect_the_engine_speaks(monkeypatch, dialect):
    import httpx

    engine = _FakeEngine(speaks=dialect)
    monkeypatch.setattr(httpx, "post", engine.post)

    c = Counter(base_url="http://engine.test/v1", model="m", allow_ratio=True)
    assert c.backend == "server", f"gave up on an engine that speaks {dialect!r}"
    assert c.exact is True
    assert c.count("one two three") == 3
    assert dialect in engine.asked


def test_an_engine_that_tokenizes_into_nothing_is_not_trusted(monkeypatch):
    """A zero is as disqualifying as an exception. Taking it at face value
    would mean every budget on that engine counted zero, and a budget of zero
    passes every gate."""
    import httpx

    monkeypatch.setattr(httpx, "post", _FakeEngine(speaks="neither").post)
    c = Counter(base_url="http://engine.test/v1", model="m", allow_ratio=True)
    assert c.backend == "ratio"
    assert c.exact is False


# ---------------------------------------------------------------------------
# Resolving a real tokenizer, and the estimate that stands in when none is.
#
# The estimate was the one number in this project that was folklore: a
# constant whose comment claimed a measurement nobody could reproduce. It was
# not merely imprecise, it was unsafe in the direction that founded the
# project.
# ---------------------------------------------------------------------------


def test_the_ratio_never_under_counts_the_densest_content():
    """`CHARS_PER_TOKEN` must sit at or below the lowest ratio real content
    produces, because the estimate CAN refuse a request.

    `Budget.verdict` is computed whatever the backend and the gateway returns
    413 on `unusable`, so an optimistic estimate fails to refuse a session
    that has no room -- which is the 40,433-into-32,768 failure exactly.
    Measured floor is 2.51 chars/token on markup; see
    `scripts/measure_ratio.py`, which re-measures and refuses a constant above
    it.
    """
    from ai_bunker.budget import CHARS_PER_TOKEN

    assert CHARS_PER_TOKEN <= 2.51, (
        "the estimate would under-count dense content, and it can refuse a "
        "request; run scripts/measure_ratio.py --check"
    )


def test_the_estimate_over_counts_rather_than_under_counts():
    """The property, asserted on text rather than on the constant.

    Dense markup is the adversarial case: 2.51 chars/token measured, so an
    estimate at 4.0 reported about 60% of the real cost.
    """
    from ai_bunker.budget import Counter

    counter = Counter(allow_ratio=True)
    assert counter.backend == "ratio"

    dense = "<url><loc>https://example.test/a</loc><lastmod>2026-01-01</lastmod></url>" * 40
    # The true count for this shape is len/2.51; the estimate must not be below.
    assert counter.count(dense) >= len(dense) / 2.51


def test_a_tokenizer_file_is_used_when_one_is_configured(tmp_path):
    """The sovereign way to be exact: a file on this machine.

    An earlier version of this resolved a Hugging Face repository id, which
    worked and was wrong for this project -- resolving a repository is an
    outbound call, and a gateway whose claim is that nothing leaves the local
    network cannot phone a third party to learn how to count.
    """
    tokenizers = pytest.importorskip("tokenizers")
    source = tokenizers.Tokenizer(tokenizers.models.WordLevel({"a": 0, "b": 1}, unk_token="a"))
    source.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
    path = tmp_path / "tokenizer.json"
    source.save(str(path))

    counter = Counter(model="whatever-the-engine-calls-it", tokenizer=str(path))
    assert counter.backend == "local"
    assert counter.exact
    assert counter.count("a b a") == 3


def test_a_missing_tokenizer_file_warns_and_falls_back(tmp_path):
    """Silence here would be the worst outcome: an operator who configured a
    tokenizer believes the counts are exact, and they are estimates."""
    counter = Counter(tokenizer=str(tmp_path / "absent.json"), allow_ratio=True)
    assert counter.backend == "ratio"
    assert not counter.exact


def test_nothing_resolves_a_tokenizer_over_the_network():
    """Held to structurally rather than by intent.

    `from_pretrained` resolves a model-hub repository over the network. This
    module must not call it: the gateway's whole claim is that nothing leaves
    the local network, and a count that depends on a third-party service is
    not a count this project can make.
    """
    source = Path("ai_bunker/budget.py").read_text(encoding="utf-8")
    assert "from_pretrained" not in source
    assert "huggingface" not in source.lower()


def test_an_estimate_says_it_gates_because_it_does():
    """It used to say the opposite.

    The warning read "This figure cannot gate a deployment", and the verdict
    is computed whatever the backend -- the gateway returns 413 on `unusable`.
    A module whose whole subject is honesty about measurement cannot carry a
    sentence that contradicts what the code does.
    """
    from ai_bunker.budget import Counter, measure_request

    budget = measure_request(
        {"messages": [{"role": "user", "content": "hello"}]},
        counter=Counter(allow_ratio=True),
        served_context=8192,
    )
    estimate_warnings = " ".join(w for w in budget.warnings if "ratio" in w.lower())
    assert estimate_warnings, "an estimate must say it is one"
    assert "cannot gate" not in estimate_warnings
    assert "DOES gate" in estimate_warnings or "does gate" in estimate_warnings


def test_measuring_does_not_send_unless_asked():
    """The guarantee a test in `test_gateway.py` already held, pinned here too
    because it constrains this module's design.

    Ollama reports `prompt_eval_count`, which is exact and is not a tokenizer:
    obtaining it runs the text through the model. `/v1/budget` promises to
    measure *without* sending, so the engine probe can never be chosen
    automatically -- a planning endpoint that quietly consumes
    graphics-processor time is not one anybody can plan against.
    """
    counter = Counter(base_url="http://127.0.0.1:1/v1", model="anything", allow_ratio=True)
    assert counter.allow_engine_probe is False
    assert counter.backend == "ratio"


def test_a_stalled_tokenizer_is_abandoned_quickly():
    """A probe is a liveness check, not a measurement, and it had the
    measurement's timeout.

    `_server_works` asks each dialect to tokenize the word "ping". With
    `TOKENIZE_TIMEOUT` that was two dialects times 120 seconds before the
    gateway fell back -- and the call is synchronous inside an async handler,
    so the event loop serves nobody for the duration. An engine that cannot
    tokenize "ping" in five seconds is one to stop waiting for.

    Measured against a socket that accepts and never answers, which is a
    saturated engine rather than a dead one: 10.3 seconds instead of 240.
    """
    import socket
    import threading
    import time

    from ai_bunker.budget import PROBE_TIMEOUT, TOKENIZE_TIMEOUT

    assert PROBE_TIMEOUT < TOKENIZE_TIMEOUT, "a probe must not wait like a count"

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    port = server.getsockname()[1]
    accepted: list = []

    def hold() -> None:
        while True:
            try:
                accepted.append(server.accept()[0])
            except OSError:
                return

    threading.Thread(target=hold, daemon=True).start()
    try:
        started = time.perf_counter()
        counter = Counter(base_url=f"http://127.0.0.1:{port}/v1", model="m", allow_ratio=True)
        elapsed = time.perf_counter() - started
    finally:
        server.close()

    assert counter.backend == "ratio"
    # Generous against the measured 10.3s, strict against the 240s it was.
    assert elapsed < PROBE_TIMEOUT * 6, f"took {elapsed:.1f}s to give up"
