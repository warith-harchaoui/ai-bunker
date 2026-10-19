"""Refuse to install what the project never declared.

The threat
----------
Models invent package names. An attacker who registers an invented name owns
code execution on every machine whose agent installs it -- the attack is
called slopsquatting, and it needs no compromise of anything, only a plausible
hallucination and a registry account.

The usual defence is to ask a registry whether a package is real. That is the
wrong answer here twice over. It puts a network call on the enforcement path
of a tool whose claim is that nothing leaves the network, and it does not
work: the malicious package **is** real, registered precisely so the check
passes.

The defence that works offline
------------------------------
A project already states what it depends on, in files kept under version
control and changed by humans in reviewed commits. Anything else is either a
hallucination or a dependency nobody approved, and both should stop. So the
question is not "does this package exist" but "did this project ask for it",
which is answered by reading the repository and needs no network at all.

The cost is honest and worth stating: adding a genuine new dependency is
refused too, until a human writes it into the manifest. That is the intended
behaviour, not a side effect -- choosing a dependency is a decision with a
licence, a maintainer and a supply chain attached, and it is not an agent's
to make mid-task.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import os_helper as osh

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from ai_bunker.rules import Rule

#: Manifests read, in no particular order. Lock files are included because a
#: transitive dependency is still one the project resolved and committed.
MANIFESTS = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.cfg",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
)

#: Installers, and where the package names start. `install` and `add` both
#: appear; `-r requirements.txt` and flags are skipped by the parser.
INSTALLERS = re.compile(
    r"\b(?P<tool>pip3?|uv|pipx|npm|pnpm|yarn|bun|cargo|go|gem|poetry|conda)\b"
    r"[^\n]{0,40}?\b(?P<verb>install|add|get)\b",
    re.IGNORECASE,
)

#: A package name, conservatively. Extras, versions and URLs are stripped by
#: `_normalise` rather than matched here.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/-]{0,96}$")


@dataclass
class Check:
    """What one command would install, and what the project never asked for."""

    tool: str = ""
    requested: list[str] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.undeclared


def _normalise(name: str) -> str:
    """`Flask[async]>=2.0` and `flask` are the same dependency.

    PyPI treats `-`, `_` and `.` as equivalent and is case-insensitive, so a
    manifest saying `typing_extensions` must answer for `typing-extensions`.
    npm scopes keep their `@scope/` prefix, which is part of the identity.
    """
    name = name.strip().strip("'\"")
    name = re.split(r"[\[<>=!~;]", name, maxsplit=1)[0]
    name = name.split("@")[0] if not name.startswith("@") else name
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def declared(root: str | Path) -> set[str]:
    """Every dependency this project states, from every manifest it has.

    Deliberately crude: names are harvested with patterns rather than by
    parsing each format properly. A false *positive* here -- treating
    something as declared when it is not -- weakens the check, so the
    harvesting is narrow; a false negative is caught by the operator, who adds
    the name to a manifest where it belonged anyway.
    """
    found: set[str] = set()
    base = Path(root)

    for name in MANIFESTS:
        path = base / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if name == "package.json" or name.endswith(".json"):
            found |= _from_json(text)
        elif name.startswith("requirements"):
            found |= _from_requirements(text)
        elif name == "go.mod":
            found |= {_normalise(m) for m in re.findall(r"^\s*([\w.\-/]+)\s+v\d", text, re.M)}
        else:
            found |= _from_lines(text)

    found.discard("")
    return found


def _from_json(text: str) -> set[str]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return set()
    out: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            out |= {_normalise(k) for k in block}
    # package-lock.json: every resolved path, which is the transitive set.
    packages = data.get("packages")
    if isinstance(packages, dict):
        for path in packages:
            if path.startswith("node_modules/"):
                out.add(_normalise(path.split("node_modules/")[-1]))
    return out


#: TOML tables whose keys or values are dependencies. Anything outside these
#: is configuration, and harvesting it would put `addopts` and `all` in the
#: declared set -- which does not merely add noise, it *weakens* the check, by
#: making a name count as approved when nobody approved it.
DEPENDENCY_TABLES = (
    "project.dependencies",
    "project.optional-dependencies",
    "build-system.requires",
    "tool.poetry.dependencies",
    "tool.poetry.dev-dependencies",
    "tool.poetry.group.dev.dependencies",
    "dependencies",
    "dev-dependencies",
    "build-dependencies",
    "packages",
    "dev-packages",
    "package",
)


def _from_lines(text: str) -> set[str]:
    """Harvest names from a line-oriented or TOML-ish manifest.

    Section-aware rather than greedy. A real TOML parser would be better and
    is not available on every supported version, so this tracks the current
    table by hand and only reads inside the ones that hold dependencies.
    """
    out: set[str] = set()
    table = ""
    in_array = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith("#") else ""
        if not line:
            continue

        if line.startswith("[") and line.endswith("]"):
            table = line.strip("[]").strip().strip('"')
            in_array = False
            continue

        relevant = any(
            table == t or table.startswith(t + ".") or table.endswith("." + t)
            for t in DEPENDENCY_TABLES
        )

        # `dependencies = [` opens an array that continues over later lines.
        if match := re.match(r"^([A-Za-z0-9_.-]+)\s*=\s*\[", line):
            in_array = match.group(1).strip('"').lower() in {
                "dependencies",
                "requires",
                "dev-dependencies",
                "optional-dependencies",
            }
            relevant = relevant or in_array
            line = line.split("[", 1)[1]
        elif line.startswith("]"):
            in_array = False
            continue

        if not (relevant or in_array):
            continue

        for candidate in re.findall(r'["\']([^"\']{1,140})["\']', line):
            name = _normalise(candidate)
            if name and NAME.match(name):
                out.add(name)
        # `flask = "^2.0"` inside a poetry dependency table: the KEY is the name.
        if relevant and (match := re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]{0,96})\s*=", line)):
            name = _normalise(match.group(1))
            if name not in {"version", "python", "extras", "optional", "markers", "requires"}:
                out.add(name)

    return out


def _from_requirements(text: str) -> set[str]:
    """A requirements.txt: one dependency per line, flags and includes aside."""
    out: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = _normalise(line)
        if name and NAME.match(name):
            out.add(name)
    return out


def packages_in(command: str) -> tuple[str, list[str]]:
    """The installer used and the package names it is being asked to install.

    Flags, requirement files and anything that is not a bare name are skipped:
    `pip install -r requirements.txt` installs what the project declared by
    definition, and `pip install .` installs the project itself.
    """
    match = INSTALLERS.search(command)
    if not match:
        return "", []

    tail = command[match.end() :]
    names: list[str] = []
    skip_next = False
    for token in tail.split():
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            # Flags that take a value, so the value is not read as a package.
            skip_next = token in {
                "-r",
                "--requirement",
                "-c",
                "--constraint",
                "-t",
                "--target",
                "-e",
                "--editable",
                "--index-url",
                "-i",
                "--extra-index-url",
            }
            continue
        if token in {"&&", "||", ";", "|"}:
            break
        if (
            token.startswith((".", "/", "~"))
            or "://" in token
            or token.endswith((".txt", ".whl", ".tar.gz"))
        ):
            continue
        normalised = _normalise(token)
        if normalised and NAME.match(normalised):
            names.append(normalised)
    return match.group("tool").lower(), names


def check(command: str, root: str | Path = ".") -> Check:
    """Would this command install something the project never declared?"""
    tool, requested = packages_in(command)
    if not requested:
        return Check(tool=tool)
    known = declared(root)
    return Check(
        tool=tool,
        requested=requested,
        undeclared=[p for p in requested if p not in known],
    )


def refusal_message(result: Check) -> str:
    """What to tell a model that just tried to install an unknown package."""
    names = ", ".join(result.undeclared)
    plural = "packages are" if len(result.undeclared) > 1 else "package is"
    return (
        f"This {plural} not declared anywhere in the project: {names}. "
        "Either the name is wrong -- models invent package names, and an "
        "attacker who registers an invented one owns this machine -- or it is "
        "a new dependency, which is a decision for a human to write into a "
        "manifest and commit, not one to take mid-task. Check the spelling "
        "against the real package, then ask."
    )


def warn_if_unreadable(root: str | Path) -> None:
    """Say so when a project states no dependencies at all.

    A repository with no manifest produces an empty declared set, which would
    refuse every install and look like the check working. It is not; it is the
    check having nothing to compare against.
    """
    if not declared(root):
        osh.warning(
            f"[deps] no dependency manifest found under {root}. Every install "
            "would be refused, which is not a guardrail -- it is a check with "
            "nothing to check against. Disable it, or point it at the repository."
        )


def as_rule(result: Check) -> Rule:
    """Express a failed check as a Rule, so nothing downstream needs to know.

    The audit log, the refusal sent back as a tool result, and the dashboard's
    decision table all speak in rules. Synthesising one here means this check
    joins them without a parallel path -- and a parallel path is how two
    enforcement mechanisms end up disagreeing about what was refused.
    """
    from ai_bunker.rules import Rule

    return Rule(
        id="deps.undeclared_package",
        severity="BLOCKER",
        scope="command",
        description=refusal_message(result),
        pattern=re.compile(r"(?!)"),  # never matches: this rule is decided in code
        redact=False,
        replacement="",
        source="dependencies.py",
    )
