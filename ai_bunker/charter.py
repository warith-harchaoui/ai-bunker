"""
The charter: standards served as an index, never as a wall of text.

The tempting way to give a model your team's standards is to paste them all
into the system prompt. It is also the one that does not work, for a reason
that is arithmetic rather than aesthetic: the system prompt is the **floor** of
a session -- paid on every single request, and out of reach of compaction. A
charter pasted there is spent before the first question is asked, on every
turn, whether or not the model needed any of it.

So the charter is advertised, not delivered. A roughly 1,000-character index
names the packs and their pages; the model opens the one page the task calls
for, with the ordinary file-reading tool, in bounded slices. **A page costs
nothing until it is opened**, which is what lets the charter be large.

Measured, on the deployment this was built for: the index plus the project's
operating rules came to 1,088 tokens, about 4% of a 26,000-token declared
window, and one page opened at the right moment cost another 2%. Concatenating
the same 37 pages would have cost roughly 18,000 -- the whole window, before
any work.

The index is also the only part a model cannot ignore, which makes its wording
load-bearing: it has to say *when* to open a page, not just that pages exist.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import os_helper as osh

#: Where packs live, relative to a charter root.
PACKS_DIR = "packs"

#: Ceiling on the index itself. Past this, the index degrades to pack names and
#: page counts rather than growing without limit -- an index that costs what the
#: pages would have cost has defeated its own purpose.
MAX_INDEX_CHARS = 1200

#: Largest page worth carrying. A page an agent must read in twenty slices is
#: not a reference, it is a document, and it should be split.
MAX_PAGE_CHARS = 12_000


@dataclass(frozen=True)
class Page:
    """One page of the charter."""

    pack: str
    name: str
    path: Path
    chars: int

    @property
    def ref(self) -> str:
        """How the index names this page, and how a caller asks for it back."""
        return f"{self.pack}/{self.name}"


@dataclass
class Charter:
    """A loaded charter: its rules of operation, and an index of its pages."""

    root: Path
    operating_rules: str
    pages: list[Page] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def packs(self) -> dict[str, list[Page]]:
        """Pages grouped by pack, in a stable order."""
        out: dict[str, list[Page]] = {}
        for page in self.pages:
            out.setdefault(page.pack, []).append(page)
        return {k: sorted(v, key=lambda p: p.name) for k, v in sorted(out.items())}

    @property
    def fingerprint(self) -> str:
        """A stable digest of the charter's content.

        Two uses, both practical. It is a cache key: a serving engine's prefix
        cache re-serves an unchanged system prompt almost for free, so knowing
        the charter has *not* changed is worth money. And it is provenance: a
        session can record which charter it ran under, which is the difference
        between "the rules were followed" and "some rules were followed".
        """
        parts = [self.operating_rules]
        parts += [
            f"{p.ref}:{p.path.read_text(encoding='utf-8')}"
            for p in sorted(self.pages, key=lambda q: q.ref)
        ]
        return osh.hash_string("\n".join(parts))


def load_charter(root: str | Path, *, rules_file: str = "AGENTS.md") -> Charter:
    """Load a charter from disk.

    Parameters
    ----------
    root : str or Path
        Charter directory. Expected to hold ``AGENTS.md`` (or whatever
        ``rules_file`` names) and a ``packs/`` tree of Markdown.
    rules_file : str
        The operating rules: the one piece that *is* injected into every
        prompt, because it is what tells the model how to work -- read in
        slices, open one page at a time, do not dump a repository into the
        window. Everything else is indexed.

    Returns
    -------
    Charter
        Loaded charter. A missing root or missing packs tree yields an empty
        charter and a warning rather than an error: a deployment with no
        charter is a choice.
    """
    base = Path(root)
    warnings: list[str] = []

    if not base.is_dir():
        osh.warning(f"[charter] no charter at {base}; serving without one.")
        return Charter(root=base, operating_rules="", pages=[], warnings=[f"no charter at {base}"])

    rules_path = base / rules_file
    operating_rules = ""
    if osh.file_exists(str(rules_path)):
        operating_rules = rules_path.read_text(encoding="utf-8").strip()
    else:
        warnings.append(
            f"{rules_file} is missing. Without it the model is given an index and no "
            "instruction to consult it, which reliably produces a charter nobody reads."
        )
        osh.warning(f"[charter] {warnings[-1]}")

    packs_root = base / PACKS_DIR
    pages: list[Page] = []
    if packs_root.is_dir():
        # recursive_glob so a pack can nest (javascript/react/...), which is how
        # a charter stays navigable once it has more than a handful of pages.
        for found in sorted(osh.recursive_glob(str(packs_root), "*.md")):
            path = Path(found)
            rel = path.relative_to(packs_root)
            if len(rel.parts) < 2:
                warnings.append(
                    f"{rel} sits directly under {PACKS_DIR}/ with no pack. A page "
                    "belongs to a domain; the index groups by pack and this one has "
                    "nowhere to go."
                )
                osh.warning(f"[charter] {warnings[-1]}")
                continue
            size = path.stat().st_size
            if size > MAX_PAGE_CHARS:
                warnings.append(
                    f"{rel} is {osh.format_size(size)}, over the "
                    f"{MAX_PAGE_CHARS:,}-character page budget. An agent reads it in "
                    "slices of eighty lines; past this it will read the beginning and "
                    "guess the rest. Split it."
                )
                osh.warning(f"[charter] {warnings[-1]}")
            pages.append(
                Page(pack=rel.parts[0], name=str(Path(*rel.parts[1:])), path=path, chars=size)
            )
    else:
        warnings.append(f"no {PACKS_DIR}/ directory under {base}")

    osh.debug(f"[charter] {len(pages)} page(s) across {len({p.pack for p in pages})} pack(s).")
    return Charter(root=base, operating_rules=operating_rules, pages=pages, warnings=warnings)


def build_index(charter: Charter) -> str:
    """The index injected into the system prompt.

    Every line here is paid on every request, so the wording is chosen rather
    than generated. Four things have to be said, and nothing else:

    1. the pages exist and where they are;
    2. they are **not** in this prompt -- otherwise a model asked for the
       naming convention will answer from habit rather than open the page;
    3. **when** to open one, because "available if needed" is not an
       instruction a model acts on;
    4. **one at a time**, because an agent told to consult the charter will
       otherwise read the whole pack and spend the window it was saving.

    Point 3 is the one that decides whether a charter is used at all.
    """
    packs = charter.packs
    if not packs:
        return ""

    lines = [f"- {pack}: {', '.join(p.name for p in pages)}" for pack, pages in packs.items()]
    body = "\n".join(lines)
    if len(body) > MAX_INDEX_CHARS:
        # Degrade rather than grow. An index that costs what the pages cost has
        # reinvented concatenation.
        body = "\n".join(f"- {pack} ({len(pages)} pages)" for pack, pages in packs.items())
        body += f"\n  List one with: ls {PACKS_DIR}/<pack>"

    example = next(
        (p.ref for p in charter.pages if p.pack == "python"),
        charter.pages[0].ref if charter.pages else "",
    )
    return "\n".join(
        [
            "## House standards (the charter)",
            f"Pages live under `{PACKS_DIR}/`. They are NOT loaded into this prompt: "
            "read the one you need, when you need it, in slices.",
            "Before writing or reviewing code in one of these domains, read the matching "
            "page. The page wins over your habits and over a library's defaults.",
            "One page at a time, for the domain actually in play: never a whole pack, and "
            "no page at all for a question that writes no code.",
            body,
            f"Example: read {PACKS_DIR}/{example}",
        ]
    )


def read_page(charter: Charter, ref: str) -> str:
    """Serve one page by its index reference (``pack/name.md``).

    Parameters
    ----------
    charter : Charter
        A loaded charter.
    ref : str
        A reference as the index spells it.

    Returns
    -------
    str
        The page's text.

    Raises
    ------
    AssertionError
        If no such page exists. The message lists the pack's pages, because the
        realistic failure is a near-miss on a filename and the fix is to see the
        real one.
    """
    wanted = ref.strip().lstrip("/")
    if wanted.startswith(f"{PACKS_DIR}/"):
        wanted = wanted[len(PACKS_DIR) + 1 :]

    for page in charter.pages:
        if page.ref == wanted:
            return page.path.read_text(encoding="utf-8")

    pack = wanted.split("/")[0]
    siblings = [p.name for p in charter.pages if p.pack == pack]
    hint = (
        f" Pages in {pack}: {', '.join(sorted(siblings))}."
        if siblings
        else f" Known packs: {', '.join(sorted(charter.packs))}."
    )
    osh.check(False, f"[charter] no page {ref!r}.{hint}")
    raise AssertionError  # unreachable; keeps the return type honest


def system_blocks(charter: Charter) -> list[str]:
    """What ai-bunker contributes to a system prompt, in order.

    Deliberately a short list, and deliberately measurable: these are the only
    blocks ai-bunker adds, so ``ai-bunker budget`` can attribute their exact
    cost back to us rather than leaving them inside the client's total.
    """
    blocks = []
    if charter.operating_rules:
        blocks.append(charter.operating_rules)
    index = build_index(charter)
    if index:
        blocks.append(index)
    return blocks
