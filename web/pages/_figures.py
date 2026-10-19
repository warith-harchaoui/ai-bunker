"""
Hand-authored inline SVG for the site.

No chart library and no raster image: these are drawn directly, so they stay
sharp at any zoom, respond to the theme through `currentColor` and the page's
own `--brand-*` tokens, and carry a text alternative rather than an alt string
that repeats the caption.

Each figure takes a `t` dict of strings so the French and English pages share
one drawing. Geometry lives here; wording lives in the page.
"""


def flow(t: dict[str, str]) -> str:
    """A request crossing the gateway, with the four stages marked.

    The point the diagram has to make, and prose does not: stages 1 and 4 are
    the *same rule engine* at the two ends of a turn, and a gateway is the only
    position from which both are visible.
    """
    return f"""
<figure class="mt-10">
  <svg viewBox="0 0 880 420" class="w-full max-w-4xl" role="img"
       aria-labelledby="flow-t flow-d" style="color: rgb(var(--brand-blue-rgb))">
    <title id="flow-t">{t["title"]}</title>
    <desc id="flow-d">{t["desc"]}</desc>

    <defs>
      <marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
        <path d="M0 0 L10 5 L0 10 z" fill="currentColor"/>
      </marker>
      <marker id="arw-dim" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
        <path d="M0 0 L10 5 L0 10 z" fill="#9A9AA2"/>
      </marker>
    </defs>

    <!-- The band, with a gutter on its left reserved for the bracket. Two
         earlier layouts put that bracket outside the band and then across
         stage 3; both collisions were only visible once rendered. -->
    <rect x="228" y="30" width="430" height="360" rx="16"
          fill="currentColor" fill-opacity=".05" stroke="currentColor" stroke-opacity=".3"/>
    <text x="443" y="56" text-anchor="middle" font-size="13" font-weight="600"
          fill="currentColor" letter-spacing=".08em">{t["gateway"]}</text>

    <rect x="14" y="150" width="170" height="120" rx="14" fill="none"
          stroke="#9A9AA2" stroke-width="1.5"/>
    <text x="99" y="200" text-anchor="middle" font-size="15" font-weight="600" fill="currentColor">{t["client"]}</text>
    <text x="99" y="222" text-anchor="middle" font-size="11" fill="#8A8A92">{t["client_sub"]}</text>

    <rect x="700" y="150" width="150" height="120" rx="14" fill="none"
          stroke="#9A9AA2" stroke-width="1.5"/>
    <text x="775" y="200" text-anchor="middle" font-size="15" font-weight="600" fill="currentColor">{t["engine"]}</text>
    <text x="775" y="222" text-anchor="middle" font-size="11" fill="#8A8A92">{t["engine_sub"]}</text>

    <path d="M184 184 H228" stroke="currentColor" stroke-width="2" fill="none" marker-end="url(#arw)"/>
    <path d="M658 184 H700" stroke="currentColor" stroke-width="2" fill="none" marker-end="url(#arw)"/>
    <path d="M700 240 H658" stroke="#9A9AA2" stroke-width="2" fill="none" marker-end="url(#arw-dim)"/>
    <path d="M228 240 H184" stroke="#9A9AA2" stroke-width="2" fill="none" marker-end="url(#arw-dim)"/>

    <g>
      <rect x="284" y="80" width="172" height="86" rx="12" fill="rgb(var(--brand-orange-rgb))" fill-opacity=".10"
            stroke="rgb(var(--brand-orange-rgb))" stroke-opacity=".5"/>
      <text x="298" y="102" font-size="11" font-weight="700" fill="rgb(var(--brand-orange-rgb))" letter-spacing=".1em">01</text>
      <text x="298" y="124" font-size="13" font-weight="600" fill="currentColor">{t["s1"]}</text>
      <text x="298" y="144" font-size="11.5" fill="#8A8A92">{t["s1a"]}</text>
      <text x="298" y="159" font-size="11.5" fill="#8A8A92">{t["s1b"]}</text>
    </g>
    <g>
      <rect x="472" y="80" width="172" height="86" rx="12" fill="currentColor" fill-opacity=".10"
            stroke="currentColor" stroke-opacity=".45"/>
      <text x="486" y="102" font-size="11" font-weight="700" fill="currentColor" letter-spacing=".1em">02</text>
      <text x="486" y="124" font-size="13" font-weight="600" fill="currentColor">{t["s2"]}</text>
      <text x="486" y="144" font-size="11.5" fill="#8A8A92">{t["s2a"]}</text>
      <text x="486" y="159" font-size="11.5" fill="#8A8A92">{t["s2b"]}</text>
    </g>
    <g>
      <rect x="284" y="196" width="360" height="76" rx="12" fill="currentColor" fill-opacity=".10"
            stroke="currentColor" stroke-opacity=".45"/>
      <text x="298" y="218" font-size="11" font-weight="700" fill="currentColor" letter-spacing=".1em">03</text>
      <text x="298" y="240" font-size="13" font-weight="600" fill="currentColor">{t["s3"]}</text>
      <text x="298" y="259" font-size="11.5" fill="#8A8A92">{t["s3a"]}</text>
      <text x="630" y="240" text-anchor="end" font-size="12" font-weight="600"
            fill="rgb(var(--brand-red-rgb))">{t["s3_refuse"]}</text>
    </g>
    <g>
      <rect x="284" y="300" width="360" height="76" rx="12" fill="rgb(var(--brand-red-rgb))" fill-opacity=".08"
            stroke="rgb(var(--brand-red-rgb))" stroke-opacity=".45"/>
      <text x="298" y="322" font-size="11" font-weight="700" fill="rgb(var(--brand-red-rgb))" letter-spacing=".1em">04</text>
      <text x="298" y="344" font-size="13" font-weight="600" fill="currentColor">{t["s4"]}</text>
      <text x="298" y="363" font-size="11.5" fill="#8A8A92">{t["s4a"]}</text>
      <text x="630" y="344" text-anchor="end" font-size="12" font-weight="600"
            fill="rgb(var(--brand-red-rgb))">{t["s4_refuse"]}</text>
    </g>

    <!-- The claim the diagram exists to make, in its own gutter. -->
    <path d="M276 123 Q258 123 258 228 Q258 338 276 338" fill="none"
          stroke="rgb(var(--brand-orange-rgb))" stroke-width="1.5" stroke-dasharray="4 4" stroke-opacity=".8"/>
    <text x="248" y="230" font-size="10.5" font-weight="600" text-anchor="middle"
          fill="rgb(var(--brand-orange-rgb))" transform="rotate(-90 248 230)">{t["same1"]} {t["same2"]}</text>
  </svg>
  <figcaption class="mt-4 max-w-3xl text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">{t["caption"]}</figcaption>
</figure>
"""


