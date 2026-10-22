"""
Configuration keys the loader does not read, at every depth.

Why this exists
---------------
`_warn_about_strays` guarded the top level and nothing below it, and the
asymmetry cost exactly what it looks like it would cost.
`upstreams.<name>.served_context` is the most load-bearing figure in this
project -- the budget is measured against it -- and `served_kontext: 32768`
parsed, loaded, and left the gateway believing the default 131,072. It then
declared 104,857 tokens to every client against an engine serving 32,768:
the incident this project was built after, reproduced by one letter, in
silence.

Found by injecting, into each of the eleven gates, the defect that gate exists
to catch, and watching which ones stayed green.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.config import (
    NEED_KEYS,
    SECTION_KEYS,
    TOP_LEVEL_KEYS,
    UPSTREAM_KEYS,
    load_settings,
)

BASE = """charter_dir: charter
rules_dir: charter/rules
upstreams:
  local:
    base_url: http://127.0.0.1:8001/v1
    served_context: 32768
    model: devstral
default_upstream: local
audit_log: ""
"""


def _written(tmp_path, text: str):
    path = tmp_path / "gateway.yaml"
    path.write_text(text, encoding="utf-8")
    return load_settings(path)


# ---------------------------------------------------------------------------
# The one that keeps the key lists honest without anybody maintaining them.
# ---------------------------------------------------------------------------


def test_the_shipped_example_configuration_has_no_stray_key():
    """`config/gateway.example.yaml` is the documentation for every key, so it
    is also the test for the lists above.

    Both directions are covered by this one assertion. A key the loader learns
    to read and somebody documents, without adding it here, fails. A key
    documented and never read fails the same way -- which is how `render:` was
    found warning "unknown key `render` is being ignored" at the one placement
    that works, while both of its settings took effect.
    """
    settings = load_settings(ROOT / "config" / "gateway.example.yaml")
    assert settings.config_strays == (), "\n".join(settings.config_strays)


def test_the_example_configures_the_render_section():
    """The section that was read and undocumented. Asserted because the fix
    was to write it down, and a fix to documentation is undone by silence."""
    text = (ROOT / "config" / "gateway.example.yaml").read_text(encoding="utf-8")
    assert "\nrender:" in text
    assert "allow_hosts" in text and "neutralise" in text


# ---------------------------------------------------------------------------
# The founding incident, reproduced by one letter.
# ---------------------------------------------------------------------------


def test_one_letter_wrong_in_served_context_is_caught(tmp_path):
    """The whole reason this file exists.

    Note what is asserted and what is not: the gateway still loads, and the
    context is still the default. Refusing to start on an unreadable key is a
    bigger decision than this round is making. What changed is that the
    mistake is now *reported* with the correction next to it, and that
    `ai-bunker doctor` refuses.
    """
    settings = _written(tmp_path, BASE.replace("served_context", "served_kontext"))

    assert settings.upstreams["local"].served_context == 131_072
    assert len(settings.config_strays) == 1
    message = settings.config_strays[0]
    assert "upstreams.local.served_kontext" in message
    assert "Did you mean `served_context`?" in message, (
        "a typo is useful read next to what it was meant to be; without the "
        "suggestion this is a warning rather than a fix"
    )


def test_the_declared_window_was_four_times_the_real_one(tmp_path):
    """Why one letter mattered, stated as the number it produced.

    This is the project's own founding sentence -- "exactly the kind of figure
    that let a client send 40,433 tokens to a 32,768-token server" -- and the
    typo made it worse than the original.
    """
    right = _written(tmp_path, BASE)
    wrong = _written(tmp_path, BASE.replace("served_context", "served_kontext"))

    def declared(settings):
        upstream = settings.upstreams["local"]
        return int(upstream.served_context * settings.declared_fraction)

    assert declared(right) == 26_214
    assert declared(wrong) == 104_857
    assert declared(wrong) > 3 * declared(right)


# ---------------------------------------------------------------------------
# Every section, so no block is guarded by accident.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block", sorted(SECTION_KEYS))
def test_a_typo_in_any_block_is_caught(tmp_path, block):
    """Parametrised over the blocks themselves rather than over a list written
    out here: a block added to `SECTION_KEYS` is tested the day it is added,
    and one that is never checked cannot hide behind a test file that forgot
    it."""
    settings = _written(tmp_path, BASE + f"{block}:\n  zzz_not_a_key: 1\n")
    assert any(f"{block}.zzz_not_a_key" in s for s in settings.config_strays), list(
        settings.config_strays
    )


def test_a_typo_in_a_long_form_need_is_caught(tmp_path):
    """A `needs` entry can be a plain upstream name or a block with `upstream`
    and `model`. The shorthand must not be checked -- its key is a name an
    operator chose -- and the long form must be."""
    settings = _written(
        tmp_path,
        BASE + "needs:\n  code: local\n  structured:\n    upstream: local\n    modell: devstral\n",
    )
    assert any("needs.structured.modell" in s for s in settings.config_strays)
    assert not any("needs.code" in s for s in settings.config_strays), (
        "the shorthand names an upstream; checking it would flag every need"
    )


def test_an_operator_chosen_name_is_never_a_stray(tmp_path):
    """`routes` and `upstreams` are keyed by names, not by a vocabulary."""
    settings = _written(
        tmp_path,
        BASE.replace(
            "default_upstream: local", "default_upstream: local\nroutes:\n  gpt-5.2: local\n"
        ),
    )
    assert settings.config_strays == (), list(settings.config_strays)


def test_a_block_written_as_a_value_is_reported_rather_than_a_crash(tmp_path):
    """`budget: true` used to raise `AttributeError: 'bool' object has no
    attribute 'get'` out of the loader.

    It is a plausible mistake rather than an exotic one: the enforcement
    switch *is* called `budget`, one level down, and `MISPLACED_KEYS` already
    anticipates that confusion for `commands`, `mcp` and `mark_provenance`.
    It could not anticipate it for `budget`, because `budget:` is also a real
    block -- which is why the overlap below is correct rather than a defect,
    and why my first version of this test asserted the opposite and was wrong.
    """
    settings = _written(tmp_path, BASE + "budget: true\n")
    assert settings.config_strays, "a crash is not a report"
    assert "`budget:` is written as a value" in settings.config_strays[0]
    assert "enforcement.budget" in settings.config_strays[0], (
        "the operator has read the enforcement switch and put it one level too high"
    )


@pytest.mark.parametrize("block", ["upstreams", "needs", "routes", "enforcement", "render"])
def test_no_block_written_as_a_value_crashes_the_loader(tmp_path, block):
    """Every block, because the three keyed by operator-chosen names are read
    with `.items()` rather than `.get()` and failed with a different
    exception."""
    settings = _written(tmp_path, BASE + f"{block}: a-scalar\n")
    assert any(f"`{block}:` is written as a value" in s for s in settings.config_strays)


def test_a_block_name_may_also_be_a_key_one_level_down():
    """`budget` is a top-level block *and* a key inside `enforcement`, which
    is the configuration's design rather than an accident -- two depths, two
    readings. Asserted because the obvious sanity check is the wrong one: a
    test demanding the vocabularies be disjoint fails on correct code, and
    mine did."""
    assert "budget" in TOP_LEVEL_KEYS
    assert "budget" in SECTION_KEYS["enforcement"]
    # What must NOT overlap: the keys of a single mapping with the top level,
    # since those are read from one dictionary each.
    assert not UPSTREAM_KEYS & TOP_LEVEL_KEYS
    assert not NEED_KEYS & TOP_LEVEL_KEYS


# ---------------------------------------------------------------------------
# And what the gate does about it.
# ---------------------------------------------------------------------------


def _doctor(config) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ai_bunker.cli", "doctor", "--config", str(config)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


def test_doctor_refuses_a_configuration_with_a_stray_key(tmp_path):
    """It used to print `WARN` and return 0.

    `ai-bunker doctor` returned non-zero only when a rule's own example
    failed, which is what `ai-bunker rules --check` tests one step earlier in
    continuous integration -- so the step named "Deployment claims" tested no
    deployment claim. A stray key is now fatal, because it is the one check
    here that cannot be a deployment *choice*: an operator who writes a key
    believes it is in effect.
    """
    path = tmp_path / "typo.yaml"
    path.write_text(BASE.replace("served_context", "served_kontext"), encoding="utf-8")
    result = _doctor(path)
    assert result.returncode != 0, result.stdout
    assert "[FAIL]" in result.stdout
    assert "served_context" in result.stdout, "the suggestion belongs in the gate's output"


def test_doctor_still_passes_a_deployment_that_only_made_choices(tmp_path):
    """The other half of the distinction, and the reason the original author's
    reasoning is kept: an open gateway on a trusted network, no audit log and
    an unreachable engine are all reported and none of them is a failure."""
    path = tmp_path / "choices.yaml"
    path.write_text(BASE, encoding="utf-8")
    result = _doctor(path)
    assert result.returncode == 0, result.stdout
    assert "[WARN]" in result.stdout, "the choices must still be reported"
    assert "WARN is a report, not a refusal" in result.stdout, (
        "a reader seeing 13/16 next to a zero exit is entitled to know which "
        "number the gate is made of"
    )


def test_the_shipped_example_passes_the_gate():
    """What continuous integration runs."""
    assert _doctor(ROOT / "config" / "gateway.example.yaml").returncode == 0
