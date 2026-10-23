"""
Equip a repository: the charter, and a client pointed at the gateway.

Two things get copied, and the asymmetry between them is the design.

The **charter** is the project's own: its operating rules and its standards
pages. It belongs in the repository, versioned, reviewed like code, because it
describes *this* codebase.

A **client kit** is thin on purpose. Everything the gateway can see, the
gateway enforces for every client with no way to opt out. What a kit carries is
exactly the set of things that happen *before a request exists* -- bounded
reads, no skill injection, compaction thresholds -- which no endpoint can
reach. See ``clients/README.md`` for the full division of labour.

Nothing is overwritten without ``force``. A repository that already has an
``AGENTS.md`` has one for a reason, and silently replacing it is how a tool
loses the trust it needs to be run again.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import os_helper as osh

from .i18n import available

#: Repository root of this installation, so an adopt can find its own templates.
ROOT = Path(__file__).resolve().parent.parent

#: Environment variable naming where the website lives.
#:
#: The site used to be `web/` inside this repository and is now a directory
#: the maintainer uploads from, outside it. That is a deliberate trade: the
#: upload is a copy of one folder, and the site stops being versioned here.
#: What it costs the repository is that five scripts and three test modules
#: read the site, and all of them now have to be able to say "not on this
#: machine" rather than fail -- a gate that is permanently red is a gate
#: nobody reads, which this project learned the hard way in round 7.
SITE_ENV = "AI_BUNKER_SITE"

#: Searched in order when `AI_BUNKER_SITE` is unset. `web/` comes first so a
#: checkout that still carries the site works unchanged; the second is the
#: maintainer's own layout, where `~/web/deraison/` mirrors `deraison.ai` one
#: directory per path. Hardcoding somebody's home directory in a library is
#: ugly, and the honest alternative -- requiring an environment variable in
#: every shell -- is the kind of friction that gets a check disabled.
SITE_CANDIDATES = ("web", "~/web/deraison/ai-bunker")


def site_root() -> Path | None:
    """Where the website's tree is, or None when it is not here.

    None is a real answer rather than an error: the site is no longer part of
    this repository, so continuous integration runs without it and every
    caller has to decide what that means for itself. A caller that cannot work
    without the site should skip; one that only wanted to lint it should say
    so and pass.
    """
    named = os.environ.get(SITE_ENV, "").strip()
    if named:
        candidate = Path(named).expanduser()
        return candidate if candidate.is_dir() else None
    for relative in SITE_CANDIDATES:
        candidate = Path(relative).expanduser() if relative.startswith("~") else ROOT / relative
        if candidate.is_dir():
            return candidate
    return None


def site_file(relative: str) -> Path | None:
    """One file of the site, by the path it had when the site lived in `web/`.

    Written so the file lists in `lint_claims.py` and `lint_acronyms.py` can
    keep naming `web/index.html` -- the spelling a reader of those files
    recognises, and the spelling the site still uses internally.
    """
    root = site_root()
    if root is None:
        return None
    inside = relative[4:] if relative.startswith("web/") else relative
    found = root / inside
    return found if found.is_file() else None


#: Written by default. Both are *code agents* -- somebody else's loop, which a
#: kit has to reach into for the things that happen before a request exists.
CLIENTS = ("opencode", "claude-code")

#: Opt-in, via ``--client``. These are *agent frameworks*: you write the loop,
#: so there is no harness to configure, and the kit is a module you import.
#: Deliberately not in :data:`CLIENTS` -- a default that dropped Python files
#: into every repository that ran ``adopt`` would be writing application code
#: on the user's behalf, which is a different thing from configuring a tool.
FRAMEWORKS = ("langgraph", "llamaindex", "smolagents")

#: Everything ``--client`` accepts.
ALL_CLIENTS = CLIENTS + FRAMEWORKS

#: Where each framework kit comes from and lands. One module per framework
#: rather than a shared ``ai_bunker_client.py``: adopting two of them into one
#: repository must not have the second overwrite the first.
FRAMEWORK_KITS = {
    "langgraph": "ai_bunker_langgraph.py",
    "llamaindex": "ai_bunker_llamaindex.py",
    "smolagents": "ai_bunker_smolagents.py",
}

#: Placeholders substituted into a client template. Everything here is either a
#: deployment fact or a secret, so none of it is hardcoded into the templates:
#: a rendered kit is committable, and a re-render picks up a moved gateway.
PLACEHOLDERS = (
    "AI_BUNKER_URL",
    "AI_BUNKER_URL_ROOT",
    "AI_BUNKER_API_KEY",
    "AI_BUNKER_MODEL",
    "AI_BUNKER_DECLARED_CONTEXT",
    "AI_BUNKER_COMPACTION_RESERVE",
    "AI_BUNKER_TEMPERATURE",
)


@dataclass
class Plan:
    """What an adopt would write, before it writes anything."""

    target: Path
    writes: list[tuple[str, str]] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing

    def summary(self) -> str:
        lines = [f"Adopting ai-bunker into {self.target}:"]
        lines += [f"  + {path}   ({why})" for path, why in self.writes]
        lines += [f"  = {path}   kept; --force to replace" for path in self.kept]
        lines += [f"  ! {path}   missing from this installation" for path in self.missing]
        lines += [f"  ~ {note}" for note in self.notes]
        return "\n".join(lines)


#: Files that make Claude Code ignore ``AGENTS.md``, in the spellings its own
#: documentation counts. Quoted, because the rule is not symmetrical and
#: guessing it wrong is what this check exists to prevent: "By default, Claude
#: reads AGENTS.md only when you have no CLAUDE.md in your working directory or
#: above it."
SHADOWING_NAMES = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md")

#: Where an ``AGENTS.md`` that a repository already relies on actually sits.
#: Not ``charter/AGENTS.md``: that one is the charter's operating rules, served
#: by the gateway, and no client reads it as project instructions.
AGENTS_NAMES = ("AGENTS.md", ".claude/AGENTS.md")


def shadowing_claude_files(target: Path) -> list[Path]:
    """Existing files that already stop Claude Code reading an ``AGENTS.md``.

    Walks upward, because the rule does: a ``CLAUDE.md`` three directories
    above a repository shadows that repository's ``AGENTS.md``.

    ``~/.claude/CLAUDE.md`` is excluded deliberately. The documentation puts it
    in the list that does **not** count and that keeps loading alongside
    ``AGENTS.md``, so including it here would warn every user who has personal
    instructions -- which is most of them -- about a conflict that does not
    exist.
    """
    home = Path.home().resolve()
    found: list[Path] = []
    for directory in [target, *target.parents]:
        for name in SHADOWING_NAMES:
            candidate = directory / name
            if candidate == home / ".claude" / "CLAUDE.md":
                continue
            if candidate.is_file():
                found.append(candidate)
    return found


def shadowing_notes(target: Path, *, writes: list[str], kept: list[str]) -> list[str]:
    """What an adopt is about to do to this repository's ``AGENTS.md``.

    The hazard runs the opposite way round to the one you expect. This tool
    does not write a root ``AGENTS.md`` -- see ``plan_adopt`` for why -- but it
    *does* write a root ``CLAUDE.md`` for the Claude Code kit. So a repository
    that keeps its instructions in ``AGENTS.md``, as tens of thousands do,
    adopts ai-bunker and finds that Claude Code has quietly stopped reading
    the file it has been maintaining. Nothing errors. The instructions simply
    go dark.

    Reported rather than refused: which file a team keeps its instructions in
    is their decision, and a tool that declines to install because it
    disapproves of the layout is a tool people stop running. But an adopt that
    said nothing would be arranging the failure in silence.
    """
    present = [name for name in AGENTS_NAMES if (target / name).is_file()]
    if not present:
        return []

    listed = ", ".join(present)
    notes: list[str] = []
    already = [p for p in shadowing_claude_files(target) if p.parent != target]

    if "CLAUDE.md" in writes:
        notes.append(
            f"{listed} is present, and this adopt writes CLAUDE.md. Claude Code reads "
            "AGENTS.md only when there is no CLAUDE.md in the working directory or "
            f"above it, so after this {listed} stops being read by that client. The "
            "written CLAUDE.md explains what the gateway does to a session; if you "
            "want to keep one file, merge it into "
            f"{present[0]} and delete CLAUDE.md, or adopt with --client opencode."
        )
    elif "CLAUDE.md" in kept:
        notes.append(
            f"{listed} and CLAUDE.md both exist. Claude Code is already reading "
            f"CLAUDE.md and ignoring {listed}; this adopt does not change that, and "
            "did not cause it."
        )

    if already:
        where = ", ".join(str(p) for p in already)
        notes.append(
            f"{listed} is also shadowed from above by {where}. That applies to every "
            "repository under those directories, not just this one."
        )
    return notes


def _values(
    *,
    url: str,
    api_key: str,
    model: str,
    declared_context: int,
    compaction_reserve: int,
    temperature: float,
) -> dict[str, str]:
    root = url.rstrip("/")
    return {
        "AI_BUNKER_URL": root,
        # Claude Code wants the server root, OpenAI clients want /v1. Deriving
        # one from the other beats asking a user for the same URL twice.
        "AI_BUNKER_URL_ROOT": root[: -len("/v1")] if root.endswith("/v1") else root,
        "AI_BUNKER_API_KEY": api_key,
        "AI_BUNKER_MODEL": model,
        "AI_BUNKER_DECLARED_CONTEXT": str(declared_context),
        "AI_BUNKER_COMPACTION_RESERVE": str(compaction_reserve),
        "AI_BUNKER_TEMPERATURE": str(temperature),
    }


def render(text: str, values: dict[str, str]) -> str:
    """Substitute ``{{PLACEHOLDER}}`` occurrences.

    Unresolved placeholders are left in place and reported rather than
    replaced with an empty string: a config file containing ``{{...}}`` fails
    loudly at load, where a silently empty URL fails at the first request with
    a message about nothing in particular.
    """
    out = text
    for name in PLACEHOLDERS:
        if name in values:
            out = out.replace("{{" + name + "}}", values[name])
    leftover = [n for n in PLACEHOLDERS if "{{" + n + "}}" in out]
    if leftover:
        osh.warning(
            f"[adopt] unresolved placeholder(s): {', '.join(leftover)}. The rendered "
            "file will fail at load rather than at the first request, which is the "
            "better of the two."
        )
    return out


def plan_adopt(
    target: str | Path,
    *,
    clients: tuple[str, ...] = CLIENTS,
    charter: bool = True,
    force: bool = False,
    root: Path | None = None,
) -> Plan:
    """Work out what an adopt would do, without doing it.

    Separated from :func:`adopt` so ``--list`` is the same code path as the
    real thing. A dry run that takes a different route is a dry run that can
    disagree with the run.
    """
    base = root or ROOT
    destination = Path(target).expanduser().resolve()
    plan = Plan(target=destination)

    items: list[tuple[str, str, str]] = []  # (source, destination, why)
    if charter:
        # A self-contained charter/ directory, operating rules included. No
        # copy at the repository root, and that follows from the project's own
        # thesis: the gateway injects the operating rules into every request,
        # so a client does not need to find them on disk. A root AGENTS.md
        # would be a second copy of the same text, free to drift from the one
        # actually being served -- which is the failure mode the whole design
        # exists to avoid.
        items += [
            ("charter/AGENTS.md", "charter/AGENTS.md", "how to work here, injected every request"),
            ("charter/packs", "charter/packs", "the standards pages, read on demand"),
            ("charter/rules", "charter/rules", "the rules, with their own evidence"),
        ]
        # The operating rules are copied by name; `charter/packs` is copied as
        # a tree and brings its own translations along. So these have to be
        # named too, or an adopted copy of a French charter would serve French
        # pages under English operating rules -- and `load_charter` would warn
        # about a translation the adopt had simply left behind.
        items += [
            (f"charter/AGENTS.{code}.md", f"charter/AGENTS.{code}.md", f"the same, in {code}")
            for code in available()
            if (base / f"charter/AGENTS.{code}.md").is_file()
        ]
    for client in clients:
        if client == "opencode":
            items += [
                ("clients/opencode/opencode.json", "opencode.json", "points at the gateway"),
                (
                    "clients/opencode/.opencode/plugins/bounded-reads.js",
                    ".opencode/plugins/bounded-reads.js",
                    "the one thing the gateway cannot do",
                ),
            ]
        elif client == "claude-code":
            items += [
                (
                    "clients/claude-code/settings.json",
                    ".claude/settings.ai-bunker.json",
                    "merge into .claude/settings.json",
                ),
                (
                    "clients/claude-code/CLAUDE.md",
                    "CLAUDE.md",
                    "what the gateway does to a session",
                ),
            ]
        elif client in FRAMEWORK_KITS:
            module = FRAMEWORK_KITS[client]
            items += [
                (
                    f"clients/{client}/{module}",
                    module,
                    "builds a model pointed at the gateway",
                ),
            ]
        else:
            plan.missing.append(f"unknown client {client!r}")

    for source, relative, why in items:
        if not (base / source).exists():
            plan.missing.append(source)
            continue
        if (destination / relative).exists() and not force:
            plan.kept.append(relative)
            continue
        plan.writes.append((relative, why))

    plan.notes = shadowing_notes(
        destination,
        writes=[relative for relative, _ in plan.writes],
        kept=plan.kept,
    )
    return plan


def adopt(
    target: str | Path,
    *,
    url: str = "http://127.0.0.1:8000/v1",
    api_key: str = "",
    model: str = "devstral",
    declared_context: int = 104_000,
    compaction_reserve: int = 16_000,
    temperature: float = 0.15,
    clients: tuple[str, ...] = CLIENTS,
    charter: bool = True,
    force: bool = False,
    root: Path | None = None,
) -> Plan:
    """Write the charter and the client kits into ``target``.

    Parameters
    ----------
    target : str or Path
        The repository to equip.
    url : str
        The gateway's ``/v1`` base URL. Substituted into the client configs.
    api_key : str
        The gateway key. Substituted too, so prefer an environment variable
        for it on a machine where the rendered file will be committed.
    model, declared_context, compaction_reserve, temperature
        Client-side figures. ``declared_context`` should match what
        ``GET /v1/models`` publishes: the gateway audits it, and a client that
        declares more is eventually refused.
    clients : tuple of str
        Which kits to write.
    charter : bool
        Whether to copy the charter as well. Off when a repository already has
        its own and only needs a client pointed at the gateway.
    force : bool
        Replace files that already exist. Off by default: a repository with an
        ``AGENTS.md`` has one for a reason.

    Returns
    -------
    Plan
        What was written and what was kept.
    """
    base = root or ROOT
    destination = Path(target).expanduser().resolve()
    osh.check(destination.is_dir(), f"{destination} is not a directory.")
    osh.check(
        destination != base,
        "The target is this installation itself; adopting into it would "
        "overwrite the templates with their own rendered output.",
    )

    plan = plan_adopt(target=destination, clients=clients, charter=charter, force=force, root=base)
    osh.check(
        plan.ok,
        "This installation is incomplete: " + ", ".join(plan.missing),
    )

    values = _values(
        url=url,
        api_key=api_key,
        model=model,
        declared_context=declared_context,
        compaction_reserve=compaction_reserve,
        temperature=temperature,
    )

    sources = {
        "charter/AGENTS.md": "charter/AGENTS.md",
        "charter/packs": "charter/packs",
        "charter/rules": "charter/rules",
        **{f"charter/AGENTS.{code}.md": f"charter/AGENTS.{code}.md" for code in available()},
        "opencode.json": "clients/opencode/opencode.json",
        ".opencode/plugins/bounded-reads.js": "clients/opencode/.opencode/plugins/bounded-reads.js",
        ".claude/settings.ai-bunker.json": "clients/claude-code/settings.json",
        "CLAUDE.md": "clients/claude-code/CLAUDE.md",
        **{module: f"clients/{name}/{module}" for name, module in FRAMEWORK_KITS.items()},
    }

    for relative, _why in plan.writes:
        source = base / sources[relative]
        written = destination / relative
        osh.make_directory(str(written.parent))
        if source.is_dir():
            if written.exists():
                shutil.rmtree(written)
            shutil.copytree(source, written)
        else:
            # Templates are rendered on the way out; everything else is copied
            # byte for byte so a charter page is never silently rewritten.
            text = source.read_text(encoding="utf-8")
            written.write_text(render(text, values) if "{{" in text else text, encoding="utf-8")
        osh.debug(f"[adopt] wrote {relative}")

    if not api_key:
        osh.warning(
            "[adopt] no API key given, so the rendered client config has an empty one. "
            "If the gateway is authenticated, set AI_BUNKER_API_KEY and re-run with "
            "--force."
        )

    # After the writes, not before: the notes describe the state the
    # repository is now in, and a warning printed ahead of the files it
    # describes reads as a prediction nobody can check.
    for note in plan.notes:
        osh.warning(f"[adopt] {note}")

    return plan
