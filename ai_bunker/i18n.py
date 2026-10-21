"""The gateway's own words, in the reader's language.

Why this exists
---------------
The documentation has been bilingual from the start. The *runtime* never was:
every refusal an agent received, every rule description, every budget warning
was English, on a tool written for French-speaking teams. The rules themselves
already knew better -- ``injection.override_instructions`` carries a French
branch because an injection does not have to be written in the language the
rules were written in, and that was found by probing, not by reasoning. The
same argument applies to what the gateway says back.

The shape is gettext's
----------------------
Call sites look like the standard library's, because they should: ``_()`` for
a message, ``ngettext()`` when a count changes the wording, named placeholders
rather than positional ones, and a fallback that returns something usable when
a translation is missing. If this project ever wants real ``.po`` files and a
translator's toolchain, the call sites do not change -- only what sits behind
them.

What sits behind them is a YAML file rather than a compiled ``.mo``, and that
is the same decision as committing ``css/app.css``: deployment here is a file
upload, and a binary catalogue would put a compilation step between an
operator and a corrected sentence. A catalogue that can be read in a diff and
fixed in a text editor is worth more to this project than one a standard
toolchain can process.

Keys are symbolic, not the English text
---------------------------------------
gettext uses the source string as the key, which is elegant for short labels
and unusable here: several of these messages are sixty words of careful
phrasing, and nobody wants that as an identifier in a diff, a grep or a stack
trace. So the keys are symbolic (``deps.undeclared``) and English is one
catalogue among the others. The risk that introduces -- a key that exists in
one language and not another, or whose placeholders disagree -- is what
``tests/test_i18n.py`` exists to make impossible.

What is deliberately NOT translated
-----------------------------------
**Log lines.** ``osh.warning("[gateway] ...")`` stays English in every locale.
A log is grepped, pasted into an issue and read by whoever is awake; a log
that changes language with a configuration file is a log nobody can search.

**Rule identifiers, configuration keys, command names.** They are names.

The trade on agent-facing text, stated rather than hidden
----------------------------------------------------------
A refusal is read by a *model* before it reaches a person. Changing its
language changes what the model reads, and instruction-following is not
uniformly strong across languages. So the default stays English and a
deployment opts in, the same way it opts into a premium route: the gateway
does not quietly decide that an agent should be instructed in French.

The dashboard inverts that rule, on purpose
-------------------------------------------
The dashboard *is* translated -- its strings are the ``gui.`` keys in these
catalogues, and ``tests/test_gui.py`` checks both directions, so a string
nobody shows and a label nobody translated both fail. But it resolves its
language the other way round: ``?lang=`` first, then the stored click, then
``navigator.language``, and only then the configuration.

The two rules disagree because the readers do. Agent-facing text is read by a
model whose behaviour the operator is accountable for, so the operator
chooses. The dashboard is read by a person who is standing there, and the
language a person reads is not a deployment decision. That inversion must not
leak back the other way: the toggle changes what that page says and nothing
about the language an agent is instructed in.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

#: Where the catalogues live, one file per locale.
LOCALE_DIR = Path(__file__).resolve().parent / "locales"

#: The locale everything falls back to, and the one the catalogue is authored
#: in. Also the default for agent-facing text -- see the module docstring.
DEFAULT_LOCALE = "en"

#: Named placeholders, which is the only kind these messages use. Positional
#: ones cannot be reordered by a translator whose language puts the subject
#: somewhere else, so they are rejected by the test suite rather than merely
#: discouraged here.
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)[^}]*\}")


def available() -> tuple[str, ...]:
    """Every locale with a catalogue, with the default first."""
    found = sorted(p.stem for p in LOCALE_DIR.glob("*.yaml"))
    return tuple([DEFAULT_LOCALE] + [f for f in found if f != DEFAULT_LOCALE])


@lru_cache(maxsize=8)
def _load(locale: str) -> dict[str, str]:
    """One catalogue, flattened to dotted keys.

    Nested in the file because that is how a human wants to read it, flat in
    memory because that is how a call site wants to ask for it.
    """
    path = LOCALE_DIR / f"{locale}.yaml"
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        osh.warning(f"[i18n] {path.name} is not readable YAML and is being ignored: {exc}")
        return {}

    flat: dict[str, str] = {}

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(node, str):
            flat[prefix] = node

    walk(raw, "")
    return flat


@dataclass
class Translator:
    """One locale, resolved once and reused.

    Attributes
    ----------
    locale : str
        What was asked for, which may not be what is available.
    """

    locale: str = DEFAULT_LOCALE
    _messages: dict[str, str] = field(default_factory=dict, repr=False)
    _fallback: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._messages = _load(self.locale)
        self._fallback = _load(DEFAULT_LOCALE) if self.locale != DEFAULT_LOCALE else {}

    def gettext(self, key: str, /, **params: Any) -> str:
        """The message for ``key``, interpolated with named parameters.

        Three fallbacks, in order: the requested locale, the default locale,
        then the key itself. The last one is visible on purpose -- a message
        that silently became an empty string is a bug that ships, and a
        message that reads ``deps.undeclared`` is a bug somebody reports.
        """
        template = self._messages.get(key) or self._fallback.get(key)
        if template is None:
            osh.warning(f"[i18n] no message for {key!r} in {self.locale!r} or {DEFAULT_LOCALE!r}.")
            return key
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError) as exc:
            # A catalogue whose placeholders disagree with the call site. The
            # test suite makes this unreachable; this is what happens anyway,
            # because a gateway must not raise while explaining a refusal.
            osh.warning(f"[i18n] {key!r} in {self.locale!r} has a placeholder error: {exc}")
            return self._fallback.get(key, template)

    #: The conventional spelling at a call site.
    __call__ = gettext

    def ngettext(self, key: str, count: int, /, **params: Any) -> str:
        """Singular or plural, chosen by ``count``.

        The catalogue holds ``key.one`` and ``key.other``, which covers
        English and French. A language with a richer plural system would need
        the gettext plural-forms expression, and this is the point at which
        this module should be replaced rather than extended.
        """
        suffix = "one" if abs(count) == 1 else "other"
        return self.gettext(f"{key}.{suffix}", count=count, **params)

    def has(self, key: str) -> bool:
        return key in self._messages or key in self._fallback


@lru_cache(maxsize=8)
def translator(locale: str | None = None) -> Translator:
    """A translator for ``locale``, cached.

    An unknown locale resolves to the default rather than failing: a typo in a
    configuration file should not stop a gateway from starting, and the
    warning says which locales exist.
    """
    wanted = (locale or DEFAULT_LOCALE).strip().lower()
    wanted = wanted.replace("_", "-").split("-")[0] or DEFAULT_LOCALE
    if wanted not in available():
        if locale:
            osh.warning(
                f"[i18n] locale {locale!r} has no catalogue; using {DEFAULT_LOCALE!r}. "
                f"Available: {', '.join(available())}."
            )
        wanted = DEFAULT_LOCALE
    return Translator(locale=wanted)


def negotiate(header: str = "", configured: str = "") -> str:
    """The locale to answer in, from the deployment and the request.

    Configuration wins over the request. That is the opposite of a public
    website and right for this one: the language of a refusal is a property
    of the deployment -- the operator decided which language their agents are
    instructed in -- not something a client gets to flip per call.

    The header is read only when nothing is configured, and it is the standard
    ``Accept-Language`` grammar: a comma-separated list with optional quality
    values, best first.
    """
    if configured.strip():
        return translator(configured).locale
    for part in header.split(","):
        tag = part.split(";")[0].strip().replace("_", "-").split("-")[0].lower()
        if tag and tag in available():
            return tag
    return DEFAULT_LOCALE


def missing(locale: str) -> tuple[list[str], list[str]]:
    """Keys the default has and ``locale`` lacks, and the reverse.

    Used by the test suite and by `ai-bunker doctor`, because a catalogue that
    has quietly fallen behind is the normal failure mode of any translation
    and the only one worth automating against.
    """
    base = set(_load(DEFAULT_LOCALE))
    other = set(_load(locale))
    return sorted(base - other), sorted(other - base)


def placeholders(template: str) -> set[str]:
    """The named placeholders a message expects."""
    return set(PLACEHOLDER.findall(template))
