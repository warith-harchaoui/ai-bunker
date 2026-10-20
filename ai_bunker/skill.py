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

import hashlib
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
    metadata: dict[str, str] = {}
    folded: str | None = None
    for line in block.splitlines():
        indented = line.startswith(("  ", "\t"))
        if indented and folded == "metadata":
            # A nested mapping, which this parser used to drop on the floor.
            # It matters because that is where another project puts the facts
            # about a skill that are not prose -- skore-skills carries
            # `role` and `modelTier` there -- and dropping them meant an
            # imported skill arrived stripped of everything machine-readable.
            key, _, value = line.partition(":")
            if value.strip():
                metadata[key.strip()] = value.strip().strip("\"'")
            continue
        if indented or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        folded = key if not value.strip() or value.strip() in {">", "|", ">-", "|-"} else None
        fields[key] = value.strip()

    references = {}
    if (root / "references").is_dir():
        references = {
            p.name: p.read_text(encoding="utf-8") for p in sorted((root / "references").glob("*"))
        }
    return Skill(
        name=fields.get("name", ""),
        description=_unfold(block, "description") or fields.get("description", ""),
        body=body.strip(),
        references=references,
        metadata=metadata,
        license=fields.get("license", ""),
        compatibility=fields.get("compatibility", ""),
    )


def _unfold(block: str, key: str) -> str:
    """Recover a folded scalar (``description: >``) as one line.

    Written because the skills this project did not write use the folded form
    for `description` -- it is the only field long enough to need it -- and
    reading only the text after the colon returned the fold marker instead of
    the description. A skill whose description is `>` passes every length
    check and tells an agent nothing.
    """
    lines = block.splitlines()
    for index, line in enumerate(lines):
        head, _, value = line.partition(":")
        if head.strip() != key or value.strip() not in {">", "|", ">-", "|-"}:
            continue
        collected: list[str] = []
        for following in lines[index + 1 :]:
            if following.strip() and not following.startswith(("  ", "\t")):
                break
            collected.append(following.strip())
        return " ".join(part for part in collected if part).strip()
    return ""


# ---------------------------------------------------------------------------
# The other direction: a skills tree someone else wrote, read in as a charter
# pack.
#
# `build_skill` exports a charter so clients with no kit can read it. This is
# the inverse, and it exists because the export already proved the formats
# line up: an Agent Skill is a description plus a body plus bundled
# references, and a charter pack is an indexed directory of Markdown. The
# useful asymmetry is what the gateway adds on the way through -- the pages
# arrive as a ~600-token index rather than a wall of text, the budget counts
# them with the server's own tokenizer, and the rule engine screens them like
# any other text crossing the boundary.
#
# Deliberately NOT done here: acting on `modelTier`. skore-skills declares
# `metadata.modelTier: small | medium | big`, which lines up exactly with this
# project's routing by need rather than by model name, and it is tempting to
# wire the two together. It is not wired. A third-party directory that can
# raise the tier is a third-party directory deciding what the team pays for
# inference, and that is an operator's decision. The declaration is preserved
# on the page, where a person can read it and configure a route, and it never
# reaches the router on its own.
# ---------------------------------------------------------------------------

#: Heading level the splitter cuts on. Chosen because the specification's own
#: advice is to keep `SKILL.md` short and push detail into references, so a
#: body long enough to need splitting is already organised under `##`.
SPLIT_HEADING = "## "


def import_skills(directory: str | Path) -> list[Skill]:
    """Every skill under ``directory``, in name order.

    A skill is any immediate subdirectory holding a ``SKILL.md``. Nothing
    recurses past that: a `references/` folder belongs to its skill, and
    treating it as a nesting level would turn one skill into several.
    """
    root = Path(directory)
    osh.check(root.is_dir(), f"{root} is not a directory")
    found: list[Skill] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "SKILL.md").is_file():
            continue
        found.append(read_skill(child))
    if not found:
        osh.warning(
            f"[skill] no SKILL.md found under {root}. Point --import at the "
            "directory that *contains* the skills, not at one skill."
        )
    return found


