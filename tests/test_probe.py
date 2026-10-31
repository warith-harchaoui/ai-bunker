"""
The number every budget is measured against, asked of the engine.

`upstreams.<name>.served_context` is, in `config.py`'s own words, the single
most load-bearing figure in this project. The guard that existed catches a
misspelled key -- `served_kontext: 32768` parsed, loaded, and left the gateway
declaring 104,857 tokens against an engine serving 32,768, which is the
incident this project was built after. That hole is closed.

`served_context: 131072` against an engine serving 40,960 is spelled
perfectly. It parses, it loads, and it reproduces the same incident with
nothing to grep for -- and on the machine this was written on, that is not
hypothetical: the shipped default is 131,072 and `qwen3:8b` serves 40,960.

So `doctor` asks. Nothing here touches the network: `probe._get` is the single
seam every source goes through, and it is stubbed.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest

from ai_bunker import probe
from ai_bunker.config import Upstream


def _upstream(**kwargs) -> Upstream:
    return Upstream(name="local", base_url="http://127.0.0.1:11434/v1", **kwargs)


@pytest.fixture
def answers(monkeypatch):
    """Stub `probe._get`, keyed on the URL it is called with."""
    replies: dict[str, dict | None] = {}

    def fake(url, payload=None, timeout=probe.TIMEOUT):
        return replies.get(url)

    monkeypatch.setattr(probe, "_get", fake)
    return replies


# --------------------------------------------------------------------------
# Where the answer comes from.
# --------------------------------------------------------------------------


def test_ollama_publishes_the_context_under_an_architecture_prefixed_key(answers):
    """`qwen3.context_length`, `llama.context_length`, `gemma3.context_length`.

    The architecture is part of the key, so it is matched by suffix rather
    than guessed -- a list of architectures would be a list that goes stale
    every time somebody releases a model.
    """
    answers["http://127.0.0.1:11434/api/show"] = {
        "model_info": {
            "general.architecture": "qwen3",
            "qwen3.block_count": 36,
            "qwen3.context_length": 40960,
        }
    }
    found, source = probe.served_context(_upstream(model="qwen3:8b"))
    assert found == 40960
    assert "ollama" in source


def test_a_model_this_machine_has_not_pulled_publishes_nothing(answers):
    """The correct answer, not a gap: a context for a model that is not here
    would be a number about somebody else's machine."""
    answers["http://127.0.0.1:11434/api/show"] = {"error": "model 'nope' not found"}
    assert probe.served_context(_upstream(model="nope"))[0] is None


def test_an_upstream_with_no_model_named_is_not_asked_about_one(answers):
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"x.context_length": 1}}
    # No model, so `/api/show` is never consulted and `/v1/models` decides.
    assert probe.served_context(_upstream())[0] is None


def test_an_openai_compatible_server_is_read_in_three_spellings(answers):
    """vLLM says `max_model_len`, `best-engine-ai-helper` says
    `context_length`, and `context_window` turns up in the wild."""
    for key in ("max_model_len", "context_length", "context_window"):
        answers["http://127.0.0.1:11434/v1/models"] = {"data": [{"id": "devstral", key: 32768}]}
        found, source = probe.served_context(_upstream(model="devstral"))
        assert (found, source) == (32768, "/v1/models"), key


def test_a_server_with_one_model_answers_even_under_another_name(answers):
    """A single-model deployment whose configuration spells the model
    differently is common, and one entry leaves nothing to resolve."""
    answers["http://127.0.0.1:11434/v1/models"] = {
        "data": [{"id": "whatever-the-server-calls-it", "max_model_len": 8192}]
    }
    assert probe.served_context(_upstream(model="what-the-operator-wrote"))[0] == 8192

    # Two entries and no name match is genuinely ambiguous, so nothing is said.
    answers["http://127.0.0.1:11434/v1/models"] = {
        "data": [{"id": "a", "max_model_len": 8192}, {"id": "b", "max_model_len": 4096}]
    }
    assert probe.served_context(_upstream(model="c"))[0] is None


def test_ollama_is_preferred_when_both_answer(answers):
    """It reads the weights' own metadata; `/v1/models` reports whatever the
    server was started with."""
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"q.context_length": 40960}}
    answers["http://127.0.0.1:11434/v1/models"] = {"data": [{"id": "q", "max_model_len": 131072}]}
    assert probe.served_context(_upstream(model="q"))[0] == 40960


def test_nonsense_is_not_a_measurement(answers):
    """Zero, negative and non-integers are refused rather than believed. A
    server that answers `"context_length": "unknown"` must not set a budget."""
    for value in (0, -1, "40960", None, 1.5):
        answers["http://127.0.0.1:11434/v1/models"] = {
            "data": [{"id": "q", "max_model_len": value}]
        }
        assert probe.served_context(_upstream(model="q"))[0] is None, value


# --------------------------------------------------------------------------
# And which direction is a mistake.
# --------------------------------------------------------------------------


def test_configured_above_what_the_engine_serves_is_the_founding_incident(answers):
    """The live specimen. On the machine this was written on, the shipped
    default is 131,072 and `qwen3:8b` serves 40,960 -- a gateway declaring
    three times the room the engine has, with a correctly spelled config."""
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"qwen3.context_length": 40960}}
    safe, note = probe.mismatch(_upstream(model="qwen3:8b", served_context=131_072))
    assert not safe
    assert "131,072" in note and "40,960" in note
    assert "Lower served_context to 40,960" in note


