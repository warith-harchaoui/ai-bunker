"""
The two language halves, held to the same shape.

Why this exists
---------------
`LISEZMOI.md` and `docs/REGLES.md` are not translations in any tooled sense.
They are parallel documents a person keeps in agreement, 57 KB and 56 KB of
them, and the only mechanism was somebody remembering.

It failed, measurably. `LISEZMOI.md` quoted **25 rules and 198 assertions**
when the repository had 27 and 218 -- stale for three sessions, because every
drift guard was written in English and could not match `règles`. That specific
hole is closed; the class of defect was not, and it applies to every sentence
in those files.

What this checks, and what it deliberately does not
---------------------------------------------------
**Structure, not content.** Each pair must carry the same number of sections at
each heading level. That catches the failure that actually happens -- a section
added to one side and not the other -- without pretending to judge a
translation.

It does **not** enforce order, and it does not require the site's two home
pages to match: the French one has no stage cards where the English one does,
which was a choice. A guard that fails on a difference somebody chose is a
guard that gets deleted.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest

from ai_bunker.adopt import ROOT

#: (English, French). Only documents that are genuine twins -- same argument,
#: same order, section for section.
PAIRS = (
    ("README.md", "LISEZMOI.md"),
    ("docs/RULES.md", "docs/REGLES.md"),
    ("LANDSCAPE.md", "PAYSAGE.md"),
    ("EXAMPLES.md", "EXEMPLES.md"),
)


def _headings(relative: str, depth: int) -> list[str]:
    """Headings at one level, ignoring anything inside a code fence.

    The fence matters: `docs/RULES.md` quotes `ai-bunker charter --index` output
    that begins `## House standards`, and counting it as a section is how an
    earlier measurement in this project reported a 29,000-character French
    section inside the English README. There was none.
    """
    out: list[str] = []
    fence = False
    marker = "#" * depth + " "
    for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence and line.startswith(marker):
            out.append(line[len(marker) :].strip())
    return out


@pytest.mark.parametrize("english,french", PAIRS, ids=[p[0] for p in PAIRS])
@pytest.mark.parametrize("depth", [2, 3])
def test_both_halves_carry_the_same_number_of_sections(english, french, depth):
    """A section added to one side and not the other is how 57 KB of parallel
    prose diverges, and it is the one divergence a machine can see."""
    left, right = _headings(english, depth), _headings(french, depth)
    assert len(left) == len(right), (
        f"{english} has {len(left)} level-{depth} sections and {french} has "
        f"{len(right)}. One side gained a section the other did not."
    )


@pytest.mark.parametrize("english,french", PAIRS, ids=[p[0] for p in PAIRS])
def test_neither_half_is_obviously_truncated(english, french):
    """A translation that stops early reads as finished. Length is a weak
    signal and a sharp one at the extremes: French runs longer than English by
    about 10-20% in this project, measured, so a French half *shorter* than its
    English twin is worth a look."""
    left = (ROOT / english).read_text(encoding="utf-8")
    right = (ROOT / french).read_text(encoding="utf-8")
    assert len(right) > len(left) * 0.85, (
        f"{french} is {len(right):,} characters against {english}'s "
        f"{len(left):,}. French is normally longer here; this looks truncated."
    )


def test_the_pairs_named_here_all_exist():
    """A pair that was renamed and not updated here is a guard that silently
    checks nothing."""
    for english, french in PAIRS:
        assert (ROOT / english).is_file(), english
        assert (ROOT / french).is_file(), french