def split_body(body: str, limit: int) -> list[tuple[str, str]]:
    """Cut a long body at ``##`` boundaries, returning (heading, text) slices.

    Text is **distributed, never rewritten**: every slice is a contiguous run
    of the original, so concatenating them returns the input. That is the line
    this project draws elsewhere about editing someone else's content -- a
    gateway may decide where a page ends, and may not decide what it says.

    A body already inside the limit comes back as one unnamed slice, so the
    common case produces exactly one page with no heading invented for it.
    """
    if len(body) <= limit:
        return [("", body)]

    chunks: list[tuple[str, str]] = []
    heading = ""
    buffer: list[str] = []
    for line in body.splitlines(keepends=True):
        if line.startswith(SPLIT_HEADING):
            if "".join(buffer).strip():
                chunks.append((heading, "".join(buffer)))
            heading = line[len(SPLIT_HEADING) :].strip()
            buffer = [line]
            continue
        buffer.append(line)
    if "".join(buffer).strip():
        chunks.append((heading, "".join(buffer)))
    return chunks or [("", body)]


def _slug(text: str, fallback: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out[:48] or fallback


def as_charter_pack(
    skills: list[Skill],
    *,
    pack: str,
    source: str = "",
    limit: int = 12_000,
) -> dict[str, str]:
    """Render skills as charter pages, keyed by path relative to ``packs/``.

    One page per skill, plus one per bundled reference, plus a split into
    numbered parts for a body over ``limit``. The default limit is the
    charter's own page budget, and it is a parameter rather than an import so
    this function can be tested at a size that fits in a test.

    Each page opens with what the index cannot carry: where it came from, what
    the source declared about it, and a digest of the text it was made from.
    The digest is the point of the header -- it is what lets anyone check
    later whether this copy still matches upstream, which is the same argument
    `build_skill` makes in reverse about a skill on disk drifting from the
    charter the gateway enforces.
    """
    pages: dict[str, str] = {}
    for skill in skills:
        name = skill.name or "unnamed"
        digest = hashlib.sha256(skill.body.encode("utf-8")).hexdigest()[:16]
        declared = ", ".join(f"`{k}: {v}`" for k, v in sorted(skill.metadata.items()))

        header = [f"# {name}", ""]
        if skill.description:
            header += [skill.description.strip(), ""]
        provenance = [f"**Imported skill.** Source: {source or 'unrecorded'}. Digest `{digest}`."]
        if declared:
            provenance.append(
                f"The source declares {declared}. Recorded, not acted on: a routing "
                "decision belongs to the operator, not to an imported directory."
            )
        header += [" ".join(provenance), ""]

        slices = split_body(skill.body, limit)
        for index, (heading, text) in enumerate(slices, start=1):
            if len(slices) == 1:
                key = f"{pack}/{name}.md"
                part = []
            else:
                # The first slice is the body's preamble -- everything before
                # the first `##` -- and has no heading to be named after.
                fallback = "overview" if index == 1 else f"part{index}"
                key = f"{pack}/{name}/{index:02d}_{_slug(heading, fallback)}.md"
                part = [
                    f"*Part {index} of {len(slices)} of `{name}`, split at a heading "
                    "because the whole exceeded the page budget. The text is "
                    "unchanged.*",
                    "",
                ]
            pages[key] = "\n".join(header + part + [text.strip(), ""])

        for ref_name, ref_text in skill.references.items():
            stem = Path(ref_name).stem
            pages[f"{pack}/{name}/ref_{_slug(stem, 'reference')}.md"] = (
                f"# {name}: {stem}\n\n"
                f"*Bundled reference from the imported skill `{name}`. "
                f"Source: {source or 'unrecorded'}.*\n\n"
                f"{ref_text.strip()}\n"
            )
    return pages


def write_charter_pack(
    pages: dict[str, str],
    charter_root: str | Path,
    *,
    force: bool = False,
) -> list[Path]:
    """Write rendered pages under ``charter_root/packs/``.

    Nothing is overwritten without ``force``, for the reason `adopt` gives:
    a charter page that already exists was written or reviewed by somebody,
    and replacing it silently is how a tool stops being run.
    """
    base = Path(charter_root) / "packs"
    written: list[Path] = []
    for rel, text in sorted(pages.items()):
        target = base / rel
        if target.exists() and not force:
            osh.warning(f"[skill] {target} exists; left alone. Pass --force to replace.")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written
