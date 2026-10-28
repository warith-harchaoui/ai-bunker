"""
Tests for the runtime's own words.

A translation catalogue has exactly one interesting failure mode: it falls
behind. A key is added in English and nowhere else, or a translator reorders a
sentence and drops a placeholder with it, and nobody notices until a French
deployment shows an agent the word `deps.undeclared` or raises a `KeyError`
while explaining a refusal. Everything here exists to make that impossible
rather than unlikely.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.i18n import (
    DEFAULT_LOCALE,
    LOCALE_DIR,
    Translator,
    _load,
    available,
    missing,
    negotiate,
    placeholders,
    translator,
)
from ai_bunker.pipeline import apply_outbound
from ai_bunker.rules import load_rules, refusal_message

OTHERS = [locale for locale in available() if locale != DEFAULT_LOCALE]


@pytest.fixture(scope="module")
def shipped():
    return load_rules(ROOT / "charter" / "rules")


def command(text: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "bash", "arguments": json.dumps({"command": text})}}
                    ]
                }
            }
        ]
    }


# ---------------------------------------------------------------------------
# The catalogues agree with each other.
# ---------------------------------------------------------------------------


def test_there_is_more_than_one_locale():
    """Otherwise everything below passes for the wrong reason."""
    assert len(available()) >= 2
    assert available()[0] == DEFAULT_LOCALE


@pytest.mark.parametrize("locale", OTHERS)
def test_no_key_is_missing_and_none_is_extra(locale):
    """Both directions. A missing key falls back and goes unnoticed; an extra
    one is a translation of something that no longer exists, which is how a
    catalogue starts lying about what the gateway says."""
    absent, extra = missing(locale)
    assert absent == [], f"{locale} is missing: {absent}"
    assert extra == [], f"{locale} has keys {DEFAULT_LOCALE} does not: {extra}"


@pytest.mark.parametrize("locale", OTHERS)
def test_every_message_keeps_the_same_placeholders(locale):
    """The failure that raises in production rather than reading badly.

    A translator who drops `{count}` produces a message that formats fine
    until the day it is called with a count, and one who invents `{total}`
    produces a `KeyError` inside a refusal.
    """
    base = _load(DEFAULT_LOCALE)
    other = _load(locale)
    wrong = {
        key: (placeholders(base[key]), placeholders(other[key]))
        for key in base
        if key in other and placeholders(base[key]) != placeholders(other[key])
    }
    assert wrong == {}, f"placeholders disagree in {locale}: {wrong}"


@pytest.mark.parametrize("locale", available())
def test_no_message_uses_a_positional_placeholder(locale):
    """`{0}` cannot be reordered by a language that puts the subject
    elsewhere, which is the whole reason named parameters are the rule."""
    bad = {k: v for k, v in _load(locale).items() if "{0}" in v or "{}" in v}
    assert bad == {}, f"positional placeholders in {locale}: {sorted(bad)}"


@pytest.mark.parametrize("locale", available())
def test_every_plural_key_has_both_forms(locale):
    """`ngettext` picks `.one` or `.other`; a catalogue with only one of them
    falls back to English for half the counts, silently."""
    keys = set(_load(locale))
    stems = {k.rsplit(".", 1)[0] for k in keys if k.endswith((".one", ".other"))}
    for stem in stems:
        assert f"{stem}.one" in keys, f"{locale}: {stem} has no singular"
        assert f"{stem}.other" in keys, f"{locale}: {stem} has no plural"


@pytest.mark.parametrize("locale", available())
def test_every_message_is_interpolatable(locale):
    """Each message formats without raising when given its own placeholders.

    This is the test that would have caught an unescaped brace in a message
    that mentions a JSON object, which is exactly the kind of thing that
    appears in a sentence about a tool call.
    """
    for key, template in _load(locale).items():
        params = dict.fromkeys(placeholders(template), "x")
        try:
            template.format(**params)
        except (KeyError, IndexError, ValueError) as exc:
            pytest.fail(f"{locale}:{key} cannot be formatted: {exc}")


# ---------------------------------------------------------------------------
# Every rule carries its own translation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("locale", OTHERS)
def test_every_shipped_rule_is_translated(shipped, locale):
    """A rule description is the longest thing an agent reads from this
    gateway. A half-translated rule set is a French deployment that explains
    itself in two languages at once."""
    untranslated = [r.id for r in shipped if locale not in r.translations]
    assert untranslated == [], f"no {locale} description: {untranslated}"


def test_an_untranslated_rule_still_explains_itself(shipped):
    """Falling back to English beats falling back to the identifier: a rule
    whose French has not been written yet must still say what it is."""
    rule = shipped[0]
    assert rule.describe("de") == rule.description
    assert rule.describe("fr") != ""


# ---------------------------------------------------------------------------
# Resolution: what language does a given request get answered in?
# ---------------------------------------------------------------------------


def test_the_deployment_decides_the_language_and_a_bad_answer_is_never_fatal():
    """The resolution order is the opposite of a public website's, and right
    for this one: which language an agent is *instructed* in is the operator's
    decision, not a per-call flag a client gets to flip. The header is read
    only when nothing is configured, where it is the best evidence available.

    Nothing here may fail. A typo in a configuration file must not stop a
    gateway from starting, so an unknown locale falls back; a region tag
    resolves to its language; case does not matter; and an unparseable or
    absent header lands on the default rather than raising.
    """
    assert translator("kl").locale == DEFAULT_LOCALE
    assert translator("fr-CA").locale == "fr", "a region should resolve to its language"
    assert translator("FR").locale == "fr"
    assert translator(None).locale == DEFAULT_LOCALE

    assert negotiate(header="fr", configured="en") == "en"
    assert negotiate(header="en", configured="fr") == "fr"

    assert negotiate(header="fr-CA,fr;q=0.9,en;q=0.8") == "fr"
    assert negotiate(header="de,en;q=0.5") == "en", "the first *available* match wins"
    assert negotiate(header="") == DEFAULT_LOCALE
    assert negotiate(header="xx-YY") == DEFAULT_LOCALE


# ---------------------------------------------------------------------------
# What the agent actually receives.
# ---------------------------------------------------------------------------


def test_a_refusal_arrives_in_the_configured_language(shipped):
    """The end-to-end claim, through the real pipeline rather than the
    catalogue: a French deployment refuses in French."""
    english = apply_outbound(command("rm -rf ~"), rules=shipped, locale="en")
    french = apply_outbound(command("rm -rf ~"), rules=shipped, locale="fr")
    assert english.refusal.id == french.refusal.id == "shell.destructive_rm"
    assert "refuses this command" in refusal_message(english.refusal, "en")
    assert "refuse cette commande" in refusal_message(french.refusal, "fr")


def test_the_default_is_still_english(shipped):
    """Deliberate, not lazy: a refusal is read by a model before it reaches a
    person, so the gateway does not quietly decide to instruct in French."""
    refused = apply_outbound(command("rm -rf ~"), rules=shipped)
    assert "This is a decision" in refusal_message(refused.refusal)


def test_a_message_the_catalogue_cannot_serve_degrades_visibly_not_silently():
    """Two ways to ask for something the catalogue cannot give, and neither
    may produce an empty string or an exception.

    A **missing key** is echoed back: an empty string is a bug that ships, and
    a key echoed back is a bug somebody reports. **Missing parameters** return
    the template, braces and all, rather than raising -- because the caller
    that forgets them is in the middle of explaining a refusal, and an
    exception there replaces a guardrail's explanation with a stack trace.
    """
    assert Translator(locale="en").gettext("no.such.key") == "no.such.key"

    key = "payments.refusal"
    assert "{problems}" in translator("en")(key)
    assert "{problems}" not in translator("en")(key, problems="no mandate")


# ---------------------------------------------------------------------------
# The catalogue is a file somebody has to maintain.
# ---------------------------------------------------------------------------


def test_the_catalogues_are_committed_and_readable():
    """They ship inside the package: a deployment is a file copy, and a
    gateway that cannot find its own words is one that starts and then says
    `deps.undeclared` to an agent."""
    for locale in available():
        path = LOCALE_DIR / f"{locale}.yaml"
        assert path.is_file(), f"{path} is missing"
        assert _load(locale), f"{path} parsed to nothing"


def test_log_lines_were_deliberately_left_alone():
    """Not an oversight, a decision -- a log that changes language with a
    configuration file is a log nobody can grep. If this ever changes, this
    test is the place the reasoning was written down."""
    source = (ROOT / "ai_bunker" / "gateway.py").read_text(encoding="utf-8")
    assert "osh.warning" in source
    assert "[gateway]" in source
