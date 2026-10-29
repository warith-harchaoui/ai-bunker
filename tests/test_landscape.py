"""
The competitive survey, held to the numbers it is drawn from.

Why this exists
---------------
`LANDSCAPE.md` carries the same comparison twice: once as a table of stars a
reader scans, and once as `assets/landscape.csv`, the file `standpoint` turns
into the positioning map. Two spellings of one claim is a drift waiting to
happen -- and the drift is invisible, because a star count nobody re-reads and
a scatter plot nobody re-renders disagree silently for as long as you like.

`PAYSAGE.md` adds a second axis to the same problem. It is a genuine
translation of the table and it showed the **English** map for ten days: axes
and criteria a French reader never asked for, under a heading promising the
French landscape. Nothing noticed, because nothing was looking.

So four things:

1. Each document's star table is exactly its own `.csv`, rendered.
2. The two `.csv` files score the field identically -- only the names are
   translated. A French score that drifted would be two different analyses
   wearing one argument.
3. Each document points at the map built from its own table.
4. `ai-bunker` is in the table and is not the winner of every column, because
   a landscape where one tool sweeps is a landscape nobody believes -- and
   this file is where that sentence stops being a promise.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: (document, table of numbers, the map image the document must point at).
PAIRS = (
    ("LANDSCAPE.md", "assets/landscape.csv", "assets/landscape.png"),
    ("PAYSAGE.md", "assets/paysage.csv", "assets/paysage.png"),
)


def _scores(relative: str) -> list[list[str]]:
    with (ROOT / relative).open(encoding="utf-8") as handle:
        return list(csv.reader(handle))


def _rendered(rows: list[list[str]]) -> list[str]:
    """The star table a document should carry for these numbers.

    `ai-bunker` is bolded because it is the reference the map is rotated onto,
    and a reader scanning fifteen rows should not have to hunt for the subject
    of the comparison.
    """
    head, body = rows[0], rows[1:]
    lines = [
        "| " + " | ".join(head) + " |",
        "| --- | " + " | ".join([":---:"] * (len(head) - 1)) + " |",
    ]
    for row in body:
        name = f"**{row[0]}**" if row[0] == "ai-bunker" else row[0]
        lines.append("| " + " | ".join([name, *("⭐" * int(v) for v in row[1:])]) + " |")
    return lines


@pytest.mark.parametrize("document,table,image", PAIRS, ids=[p[0] for p in PAIRS])
def test_the_stars_a_reader_scans_are_the_numbers_the_map_is_drawn_from(document, table, image):
    """One comparison, two spellings, and they have to agree.

    Compared line by line rather than as one blob: a mismatch should name the
    row that moved, not report that two thousand characters differ.
    """
    prose = (ROOT / document).read_text(encoding="utf-8")
    block = re.search(r"<!-- TABLE:START -->\n(.*?)\n<!-- TABLE:END -->", prose, re.S)
    assert block, f"{document}: no table between the markers"

    found = block.group(1).splitlines()
    expected = _rendered(_scores(table))
    assert len(found) == len(expected), (
        f"{document}: {len(found)} table rows against {len(expected)} in {table}"
    )
    for i, (a, b) in enumerate(zip(found, expected, strict=True)):
        assert a == b, f"{document}: row {i} disagrees with {table}"


@pytest.mark.parametrize("document,table,image", PAIRS, ids=[p[0] for p in PAIRS])
def test_each_half_shows_the_map_built_from_its_own_table(document, table, image):
    """The failure this test was written for, in one line.

    `PAYSAGE.md` carried `landscape.png` -- the English map, English axes,
    English criteria -- under *Carte de positionnement*. The twin test in
    `tests/test_bilingual.py` counts headings and was perfectly happy.
    """
    prose = (ROOT / document).read_text(encoding="utf-8")
    assert (ROOT / image).exists(), f"{image} has not been generated"

    wanted = Path(image).name
    others = {Path(other).name for _d, _t, other in PAIRS} - {wanted}
    assert wanted in prose, f"{document} does not show {wanted}"
    for stranger in others:
        assert stranger not in prose, f"{document} shows {stranger}, the other half's map"


def test_both_languages_score_the_field_the_same_way():
    """Only the names are translated. The judgement is one judgement."""
    english, french = _scores("assets/landscape.csv"), _scores("assets/paysage.csv")
    assert len(english) == len(french), "the two tables rank different numbers of tools"
    for row_en, row_fr in zip(english[1:], french[1:], strict=True):
        assert row_en[1:] == row_fr[1:], f"{row_en[0]} / {row_fr[0]} are scored differently"


def test_the_survey_rates_this_project_and_does_not_let_it_win_everything():
    """A landscape where one tool sweeps every column is a landscape nobody
    believes, and `LANDSCAPE.md` says so in prose. Here is the assertion
    behind the sentence.

    Two columns are named rather than merely counted. Isolation belongs to
    ToolHive and the Docker MCP Gateway -- this project hands the command back
    to a harness that runs it on the host -- and provider breadth belongs to
    LiteLLM. Both are stated in *Where this project is behind*, and both would
    be quietly flattering to score up.
    """
    rows = _scores("assets/landscape.csv")
    criteria = rows[0][1:]
    scores = {row[0]: [int(v) for v in row[1:]] for row in rows[1:]}
    assert "ai-bunker" in scores

    mine = scores["ai-bunker"]
    beaten = [
        criteria[i]
        for i in range(len(criteria))
        if any(other[i] > mine[i] for name, other in scores.items() if name != "ai-bunker")
    ]
    assert len(beaten) >= 2, f"nothing in the field beats this project at anything: {beaten}"
    assert "Isolates tool execution" in beaten
    assert "Provider breadth" in beaten
