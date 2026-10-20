"""The rule set as a specification a non-programmer can read and approve.

Why
---
Every rule already carries the cases it must catch and the cases it must leave
alone. That is behaviour-driven specification -- it is just written in YAML,
inside a regular expression's neighbourhood, where the person who most needs
to approve it cannot read it. A security officer signing off on what an agent
is allowed to run should not have to parse `(?:api[_-]?key|secret|token)`.

So this renders the same thing as Gherkin, and runs it back. Two directions,
and the second is the one that earns its keep:

* **Export** turns the shipped rules into `.feature` files. Nothing new is
  asserted; it is the YAML, legible.
* **Run** executes every scenario in a `.feature` against the real engine,
  including scenarios **nobody generated**. That is the part that matters: a
  reviewer writes a case in plain language, and the engine must satisfy it.
  A hand-written scenario that fails is a specification the implementation
  does not meet, which is exactly what a specification is for.

The vocabulary is deliberately tiny -- two Givens, one When, four Thens --
because a step vocabulary that grows becomes a programming language with no
type checker. These six cover the rule engine's two scopes, and nothing else
is accepted.

    Feature: Secrets must never enter the context window

      Scenario: a credential in a tool result is redacted
        Given a tool result containing "api_key = sk_live_8Kq2mZx9PvN3wR7t"
        When the gateway screens it
        Then the rule global.generic_secret fires
        And the text is redacted

      Scenario: a placeholder is left alone
        Given a tool result containing "api_key = REPLACE_ME_WITH_YOUR_KEY"
        When the gateway screens it
        Then no rule fires

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ai_bunker.rules import Rule, screen_command, screen_output

#: The whole step vocabulary. Anything else is a parse error rather than a
#: silently skipped line: a scenario that looks like it ran and did not is
#: worse than one that refuses to load.
GIVEN_OUTPUT = re.compile(r'^a tool result containing "(?P<text>.*)"$')
GIVEN_COMMAND = re.compile(r'^the model asks to run "(?P<text>.*)"$')
THEN_FIRES = re.compile(r"^the rule (?P<rule>[\w.]+) fires$")
THEN_NO_RULE = re.compile(r"^no rule fires$")
THEN_REDACTED = re.compile(r"^the text is redacted$")
THEN_REFUSED = re.compile(r"^it is refused$")
THEN_ALLOWED = re.compile(r"^it is allowed$")


@dataclass
class Scenario:
    name: str
    feature: str
    scope: str = ""
    text: str = ""
    expect_rules: list[str] = field(default_factory=list)
    expect_none: bool = False
    expect_redacted: bool = False
    expect_refused: bool = False
    expect_allowed: bool = False
    line: int = 0


@dataclass
class Result:
    scenario: Scenario
    passed: bool
    detail: str = ""


def _escape(text: str) -> str:
    """Gherkin step arguments are quoted; a literal quote would end them."""
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    # A character with no glyph has to be written down, or a specification
    # about hidden text is a specification nobody can read. This is the
    # scenario that made the point: `Given a tool result containing "Ig?nore"`
    # where `?` is a zero-width space looks exactly like `"Ignore"` on screen,
    # so a reviewer approving it has approved something invisible.
    out = []
    for char in text:
        if char.isprintable() or char == "\t":
            out.append(char)
        elif ord(char) > 0xFFFF:
            out.append(f"\\U{ord(char):08x}")
        else:
            out.append(f"\\u{ord(char):04x}")
    return "".join(out)


def _unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            # Four digits for the basic plane, eight for everything above it:
            # an emoji and a Unicode tag character both live up there, and
            # both turn up in these scenarios.
            width = {"u": 4, "U": 8}.get(nxt)
            if width and i + 2 + width <= len(text):
                try:
                    out.append(chr(int(text[i + 2 : i + 2 + width], 16)))
                    i += 2 + width
                    continue
                except (ValueError, OverflowError):
                    pass  # not a hex escape after all; fall through
            out.append({"n": "\n", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def export(rules: list[Rule], *, source: str = "") -> str:
    """Render one rules file as a .feature.

    Grouped by source file because that is how the rules are authored and
    reviewed: `global.yaml` is one subject, and a reviewer approves a subject
    rather than a scattering of patterns.
    """
    chosen = [r for r in rules if not source or r.source == source]
    title = (source or "rules").removesuffix(".yaml").replace("_", " ").title()

    lines = [
        f"Feature: {title}",
        "",
        "  Generated from the shipped rules by `ai-bunker spec --export`.",
        "  Scenarios written by hand below the generated ones are run too, and",
        "  are the ones that can fail: they assert behaviour nobody derived",
        "  from the implementation.",
        "",
    ]

    for rule in chosen:
        given = "the model asks to run" if rule.scope == "command" else "a tool result containing"
        lines += [f"  # {rule.id} -- {rule.severity}", f"  # {rule.description}", ""]

        for case in rule.should_match:
            lines += [
                f"  Scenario: {rule.id} catches {_summarise(case)}",
                f'    Given {given} "{_escape(case)}"',
                "    When the gateway screens it",
                f"    Then the rule {rule.id} fires",
            ]
            # Only a BLOCKER refuses. A WARNING on a command fires and lets
            # it through, which is a different promise and has to read as one
            # -- `shell.credential_read` is a WARNING, and generating "it is
            # refused" for it made three scenarios fail against the engine
            # that implements them.
            if rule.scope == "command":
                if rule.severity == "BLOCKER":
                    lines.append("    And it is refused")
                else:
                    lines.append("    And it is allowed")
            elif rule.redact:
                lines.append("    And the text is redacted")
            lines.append("")

        for case in rule.should_not_match:
            lines += [
                f"  Scenario: {rule.id} leaves {_summarise(case)} alone",
                f'    Given {given} "{_escape(case)}"',
                "    When the gateway screens it",
                "    Then no rule fires" if rule.scope == "output" else "    Then it is allowed",
                "",
            ]

    return "\n".join(lines).rstrip() + "\n"


def _summarise(case: str) -> str:
    """A scenario title a human can scan, from a case that may be long."""
    flat = " ".join(case.split())
    return (flat[:48] + "...") if len(flat) > 48 else flat


def parse(text: str) -> list[Scenario]:
    """Parse the supported subset. Unknown steps raise rather than being skipped."""
    scenarios: list[Scenario] = []
    feature = ""
    current: Scenario | None = None

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("Feature:"):
            feature = line[len("Feature:") :].strip()
            continue
        if line.startswith(("Scenario:", "Example:")):
            current = Scenario(name=line.split(":", 1)[1].strip(), feature=feature, line=number)
            scenarios.append(current)
            continue
        if current is None:
            # Narrative under Feature: is free text, by the Gherkin grammar.
            continue

        keyword, _, rest = line.partition(" ")
        rest = rest.strip()
        if keyword in {"And", "But"}:
            keyword = (current.scope and "Then") or "Given"
            keyword = "Then" if current.scope else "Given"

        if keyword == "Given":
            if m := GIVEN_OUTPUT.match(rest):
                current.scope, current.text = "output", _unescape(m["text"])
            elif m := GIVEN_COMMAND.match(rest):
                current.scope, current.text = "command", _unescape(m["text"])
            else:
                raise ValueError(f"line {number}: unsupported Given: {rest!r}")
        elif keyword == "When":
            if rest != "the gateway screens it":
                raise ValueError(f"line {number}: unsupported When: {rest!r}")
        elif keyword == "Then":
            if m := THEN_FIRES.match(rest):
                current.expect_rules.append(m["rule"])
            elif THEN_NO_RULE.match(rest):
                current.expect_none = True
            elif THEN_REDACTED.match(rest):
                current.expect_redacted = True
            elif THEN_REFUSED.match(rest):
                current.expect_refused = True
            elif THEN_ALLOWED.match(rest):
                current.expect_allowed = True
            else:
                raise ValueError(f"line {number}: unsupported Then: {rest!r}")
        else:
            raise ValueError(f"line {number}: unsupported step: {line!r}")

    return scenarios


def run(scenarios: list[Scenario], rules: list[Rule]) -> list[Result]:
    """Execute scenarios against the real engine."""
    results: list[Result] = []
    for scenario in scenarios:
        if not scenario.scope:
            results.append(Result(scenario, False, "no Given step"))
            continue

        if scenario.scope == "command":
            refusal, violations = screen_command(
                scenario.text, [r for r in rules if r.scope == "command"]
            )
            fired = [v.rule.id for v in violations]
            refused = refusal is not None
            redacted = False
        else:
            screened = screen_output(scenario.text, [r for r in rules if r.scope == "output"])
            fired = [v.rule.id for v in screened.violations]
            refused = False
            redacted = screened.text != scenario.text

        problems = []
        for expected in scenario.expect_rules:
            if expected not in fired:
                problems.append(f"expected {expected} to fire; fired: {fired or 'nothing'}")
        if scenario.expect_none and fired:
            problems.append(f"expected nothing to fire; fired: {fired}")
        if scenario.expect_redacted and not redacted:
            problems.append("expected the text to be redacted; it was unchanged")
        if scenario.expect_refused and not refused:
            problems.append("expected a refusal; the command was allowed")
        if scenario.expect_allowed and refused:
            problems.append("expected it to be allowed; it was refused")

        results.append(Result(scenario, not problems, "; ".join(problems)))
    return results


def load(directory: str | Path) -> list[Scenario]:
    """Every scenario in every .feature under ``directory``."""
    out: list[Scenario] = []
    for path in sorted(Path(directory).rglob("*.feature")):
        try:
            out += parse(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
    return out
