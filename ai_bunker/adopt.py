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

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import os_helper as osh

#: Repository root of this installation, so an adopt can find its own templates.
ROOT = Path(__file__).resolve().parent.parent

CLIENTS = ("opencode", "claude-code")

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

    @property
    def ok(self) -> bool:
        return not self.missing

    def summary(self) -> str:
        lines = [f"Adopting ai-bunker into {self.target}:"]
        lines += [f"  + {path}   ({why})" for path, why in self.writes]
        lines += [f"  = {path}   kept; --force to replace" for path in self.kept]
        lines += [f"  ! {path}   missing from this installation" for path in self.missing]
        return "\n".join(lines)


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
        "opencode.json": "clients/opencode/opencode.json",
        ".opencode/plugins/bounded-reads.js": "clients/opencode/.opencode/plugins/bounded-reads.js",
        ".claude/settings.ai-bunker.json": "clients/claude-code/settings.json",
        "CLAUDE.md": "clients/claude-code/CLAUDE.md",
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

    return plan
