"""Publish the charter as an Agent Skill, so any client can read it.

Why this exists
---------------
The charter already solves the problem Agent Skills solves, and arrived at the
same shape independently: an index small enough to sit in every prompt, with
the pages behind it read only when a task calls for one. The specification at
agentskills.io calls that progressive disclosure and gives it three stages --
metadata at startup, the ``SKILL.md`` body on activation, bundled files on
demand. Those are this project's index, operating rules, and pages, in order.

Where they differ is reach. The gateway serves the charter to anything
speaking OpenAI, which is the right answer when a team runs a gateway. A team
that has not deployed one yet, or an agent running offline, gets nothing. The
Agent Skills format is read natively by Claude Code, OpenCode, Cursor, Goose,
Amp, Roo, Codex, Copilot and Gemini CLI, so emitting one costs a few hundred
lines and makes the same charter portable to clients this project will never
write a kit for.

This is deliberately an **export**, not a second source of truth. The gateway
remains the enforcing copy; a skill on disk is a convenience that can drift,
and `fingerprint` in the metadata is what lets anyone notice that it has.

Where to write it
-----------------
There is no mandated location, and the clients disagree. OpenCode documents
reading ``.opencode/skills/``, ``.agents/skills/`` **and**
``.claude/skills/`` -- the last one explicitly as "Claude-compatible". So the
default here is ``.claude/skills/``: one directory, read by both of the
clients this project is most often asked about, without writing the files
twice.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import os_helper as osh

from ai_bunker import __version__
from ai_bunker.charter import Charter

#: The specification's rules for `name`, as one expression: lowercase
#: alphanumerics and hyphens, 1-64 characters, no leading, trailing or
#: doubled hyphen.
NAME_PATTERN = re.compile(r"^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$")

#: Specification limits, quoted here so a violation names the real constraint.
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_NAME = 64

#: "Keep your main SKILL.md under 500 lines." A recommendation, not a limit,
#: so exceeding it is a warning rather than a refusal.
RECOMMENDED_BODY_LINES = 500

#: Where each client looks, from their own documentation. `claude` is the
#: default because OpenCode reads it too, so one copy serves both.
CLIENT_PATHS: dict[str, str] = {
    "claude": ".claude/skills",
    "opencode": ".opencode/skills",
    "agents": ".agents/skills",
}


@dataclass
class Skill:
    """One Agent Skill, in memory, before anything touches the disk."""

    name: str
    description: str
    body: str
    references: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    license: str = ""
    compatibility: str = ""

    def frontmatter(self) -> str:
        """The YAML block, written by hand rather than dumped.

        A dumper would quote and order these to its own taste, and this file
        is read by other people's parsers; the specification's examples are
        the format to match.
        """
        lines = [
            "---",
            f"name: {self.name}",
            f"description: {_fold(self.description)}",
        ]
        if self.license:
            lines.append(f"license: {self.license}")
        if self.compatibility:
            lines.append(f"compatibility: {_fold(self.compatibility)}")
        if self.metadata:
            lines.append("metadata:")
            lines += [f'  {k}: "{v}"' for k, v in self.metadata.items()]
        lines.append("---")
        return "\n".join(lines)

    def skill_md(self) -> str:
        return f"{self.frontmatter()}\n\n{self.body.rstrip()}\n"


def _fold(text: str) -> str:
    """One line, no newlines: a bare YAML scalar cannot carry them."""
    return " ".join(text.split())


def _reference_name(ref: str) -> str:
    """Turn a charter page reference into a flat reference filename.

    The specification asks for references one level deep, so `python/10_style`
    cannot keep its directory. Flattening with a hyphen keeps the pack visible
    in the filename, which matters: `tests.md` alone says nothing about which
    language's tests it describes.
    """
    stem = ref[:-3] if ref.endswith(".md") else ref
    return stem.replace("/", "-").replace(" ", "-") + ".md"


def validate(skill: Skill) -> list[str]:
    """Every way this skill breaks the specification, in reading order.

    Returns findings rather than raising, because a caller writing several
    skills wants all of them at once, and because the CLI reports them as a
    list. An empty list means the skill is valid, not that it is good.
    """
    problems: list[str] = []

    if not NAME_PATTERN.match(skill.name):
        problems.append(
            f"name {skill.name!r} is not valid: 1-{MAX_NAME} characters, lowercase "
            "letters, digits and single hyphens, not leading or trailing"
        )
    if not skill.description.strip():
        problems.append("description is empty; it is required")
    elif len(skill.description) > MAX_DESCRIPTION:
        problems.append(
            f"description is {len(skill.description)} characters; the limit is {MAX_DESCRIPTION}"
        )
    if len(skill.compatibility) > MAX_COMPATIBILITY:
        problems.append(
            f"compatibility is {len(skill.compatibility)} characters; "
            f"the limit is {MAX_COMPATIBILITY}"
        )
    if "\n" in skill.name or "\n" in skill.description:
        problems.append("name and description must be single-line scalars")
    for filename in skill.references:
        if "/" in filename.strip("/"):
            problems.append(f"reference {filename!r} is more than one level deep")
    return problems


def warnings(skill: Skill) -> list[str]:
    """Things the specification recommends rather than requires."""
    out: list[str] = []
    lines = skill.body.count("\n") + 1
    if lines > RECOMMENDED_BODY_LINES:
        out.append(
            f"SKILL.md body is {lines} lines; the specification recommends under "
            f"{RECOMMENDED_BODY_LINES}, with the detail in references/"
        )
    if len(skill.description) < 40:
        out.append(
            "description is very short; it should say what the skill does AND "
            "when to use it, or agents will not know when to load it"
        )
    return out


def build_skill(
    charter: Charter,
    *,
    name: str = "team-charter",
    description: str = "",
    license_: str = "",
) -> Skill:
    """Render a loaded charter as an Agent Skill.

    The body is the operating rules followed by an index of the pages, which
    is the same two-part prompt the gateway injects -- with the page
    references rewritten as relative paths, because that is how a client
    reaches them here instead of asking an endpoint.
    """
    references = {
        _reference_name(page.ref): page.path.read_text(encoding="utf-8") for page in charter.pages
    }

    packs = charter.packs
    if not description:
        subjects = ", ".join(sorted(packs)) or "this repository"
        description = (
            "The operating rules and coding standards for this repository, "
            f"covering {subjects}. Use when writing, reviewing or refactoring code "
            "here, when deciding how to name or structure something, or when the "
            "user asks what the team's conventions are. Read the matching page "
            "under references/ before answering a question it covers."
        )

    lines: list[str] = []
    if charter.operating_rules.strip():
        lines += [charter.operating_rules.strip(), ""]

    lines += [
        "## Pages",
        "",
        "Read only the page a task calls for. Each is a few hundred words; "
        "loading all of them defeats the point.",
        "",
    ]
    for pack, pages in packs.items():
        lines.append(f"**{pack}**")
        for page in pages:
            lines.append(f"- [`{page.ref}`](references/{_reference_name(page.ref)})")
        lines.append("")

    return Skill(
        name=name,
        description=description,
        body="\n".join(lines).rstrip(),
        references=references,
        metadata={
            # Prefixed, as the specification advises, so these cannot collide
            # with another tool's metadata. The fingerprint is the useful one:
            # it is what tells a reader whether this copy still matches the
            # charter the gateway is enforcing.
            "ai-bunker.charter-fingerprint": charter.fingerprint,
            "ai-bunker.version": __version__,
            "ai-bunker.pages": str(len(charter.pages)),
        },
        license=license_,
    )


def write_skill(skill: Skill, out_dir: str | Path, *, force: bool = False) -> list[Path]:
    """Write the skill under ``out_dir/<name>/``, and return what was written.

    The directory is named for the skill because the specification requires
    `name` to match its parent directory; getting that wrong produces a skill
    some clients silently ignore, which is worse than one that fails loudly.
    """
    problems = validate(skill)
    osh.check(not problems, "The skill does not meet the specification: " + "; ".join(problems))

    root = Path(out_dir) / skill.name
    files = {root / "SKILL.md": skill.skill_md()}
    for filename, content in skill.references.items():
        files[root / "references" / filename] = content

    if not force:
        existing = sorted(p for p in files if p.exists())
        osh.check(
            not existing,
            f"{len(existing)} file(s) already exist, starting with {existing[0] if existing else ''}. "
            "Pass force=True to replace them.",
        )

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return sorted(files)


def read_skill(directory: str | Path) -> Skill:
    """Parse a skill from disk, for validating one this project did not write."""
    root = Path(directory)
    source = (root / "SKILL.md").read_text(encoding="utf-8")
    osh.check(source.startswith("---"), f"{root}/SKILL.md has no YAML frontmatter")

    _, _, rest = source.partition("---")
    block, _, body = rest.partition("\n---")
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if line.startswith(("  ", "\t")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    references = {}
    if (root / "references").is_dir():
        references = {
            p.name: p.read_text(encoding="utf-8") for p in sorted((root / "references").glob("*"))
        }
    return Skill(
        name=fields.get("name", ""),
        description=fields.get("description", ""),
        body=body.strip(),
        references=references,
        license=fields.get("license", ""),
        compatibility=fields.get("compatibility", ""),
    )