def roofline(t: dict[str, str]) -> str:
    """Tokens per second against memory bandwidth, with the comfort floor.

    Three models at a measured efficiency, so the two conclusions are visible
    rather than asserted: the mixture-of-experts line sits far above the dense
    one, and the Spark's bandwidth puts it under the floor whatever it loads.
    """

    # y = 0.70 * bw / active_gib, plotted on a 0..900 GB/s, 0..120 tok/s frame.
    def pts(active_gib: float) -> str:
        out = []
        for bw in range(0, 921, 46):
            tps = 0.70 * bw / active_gib
            x = 92 + bw / 920 * 700
            y = 330 - min(tps, 120) / 120 * 280
            out.append(f"{x:.0f},{y:.0f}")
        return " ".join(out)

    def mark(bw: float, active: float) -> tuple[float, float]:
        tps = 0.70 * bw / active
        return 92 + bw / 920 * 700, 330 - min(tps, 120) / 120 * 280

    spark_x, spark_y = mark(273, 25)
    m3_x, m3_y = mark(819, 9)
    studio_dense_x, studio_dense_y = mark(819, 25)

    # House style: no gridlines, no tick marks, no top or right spine. Tick
    # numbers in the mono face with tabular figures so columns of digits line
    # up rather than shimmer.
    yticks = "".join(
        f'<text x="84" y="{330 - v / 120 * 280 + 4:.0f}" text-anchor="end" font-size="11" '
        f'font-family="Roboto Mono, ui-monospace, monospace" style="font-variant-numeric:tabular-nums" '
        f'fill="#8A8A92">{v}</text>'
        for v in (0, 30, 60, 90, 120)
    )
    xticks = "".join(
        f'<text x="{92 + v / 920 * 700:.0f}" y="352" text-anchor="middle" font-size="11" '
        f'font-family="Roboto Mono, ui-monospace, monospace" style="font-variant-numeric:tabular-nums" '
        f'fill="#8A8A92">{v}</text>'
        for v in (0, 273, 546, 819)
    )
    return f"""
<figure class="mt-10">
  <svg viewBox="-6 0 826 400" class="w-full max-w-3xl" role="img"
       aria-labelledby="roof-t roof-d" style="color: rgb(var(--brand-blue-rgb))">
    <title id="roof-t">{t["title"]}</title>
    <desc id="roof-d">{t["desc"]}</desc>
    {yticks}
    <line x1="92" y1="50" x2="92" y2="330" stroke="#9A9AA2" stroke-opacity=".45"/>
    <line x1="92" y1="330" x2="792" y2="330" stroke="#9A9AA2" stroke-opacity=".45"/>
    {xticks}
    <text x="442" y="378" text-anchor="middle" font-size="12" fill="#8A8A92">{t["x"]}</text>
    <text x="30" y="190" font-size="12" fill="#8A8A92" transform="rotate(-90 30 190)" text-anchor="middle">{t["y"]}</text>
    <text x="46" y="190" font-size="10.5" fill="#8A8A92" transform="rotate(-90 46 190)" text-anchor="middle">{t["polarity"]}</text>

    <!-- the comfort floor -->
    <line x1="92" y1="{330 - 20 / 120 * 280:.0f}" x2="792" y2="{330 - 20 / 120 * 280:.0f}"
          stroke="rgb(var(--brand-red-rgb))" stroke-width="1.5" stroke-dasharray="6 4"/>
    <!-- Anchored at the left end: both lines are still under the floor there,
         so the label sits in open space. At the right end it landed on the
         dense line, which the render showed as text struck through. -->
    <text x="100" y="{330 - 20 / 120 * 280 - 9:.0f}" font-size="11.5"
          font-weight="600" fill="rgb(var(--brand-red-rgb))">{t["floor"]}</text>

    <polyline points="{pts(9)}" fill="none" stroke="currentColor" stroke-width="2.5"/>
    <polyline points="{pts(25)}" fill="none" stroke="#8A8A92" stroke-width="2.5" stroke-dasharray="7 4"/>

    <circle cx="{m3_x:.0f}" cy="{m3_y:.0f}" r="5" fill="currentColor"/>
    <text x="{m3_x - 10:.0f}" y="{m3_y - 12:.0f}" text-anchor="end" font-size="12" font-weight="600" fill="currentColor">{t["p_m3"]}</text>
    <!-- Both dense-model points sit within a few pixels of the comfort-floor
         line, so a label placed below either of them lands on it. Rendered,
         that read as text struck through by a dashed rule. Both now sit above
         their point, where the gap to the MoE line is wide. -->
    <circle cx="{studio_dense_x:.0f}" cy="{studio_dense_y:.0f}" r="5" fill="#8A8A92"/>
    <text x="{studio_dense_x - 12:.0f}" y="{studio_dense_y - 12:.0f}" text-anchor="end" font-size="12" fill="#8A8A92">{t["p_dense"]}</text>
    <circle cx="{spark_x:.0f}" cy="{spark_y:.0f}" r="5" fill="rgb(var(--brand-red-rgb))"/>
    <text x="{spark_x - 12:.0f}" y="{spark_y - 10:.0f}" text-anchor="end" font-size="12" font-weight="600" fill="rgb(var(--brand-red-rgb))">{t["p_spark"]}</text>

    <g transform="translate(330,62)">
      <line x1="0" y1="0" x2="26" y2="0" stroke="currentColor" stroke-width="2.5"/>
      <text x="34" y="4" font-size="12" fill="currentColor">{t["l_moe"]}</text>
      <line x1="0" y1="20" x2="26" y2="20" stroke="#8A8A92" stroke-width="2.5" stroke-dasharray="7 4"/>
      <text x="34" y="24" font-size="12" fill="#8A8A92">{t["l_dense"]}</text>
    </g>
  </svg>
  <figcaption class="mt-4 max-w-3xl text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">{t["caption"]}</figcaption>
</figure>
"""


