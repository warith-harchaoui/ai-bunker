"""
The README's figures, held to the code they describe.

Why this exists
---------------
A diagram is a claim with no linter. `scripts/lint_claims.py` guards sentences
and `scripts/sync_counts.py` guards counts, and both exist because a statement
that was true and stopped being true has nothing to notice it. A picture is the
same statement with worse odds: the numbers are baked into coordinates, the
file is binary-ish to a reviewer, and nobody re-reads a chart they have already
approved.

So three things are checked here, and the first is the one that matters:

1. **Every committed figure is exactly what the generator renders.** Edit the
   SVG by hand and this fails; change the palette and forget to regenerate and
   this fails.
2. **The numbers in the figures agree with the code.** The settle order drawn
   in `figure-plan.svg` is `resolve_plan`'s order, the overhead is
   `engine.OVERHEAD_GIB`, the anti-greed tolerance quoted on the vision row is
   `engine.LEAN_TOLERANCE`, and the seconds-per-image curve is monotone in
   bandwidth because it is a roofline.
3. **Both halves of the repository carry them.** `README.md` and `LISEZMOI.md`
   are twins; a figure that existed in one would be the first place they
   stopped being.

And a fourth, added after the audit reported a figure clean while two of its
labels had a dashed gridline through them:

4. **The legibility gate can fail.** `scripts/audit_figures.py` grew a
   geometry half -- rules through words, labels on labels, text off the canvas
   -- and a gate nobody has seen fail is a gate nobody should trust, so it is
   fed a planted collision here as well as the real figures.

What is deliberately NOT here
-----------------------------
Contrast, and the geometry run over the committed files: `audit_figures.py`
owns both, for both schemes and for the site's figures as well as these, and
it is a continuous-integration step in its own right. What this file adds is
the proof that the step is capable of going red.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.engine import LEAN_TOLERANCE, OVERHEAD_GIB


def _figures():
    """`scripts/make_figures.py`, imported by path.

    `scripts/` holds programs rather than a package, so there is no name to
    import and the path is the honest spelling.
    """
    path = ROOT / "scripts" / "make_figures.py"
    spec = importlib.util.spec_from_file_location("make_figures", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def figures():
    return _figures()


def test_every_committed_figure_is_what_the_generator_renders(figures):
    """The drift guard, and the reason the generator exists at all.

    A figure edited by hand is a figure whose numbers no longer come from
    anywhere, and an SVG is the last file in a repository anybody re-reads.
    """
    stale = [
        path.relative_to(ROOT)
        for path, svg in figures.files().items()
        if not path.exists() or path.read_text(encoding="utf-8") != svg
    ]
    assert not stale, f"run: python scripts/make_figures.py — stale: {stale}"


def test_each_figure_carries_its_own_text_alternative(figures):
    """`role="img"` plus a `<title>` and a `<desc>`, and the description has to
    be a description.

    A `<desc>` that repeats the title is the alt-text equivalent of
    `alt="image"`: it satisfies the parser and tells a reader nothing. The
    floor is that it is substantially longer than the title, and that the two
    figures carrying data say what the data is -- a chart described without
    its numbers has been described to everyone except the person who needed
    the description. `pipeline` is exempt and is a diagram, not a chart: it
    plots nothing, and demanding a digit of it would be a rule met by writing
    one in.
    """
    charts = {"plan", "trade"}
    for path, svg in figures.files().items():
        name = path.name
        assert 'role="img"' in svg, name
        title = re.search(r"<title id=\"[\w-]+\">(.+?)</title>", svg, re.S)
        desc = re.search(r"<desc id=\"[\w-]+\">(.+?)</desc>", svg, re.S)
        assert title and desc, name
        assert len(desc.group(1)) > len(title.group(1)) * 2, f"{name}: the desc restates"
        if any(name.startswith(f"figure-{kind}") for kind in charts):
            assert re.search(r"\d", desc.group(1)), f"{name}: a chart's desc carries its figures"
        assert "var(--" not in svg, f"{name}: a renderer that drops var() draws this blank"


def test_the_plan_figure_draws_the_order_resolve_plan_settles_in(figures):
    """The figure's whole argument is the order, so the order has to be the
    code's.

    `resolve_plan` settles the embedder, then vision, then the picture, and
    gives the coder what is left -- which is why asking for pictures on an
    80 GiB card costs the coder the 80B and not the other way round. If that
    order ever changes, the drawing is wrong in the one way nobody would spot.
    """
    assert figures.ORDER == ("embed", "vision", "image", "code")

    rows = dict((key, gib) for key, gib, _tone in figures.PLAN)
    assert rows["overhead"] == OVERHEAD_GIB, "the reserve drawn is the reserve reserved"
    assert sum(rows.values()) == pytest.approx(80.0), "the parts have to be the whole card"

    svg = figures.plan(figures.STRINGS["plan"]["en"])
    assert f"within {LEAN_TOLERANCE:g} points" in svg, "the vision row quotes the real rule"
    # The coder is drawn last and is the only slot described as the remainder.
    assert "the remainder" in svg


def test_the_trade_figure_is_a_roofline_and_says_which_machines_pay_twice(figures):
    """Seconds per image falls as bandwidth rises, because a denoising loop
    reads its weights out of memory like everything else.

    The two machines where the picture also costs the coder are marked twice:
    a red dot and red type. The grey suffix that used to say it in words was
    the second of two stacked labels per point, and a stacked pair is two
    chances to land on a gridline -- which it took. The footnote carries the
    sentence now, so a reader who cannot distinguish the red still has it.
    """
    bandwidths = [bw for _k, bw, _s, _f in figures.TRADE]
    seconds = [sec for _k, _bw, sec, _f in figures.TRADE]
    assert bandwidths == sorted(bandwidths), "ordered by bandwidth, or the curve lies"
    assert seconds == sorted(seconds, reverse=True), "more bandwidth, less waiting"

    svg = figures.trade(figures.STRINGS["trade"]["en"])
    lost = [key for key, _bw, _s, fits in figures.TRADE if not fits]
    assert lost, "the figure exists to show this case"
    assert svg.count('class="dot-red"') == len(lost)
    assert svg.count('class="t red"') == len(lost), "red type, not only a red dot"
    assert "Red: the picture fits" in svg, "the colour is explained in words"


def test_the_budget_figure_is_the_arithmetic_the_readme_quotes(figures):
    """The founding story, and the only part of it a reader can check by eye.

    Both columns have to sum to the window or the figure is a drawing with
    numbers on it. The looping session's floor has to be past the compaction
    trigger -- that is the entire argument, and if the constants ever drift so
    that it is not, the bar stops crossing the line and nothing else in the
    figure would say so.
    """
    works, loops = figures.BUDGETS["works"], figures.BUDGETS["loops"]
    assert sum(works) < figures.TRIGGER, "the working session leaves room to work"
    assert sum(loops) > figures.TRIGGER, "the looping session is the one past the line"
    assert figures.TRIGGER < figures.WINDOW, "compaction fires inside the window"

    svg = figures.budget(figures.STRINGS["budget"]["en"])
    assert f"{figures.WINDOW:,}" in svg, "the total is printed, so the table can be checked"
    # Twice: the segment in the looping bar, and its row in the key. The
    # working session has none -- red is the state, not a decoration.
    assert svg.count('class="seg-red"') == 2
    assert 'class="seg-red" x="795.6" y="222.0"' in svg, "the red is in the looping bar"


#: Which twin pair each figure belongs in. A figure has one home and both
#: halves of it: the four that explain the product live in the README, and the
#: one that places the field lives beside the field.
HOMES = {
    "pipeline": ("README.md", "LISEZMOI.md"),
    "plan": ("README.md", "LISEZMOI.md"),
    "trade": ("README.md", "LISEZMOI.md"),
    "budget": ("README.md", "LISEZMOI.md"),
    "path": ("LANDSCAPE.md", "PAYSAGE.md"),
}


def test_both_language_halves_carry_the_same_figures(figures):
    """A figure in one half and not the other is where two twins stop being
    twins, and `tests/test_bilingual.py` counts sections rather than pictures,
    so it would not notice.

    `HOMES` is asserted to cover the generator rather than merely consulted:
    a figure added without a home would otherwise be a figure this test
    silently skips, which is the failure mode of every lookup table that is
    allowed to be incomplete.
    """
    assert set(HOMES) == set(figures.STRINGS), "every figure needs a home, and only one"

    for name, (en_doc, fr_doc) in HOMES.items():
        assert f"assets/figure-{name}.svg" in (ROOT / en_doc).read_text(encoding="utf-8"), name
        assert f"assets/figure-{name}.fr.svg" in (ROOT / fr_doc).read_text(encoding="utf-8"), name

    # Referenced with a text alternative, not a bare link: an image whose alt
    # text is empty is an image a screen reader announces as nothing at all.
    for half in {doc for pair in HOMES.values() for doc in pair}:
        text = (ROOT / half).read_text(encoding="utf-8")
        for alt, target in re.findall(r"!\[(.*?)\]\((assets/figure-[\w.-]+\.svg)\)", text, re.S):
            assert (ROOT / target).exists(), f"{half}: {target} is missing"
            assert len(alt) > 80, f"{half}: {target} has a stub for alt text"


def test_no_figure_is_referenced_that_the_generator_does_not_own(figures):
    """The other direction: a file left in `assets/` after a figure was
    renamed is a file that goes on being served and stops being regenerated."""
    owned = {path.name for path in figures.files()}
    on_disk = {p.name for p in (ROOT / "assets").glob("figure-*.svg")}
    assert on_disk == owned, f"orphaned: {sorted(on_disk - owned)}"


def test_the_legibility_gate_catches_a_rule_through_a_word(tmp_path):
    """The audit's geometry half, shown failing.

    Two labels in `figure-trade.svg` had a dashed gridline through them for a
    round while the figure audit printed `all pairs meet the 4.5:1 floor`.
    Contrast was never what was wrong, and the half that would have caught it
    did not exist. It does now -- so it is given each defect it is meant to
    find, one at a time, and has to report every one.

    `clean` is checked first and on purpose: a detector that reports
    everything is as useless as one that reports nothing, and the committed
    figures are the specimen that must stay quiet.
    """
    spec = importlib.util.spec_from_file_location(
        "audit_figures", ROOT / "scripts" / "audit_figures.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    def figure(body: str) -> pathlib.Path:
        path = tmp_path / "f.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
            "<style>text { font-size: 12px; } .s { font-size: 11.5px; }</style>"
            f"{body}</svg>",
            encoding="utf-8",
        )
        return path

    clean = figure('<path class="dash" d="M20 40 H380"/><text x="40" y="100">Fine</text>')
    assert audit.audit_geometry(clean, quiet=True) == []

    struck = figure('<path class="dash" d="M20 100 H380"/><text x="40" y="100">Struck</text>')
    assert "crosses" in "".join(audit.audit_geometry(struck, quiet=True))

    upright = figure('<path class="dash" d="M60 20 V180"/><text x="40" y="100">Struck</text>')
    assert "x=60.0" in "".join(audit.audit_geometry(upright, quiet=True))

    stacked = figure('<text x="40" y="100">Over</text><text x="50" y="102">Under</text>')
    assert "overlaps" in "".join(audit.audit_geometry(stacked, quiet=True))

    overrun = figure('<text x="380" y="100">A label far wider than the canvas</text>')
    assert "leaves the" in "".join(audit.audit_geometry(overrun, quiet=True))


# ---------------------------------------------------------------------------
# The width model: per character, out of the fonts, and tracking included.
# ---------------------------------------------------------------------------


def _audit():
    """`scripts/audit_figures.py`, imported by path."""
    spec = importlib.util.spec_from_file_location(
        "audit_figures", ROOT / "scripts" / "audit_figures.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_advance_table_describes_the_font_stack_the_figures_ask_for():
    """The drift guard that needs no fonts.

    `scripts/measure_advances.py` reads the widths out of Roboto, Helvetica
    Neue, Helvetica and Arial, which means it needs those fonts and
    `fontTools` — neither of which the lane has, and neither of which it
    should. What it writes is committed, and this is what keeps the committed
    file describing the right fonts: the table records the stack it measured,
    and the day `make_figures.FONT` names a different one, this fails and says
    to re-measure.
    """
    figures = _figures()
    table = _audit().ADVANCES
    assert table["font_stack"] == figures.FONT, (
        "the figures changed font stack; run scripts/measure_advances.py"
    )
    assert table["faces"], "a table measured from no faces bounds nothing"


def test_every_weight_the_stylesheet_declares_has_been_measured():
    """A class can declare `font-weight: 800` in one edit, and a weight the
    table does not carry would silently fall through to the widest and
    narrowest advance in the whole table — a bound so loose it reports
    nothing. So the stylesheet's own weights are compared against the table's.
    """
    audit = _audit()
    style = (ROOT / "assets" / "figure-plan.svg").read_text(encoding="utf-8")
    declared = {int(w) for w in re.findall(r"font-weight:\s*(\d+)", style)} | {400}
    assert declared <= {int(w) for w in audit.PER_WEIGHT}, (
        f"the figures declare weights the advance table has no widths for: "
        f"{declared - {int(w) for w in audit.PER_WEIGHT}}"
    )


def test_every_character_in_every_figure_has_a_measured_width():
    """Coverage, asserted rather than hoped for.

    The committed figures carry French accents, an em dash, a middle dot, a
    narrow no-break space and an arrow. A character the table misses does not
    make the audit wrong — the bound widens to the extremes of the whole table
    — but it makes it useless for that label, silently. The audit reports it
    and this is the test that the figures as committed never trip it.
    """
    audit = _audit()
    for figure in sorted((ROOT / "assets").glob("figure-*.svg")):
        findings = [f for f in audit.audit_geometry(figure, quiet=True) if "no width for" in f]
        assert findings == [], "\n".join(findings)


def test_letter_spacing_is_part_of_a_label_width():
    """The defect this round found, in one assertion.

    `.n` declares `letter-spacing: .1em` and `.h` declares `.08em`, and the
    width model ignored both. That is not imprecision, it is an unsound bound:
    the collision test asks for the *widest* a string could be, and for every
    capitalised letter-spaced label — thirty-six of them in the committed
    figures — the answer it got was about a third narrower than the label
    actually renders. A bound in the wrong direction cannot miss politely; it
    misses a rule through a word.
    """
    audit = _audit()
    rules = audit._type_rules(
        "text { font-size: 12px; } .n { font-size: 11px; font-weight: 700; letter-spacing: .1em; }"
    )
    assert audit._type_of("n", rules) == (11.0, 700, 0.1)
    assert audit._type_of("", rules) == (12.0, 400, 0.0)

    plain = audit._text_width("ORDER", 11.0, 700, 0.0, True)
    spaced = audit._text_width("ORDER", 11.0, 700, 0.1, True)
    assert spaced > plain
    assert spaced - plain == pytest.approx(5 * 11.0 * 0.1)

    # And the narrow bound does not pay for the space after the last
    # character, because implementations disagree about it and a bound must
    # not depend on which is right.
    assert audit._text_width("ORDER", 11.0, 700, 0.1, False) - audit._text_width(
        "ORDER", 11.0, 700, 0.0, False
    ) == pytest.approx(4 * 11.0 * 0.1)


def test_the_width_model_knows_an_l_from_a_w():
    """What replacing one number with two hundred actually bought.

    The old model gave every character the same advance, so `llll` and `WWWW`
    were the same width. They are not: a lower-case `l` is a little over a
    fifth of an em and a capital `W` is nearly a whole one.
    """
    audit = _audit()
    narrow = audit._text_width("llllllll", 12.0, 400, 0.0, True)
    wide = audit._text_width("WWWWWWWW", 12.0, 400, 0.0, True)
    assert wide > 3 * narrow

    # And the bound is still a bound in both directions, for every character.
    for weight, chars in audit.PER_WEIGHT.items():
        for char, (low, high) in chars.items():
            assert 0 < low <= high <= 1.1, f"{char!r} at weight {weight} measures {low}..{high}"


def test_the_audit_catches_a_rule_under_a_letter_spaced_heading(tmp_path):
    """The specimen neither older model could see, with the arithmetic shown.

    One heading, `WHERE A TURN IS READ`, at 13px in the `.h` class — capitals,
    weight 600, `letter-spacing: .08em`. Its widest possible extent from
    x=40 is:

        40..183.0   one average advance for every character (the old model)
        40..198.8   per-character advances, letter-spacing ignored
        40..219.6   per-character advances, letter-spacing paid for

    So a dashed rule starting at x=205 runs through the last three words of a
    heading that renders to 219, and both earlier models called the figure
    clean — not by a hair, by twenty pixels. A bound that lands short is not a
    loose bound, it is the wrong answer: the collision test exists to be told
    the *widest* a string can be.
    """
    audit = _audit()

    def figure(rule_from: float) -> pathlib.Path:
        path = tmp_path / f"heading-{rule_from:g}.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
            "<style>text { font-size: 12px; }"
            " .h { font-size: 13px; font-weight: 600; letter-spacing: .08em; }</style>"
            f'<path class="dash" d="M{rule_from:g} 100 H390"/>'
            '<text class="h" x="40" y="100">WHERE A TURN IS READ</text></svg>',
            encoding="utf-8",
        )
        return path

    heading = "WHERE A TURN IS READ"
    tracked = audit._text_width(heading, 13.0, 600, 0.08, True)
    untracked = audit._text_width(heading, 13.0, 600, 0.0, True)
    uniform = len(heading) * 13.0 * 0.55

    assert uniform < untracked < tracked, (uniform, untracked, tracked)

    # Beyond what the old uniform advance could reach, inside what the
    # per-character widths give.
    assert any("crosses" in f for f in audit.audit_geometry(figure(40 + uniform + 5), quiet=True))

    # And beyond even that, reachable only once letter-spacing is paid for.
    only_tracking = 40 + untracked + 5
    assert only_tracking < 40 + tracked
    assert any("crosses" in f for f in audit.audit_geometry(figure(only_tracking), quiet=True))

    # The figure stays clean when the rule really is past the label, which is
    # what keeps the test above from passing for the wrong reason.
    assert audit.audit_geometry(figure(40 + tracked + 5), quiet=True) == []
