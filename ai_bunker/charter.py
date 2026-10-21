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

from .i18n import DEFAULT_LOCALE, available, translator

#: Where packs live, relative to a charter root.
PACKS_DIR = "packs"

#: Ceiling on the index itself. Past this, the index degrades to pack names and
#: page counts rather than growing without limit -- an index that costs what the
#: pages would have cost has defeated its own purpose.
MAX_INDEX_CHARS = 1200

#: Largest page worth carrying. A page an agent must read in twenty slices is
#: not a reference, it is a document, and it should be split.
MAX_PAGE_CHARS = 12_000


def _declared_locale(path: Path) -> str:
    """The locale a filename declares, or ``""`` -- ``10_style.fr.md`` -> ``fr``.

    Only locales that have a catalogue count. The alternative, reading any
    two-letter segment as a language, turns ``api.v2.md`` into a translation of
    ``api.md`` for a language called ``v2``, and a page would vanish from the
    index to pay for the cleverness.
    """
    head, _, tail = path.stem.rpartition(".")
    return tail if head and tail in available() else ""


def _for_locale(path: Path, locale: str) -> Path:
    """``path``'s sibling for ``locale``, or ``path`` when none exists.

    The convention is the locale before the extension: ``AGENTS.md`` and
    ``AGENTS.fr.md``, ``10_style.md`` and ``10_style.fr.md``. Chosen over a
    parallel ``packs.fr/`` tree because a translation that sits next to its
    original is reviewed in the same diff and noticed when the original moves;
    a parallel tree is how half a charter ends up describing a page that was
    renamed a year ago.

    No special case for the default locale, deliberately. A deployment whose
    base pages are written in French can ship ``10_style.en.md`` and get the
    same behaviour in the other direction. The base file is simply the
    fallback for every locale, which is also what makes a partial translation
    usable rather than a half-broken charter.
    """
    sibling = path.with_name(f"{path.stem}.{locale}{path.suffix}")
    return sibling if sibling.is_file() else path


@dataclass(frozen=True)
class Page:
    """One page of the charter.

    ``name`` is always the base spelling and ``path`` may be a translation of
    it. That split is the whole design: a page keeps **one** reference in every
    language, so the index costs the same and `read_page` answers the same
    question whatever the charter's locale. What changes is the file served.
    """

    pack: str
    name: str
    path: Path
    chars: int
    #: Whether ``path`` is a locale sibling rather than the base file. Lets a
    #: deployment be told which pages have fallen behind instead of finding out
    #: when an agent reads English standards out of a French prompt.
    translated: bool = False

    @property
    def ref(self) -> str:
        """How the index names this page, and how a caller asks for it back.

        The base spelling, never the translated filename. An index that listed
        `10_style.fr.md` would teach the agent a path that only resolves in one
        language, and an index that listed both would cost double -- on the one
        block paid for on every request.
        """
        return f"{self.pack}/{self.name}"