def floor_bar(t: dict[str, str]) -> str:
    """The session floor against the window, at two scales.

    One bar cannot carry a 300:1 ratio and a composition at once — the same
    problem the dashboard hit — so there are two, each honest at its own scale.
    """
    items = [
        ("tool schemas (7)", 2875, "orange"),
        ("client system prompt", 960, "orange"),
        ("charter", 465, "blue"),
        ("knowledge index", 142, "blue"),
    ]
    floor = sum(v for _, v, _ in items)
    x, segs, labels = 92, [], []
    for i, (name, value, hue) in enumerate(items):
        w = value / floor * 700
        token = "--brand-orange-rgb" if hue == "orange" else "--brand-blue-rgb"
        segs.append(
            f'<rect x="{x:.1f}" y="118" width="{max(w - 2, 2):.1f}" height="40" rx="4" '
            f'fill="rgb(var({token}))" fill-opacity="{1 - 0.3 * (i % 2):.2f}"/>'
        )
        if w > 70:
            labels.append(
                f'<text x="{x + w / 2:.0f}" y="178" text-anchor="middle" font-size="11" fill="#8A8A92">{name}</text>'
                f'<text x="{x + w / 2:.0f}" y="193" text-anchor="middle" font-size="11.5" font-weight="600" fill="currentColor">{value:,}</text>'
            )
        x += w
    return f"""
<figure class="mt-10">
  <svg viewBox="0 0 820 230" class="w-full max-w-3xl" role="img"
       aria-labelledby="floor-t floor-d" style="color: rgb(var(--brand-blue-rgb))">
    <title id="floor-t">{t["title"]}</title>
    <desc id="floor-d">{t["desc"]}</desc>

    <text x="92" y="30" font-size="12" font-weight="600" fill="currentColor">{t["window"]}</text>
    <rect x="92" y="42" width="700" height="14" rx="7" fill="rgb(var(--brand-green-rgb))" fill-opacity=".18"/>
    <rect x="92" y="42" width="15" height="14" rx="7" fill="rgb(var(--brand-orange-rgb))"/>
    <text x="92" y="76" font-size="11.5" fill="#8A8A92">{t["floor_share"]}</text>
    <text x="792" y="76" text-anchor="end" font-size="11.5" fill="#8A8A92">{t["left"]}</text>

    <text x="92" y="108" font-size="12" font-weight="600" fill="currentColor">{t["made_of"]}</text>
    {"".join(segs)}
    {"".join(labels)}

    <g transform="translate(92,214)">
      <rect x="0" y="-9" width="10" height="10" rx="2" fill="rgb(var(--brand-orange-rgb))"/>
      <text x="16" y="0" font-size="11.5" fill="#8A8A92">{t["l_client"]}</text>
      <rect x="150" y="-9" width="10" height="10" rx="2" fill="rgb(var(--brand-blue-rgb))"/>
      <text x="166" y="0" font-size="11.5" fill="#8A8A92">{t["l_us"]}</text>
    </g>
  </svg>
  <figcaption class="mt-4 max-w-3xl text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">{t["caption"]}</figcaption>
</figure>
"""