def test_configured_below_is_safe_and_still_worth_saying(answers):
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"q.context_length": 262_144}}
    safe, note = probe.mismatch(_upstream(model="q", served_context=131_072))
    assert safe
    assert "capacity left unused" in note


def test_an_exact_match_says_so(answers):
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"q.context_length": 131_072}}
    safe, note = probe.mismatch(_upstream(model="q", served_context=131_072))
    assert safe
    assert "matches" in note


def test_an_engine_that_will_not_say_is_a_note_and_not_a_failure(answers):
    """`doctor` runs in the lane, where there is no engine. A check that is
    permanently red is a check nobody reads."""
    safe, note = probe.mismatch(_upstream(model="q", served_context=131_072))
    assert safe
    assert "not verified" in note


# --------------------------------------------------------------------------
# The seam itself.
# --------------------------------------------------------------------------


def test_the_request_never_raises(monkeypatch):
    """Engine down, wrong path, an HTML error page, a body that is not JSON --
    one answer for all of them, because the caller does the same thing with
    every one: says it could not ask."""
    assert probe._get("http://127.0.0.1:9/nothing-listens-here", timeout=0.2) is None
    assert probe._get("not-even-a-url", timeout=0.2) is None

    class Body:
        def read(self):
            return b"<html>502 Bad Gateway</html>"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Body())
    assert probe._get("http://example.invalid/x") is None


def test_a_json_list_is_not_a_body_this_understands(monkeypatch):
    class Body:
        def read(self):
            return b"[1, 2, 3]"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Body())
    assert probe._get("http://example.invalid/x") is None


# --------------------------------------------------------------------------
# And acting on it, not only reporting it.
# --------------------------------------------------------------------------


def _settings(**per_upstream):
    from ai_bunker.config import Settings

    return Settings(
        upstreams={
            name: Upstream(name=name, base_url="http://127.0.0.1:11434/v1", **kwargs)
            for name, kwargs in per_upstream.items()
        }
    )


def test_a_configuration_the_engine_contradicts_is_lowered_at_boot(answers):
    """`doctor` reports; `serve` acts, and reporting was not enough.

    `doctor` is a command somebody runs. A gateway started against an engine
    smaller than its configuration claims would serve the wrong figure --
    every budget, and the context declared to every client -- until a human
    thought to re-run a diagnostic.
    """
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"qwen3.context_length": 40960}}
    settings = _settings(local={"model": "qwen3:8b", "served_context": 131_072})

    notes = probe.clamp_to_engine(settings)

    assert settings.upstreams["local"].served_context == 40_960
    assert len(notes) == 1
    assert "131,072" in notes[0] and "40,960" in notes[0]
    assert "fix the configuration" in notes[0]


def test_it_never_raises_a_configured_context(answers):
    """The whole safety argument, in one assertion.

    A probe that could raise `served_context` would let one HTTP response hand
    the gateway room that does not exist -- a server answering for a different
    model, or a proxy in between. Lowering can only waste capacity; raising is
    the failure this project was built after. So a measurement *above* the
    configuration is ignored.
    """
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"q.context_length": 262_144}}
    settings = _settings(local={"model": "q", "served_context": 32_768})

    assert probe.clamp_to_engine(settings) == []
    assert settings.upstreams["local"].served_context == 32_768


def test_an_engine_that_will_not_say_changes_nothing(answers):
    """An operator starts the gateway before the engine as often as after.
    Refusing to boot, or guessing, would both be worse than carrying on with
    the configured figure."""
    settings = _settings(local={"model": "q", "served_context": 131_072})
    assert probe.clamp_to_engine(settings) == []
    assert settings.upstreams["local"].served_context == 131_072


def test_each_upstream_is_judged_against_its_own_engine(answers):
    """Three upstreams, three answers, and only the one that over-declares
    moves."""
    answers["http://127.0.0.1:11434/api/show"] = {"model_info": {"q.context_length": 40_960}}
    settings = _settings(
        small={"model": "q", "served_context": 131_072},
        exact={"model": "q", "served_context": 40_960},
        humble={"model": "q", "served_context": 8_192},
    )

    notes = probe.clamp_to_engine(settings)

    assert [u.served_context for u in settings.upstreams.values()] == [40_960, 40_960, 8_192]
    assert len(notes) == 1
    assert "small" in notes[0]


def test_building_the_application_does_not_touch_the_network(monkeypatch):
    """Why the clamp lives in `serve` and not in `State.__init__`.

    Every test that builds the gateway would run a startup probe, so the suite
    would make network calls and pay a connect timeout per upstream per test.
    This asserts the boundary: constructing the app asks nothing.
    """
    pytest.importorskip("fastapi", reason="the gateway is the [api] extra")
    from ai_bunker.gateway import create_app

    def refuse(*args, **kwargs):
        raise AssertionError("create_app must not probe an upstream")

    monkeypatch.setattr(probe, "_get", refuse)
    monkeypatch.setattr(probe, "served_context", refuse)
    create_app(_settings(local={"model": "q", "served_context": 131_072}))