@dataclass
class Charter:
    """A loaded charter: its rules of operation, and an index of its pages.

    ``locale`` is a property of the *loaded* charter rather than an argument to
    the functions that render it, and that is the design, not a shortcut. The
    language an agent is instructed in belongs to the deployment: it is read
    from configuration once, at load time. A request cannot reach it, because
    after this there is no seam to pass one through -- the per-request locale
    that `negotiate()` works out from `Accept-Language` reaches refusals and
    notes, and stops there.
    """

    root: Path
    operating_rules: str
    pages: list[Page] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    locale: str = DEFAULT_LOCALE

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

        The locale is part of the digest, and both of those uses are why. Since
        the index is rendered in the charter's locale, two deployments of the
        same files serve system prompts that differ in bytes -- so a key that
        ignored the locale would name two different prompts the same thing,
        which is wrong for a cache and worse for provenance. A record saying
        "this ran under charter 9f2c" has to mean one prompt, not two.
        """
        parts = [self.locale, self.operating_rules]
        parts += [
            f"{p.ref}:{p.path.read_text(encoding='utf-8')}"
            for p in sorted(self.pages, key=lambda q: q.ref)
        ]
        return osh.hash_string("\n".join(parts))


def load_charter(
    root: str | Path, *, rules_file: str = "AGENTS.md", locale: str = DEFAULT_LOCALE
) -> Charter:
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
    locale : str
        Language for the index this charter renders. Comes from the
        deployment's ``language:``, and the default stays English for the
        reason given in `ai_bunker.i18n`: a deployment opts in rather than
        having the language an agent is instructed in decided for it.

    Returns
    -------
    Charter
        Loaded charter. A missing root or missing packs tree yields an empty
        charter and a warning rather than an error: a deployment with no
        charter is a choice.
    """
    base = Path(root)
    warnings: list[str] = []

    # The *effective* locale, not what was asked for. `language:` defaults to
    # an empty string and an unknown locale falls back, so "", "zz" and
    # "en-US" all render the identical English index -- and storing them
    # verbatim gave one prompt three fingerprints, which is the exact lie
    # putting the locale in the digest was meant to prevent. Resolve once,
    # here, so the field always names the language the index is really in.
    locale = translator(locale).locale

    if not base.is_dir():
        osh.warning(f"[charter] no charter at {base}; serving without one.")
        return Charter(
            root=base,
            operating_rules="",
            pages=[],
            warnings=[f"no charter at {base}"],
            locale=locale,
        )

    rules_base = base / rules_file
    rules_path = _for_locale(rules_base, locale)
    operating_rules = ""
    if osh.file_exists(str(rules_path)):
        operating_rules = rules_path.read_text(encoding="utf-8").strip()
        if locale != DEFAULT_LOCALE and rules_path == rules_base:
            wanted = f"{rules_base.stem}.{locale}{rules_base.suffix}"
            warnings.append(
                f"{rules_file} has no {locale} translation ({wanted}), so the block "
                "injected into every request is served in its original language while "
                "the rest of the prompt is not."
            )
            osh.warning(f"[charter] {warnings[-1]}")
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
        found_files = [Path(f) for f in sorted(osh.recursive_glob(str(packs_root), "*.md"))]
        present = {p.resolve() for p in found_files}
        untranslated: list[str] = []

        for path in found_files:
            rel = path.relative_to(packs_root)

            # A translation is not a page. It is the same page in another
            # language, reached through the base file below -- listing it would
            # either double the index or teach the agent a path that resolves
            # in one language only.
            declared = _declared_locale(path)
            if declared:
                original = path.with_name(f"{path.stem.removesuffix('.' + declared)}{path.suffix}")
                if original.resolve() not in present:
                    warnings.append(
                        f"{rel} is a {declared} translation of {original.name}, which does "
                        "not exist. A translation is reached through the page it "
                        "translates, so this file is served to nobody; rename it or add "
                        "the page."
                    )
                    osh.warning(f"[charter] {warnings[-1]}")
                continue

            if len(rel.parts) < 2:
                warnings.append(
                    f"{rel} sits directly under {PACKS_DIR}/ with no pack. A page "
                    "belongs to a domain; the index groups by pack and this one has "
                    "nowhere to go."
                )
                osh.warning(f"[charter] {warnings[-1]}")
                continue

            # The file actually served, which is what the budget and the
            # fingerprint have to measure -- a translation is not the same
            # length as its original.
            served = _for_locale(path, locale)
            if served == path and locale != DEFAULT_LOCALE:
                untranslated.append(str(rel))
            size = served.stat().st_size
            if size > MAX_PAGE_CHARS:
                warnings.append(
                    f"{served.relative_to(packs_root)} is {osh.format_size(size)}, over the "
                    f"{MAX_PAGE_CHARS:,}-character page budget. An agent reads it in "
                    "slices of eighty lines; past this it will read the beginning and "
                    "guess the rest. Split it."
                )
                osh.warning(f"[charter] {warnings[-1]}")
            pages.append(
                Page(
                    pack=rel.parts[0],
                    name=str(Path(*rel.parts[1:])),
                    path=served,
                    chars=size,
                    translated=served != path,
                )
            )

        # One warning naming all of them, not one per page. A translation
        # falling behind is the normal failure mode of any translation, and the
        # operator needs the list, not a scroll.
        if untranslated:
            warnings.append(
                f"{len(untranslated)} page(s) have no {locale} translation and are served "
                f"in their original language: {', '.join(untranslated)}."
            )
            osh.warning(f"[charter] {warnings[-1]}")
    else:
        warnings.append(f"no {PACKS_DIR}/ directory under {base}")

    osh.debug(f"[charter] {len(pages)} page(s) across {len({p.pack for p in pages})} pack(s).")
    return Charter(
        root=base, operating_rules=operating_rules, pages=pages, warnings=warnings, locale=locale
    )


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

    Rendered in ``charter.locale``. This block is the one piece of agent-facing
    text that is paid on every request, so it is also the one where leaving it
    English on a French deployment was least defensible: a model is better at
    following an instruction in the language the rest of its prompt is in, and
    this is the instruction that decides whether the charter is opened at all.
    """
    packs = charter.packs
    if not packs:
        return ""
    _ = translator(charter.locale)

    # Degrade rather than grow: an index that costs what the pages cost has
    # reinvented concatenation. The degradation is **per pack**, biggest
    # first, and that detail was found by importing a 77-page pack into this
    # charter: collapsing the whole body turned `python: 10_style.md,
    # tests.md` into `python (2 pages)`, spending the agent's knowledge of two
    # page names to save the forty-five characters that named them. One large
    # pack should cost its own names, not everyone else's.
    named = {pack: f"- {pack}: {', '.join(p.name for p in pages)}" for pack, pages in packs.items()}
    collapsed: set[str] = set()
    order = sorted(packs, key=lambda pack: len(named[pack]), reverse=True)

    def render() -> str:
        return "\n".join(
            _.ngettext("charter.index.pack", len(packs[pack]), pack=pack)
            if pack in collapsed
            else named[pack]
            for pack in packs
        )

    for pack in order:
        if len(render()) <= MAX_INDEX_CHARS:
            break
        collapsed.add(pack)

    body = render()
    if collapsed:
        body += "\n" + _("charter.index.list_one", dir=PACKS_DIR)

    example = next(
        (p.ref for p in charter.pages if p.pack == "python"),
        charter.pages[0].ref if charter.pages else "",
    )
    return "\n".join(
        [
            _("charter.index.heading"),
            _("charter.index.not_loaded", dir=PACKS_DIR),
            _("charter.index.when"),
            _("charter.index.one_at_a_time"),
            body,
            _("charter.index.example", dir=PACKS_DIR, ref=example),
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
