"""Landscape page — English."""

TITLE = "Landscape — where ai-bunker sits"
DESCRIPTION = (
    "The gateways route, the guardrails inspect, neither counts. A survey of "
    "LiteLLM, Portkey, Kong, NeMo Guardrails, Guardrails AI, LLM Guard and OPA, "
    "including where this project is behind."
)

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    "headline": "Where ai-bunker sits among LLM gateways and guardrail engines",
    "description": "A surveyed comparison of LLM gateways, guardrail libraries and policy engines, with a PCA positioning map and an explicit account of where ai-bunker is behind.",
    "author": {"@type": "Person", "name": "Warith Harchaoui"},
    "isPartOf": {"@type": "WebSite", "name": "ai-bunker", "url": "https://deraison.ai/ai-bunker/"},
    "mentions": [
      {"@type": "SoftwareApplication", "name": "LiteLLM"},
      {"@type": "SoftwareApplication", "name": "Portkey"},
      {"@type": "SoftwareApplication", "name": "Kong AI Gateway"},
      {"@type": "SoftwareApplication", "name": "NeMo Guardrails"},
      {"@type": "SoftwareApplication", "name": "Guardrails AI"},
      {"@type": "SoftwareApplication", "name": "LLM Guard"},
      {"@type": "SoftwareApplication", "name": "Open Policy Agent"}
    ]
  }
  </script>"""

BODY = r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Landscape</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        The gateways route.<br>The guardrails inspect.<br>Neither counts.
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        Tools that sit between a coding agent and a model, surveyed 2026-10-19. A tool optimised
        for a different job is not being criticised — and three of them are better than this
        project at something named below.
      </p>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-14">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Three clusters, and an empty corner</h2>
        <figure class="mt-8">
        <!-- `bg-white` is kept in dark mode on purpose. The map is a 96%
             transparent PNG with dark ink, produced by `standpoint`, which has
             no dark theme; dropping the white plate would not darken the chart,
             it would make it invisible. A bright card on a dark page is the
             lesser defect, and it is a choice rather than an oversight. -->
          <img src="img/landscape.png" width="1800" height="1391"
            alt="A positioning map produced by principal component analysis. The horizontal axis runs from Resourceful on the left to Vigilant on the right; the vertical from Secure at the bottom to Disciplined at the top. LiteLLM, Kong AI Gateway, Portkey, Bifrost, NeMo Guardrails, Guardrails AI and LLM Guard cluster on the left and centre. ToolHive and the Docker Model Context Protocol (MCP) Gateway sit at the lower right, with agent-scan, Open Policy Agent and client-side harness config near the centre right. ai-bunker sits alone in the top right."
            class="w-full rounded-2xl border border-neutral-200 bg-white dark:border-neutral-800">
          <figcaption class="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
            Read it as a shape, not a scoreboard. Produced by
            <a href="https://github.com/warith-harchaoui/standpoint" class="text-brand-linktext hover:underline">standpoint</a>
            from the ratings table, by PCA.
          </figcaption>
        </figure>
        <div class="mt-10 grid gap-5 md:grid-cols-3">
          <div class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <h3 class="font-semibold">Left — the gateways</h3>
            <p class="mt-3 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
              LiteLLM, Kong, Portkey. One OpenAI-shaped surface over a hundred providers, with
              keys, budgets, retries and observability — done very well. What they do not do is
              look at what the agent is reading or about to run: a tool result full of secrets
              and a <span class="font-mono text-xs">rm -rf ~</span> pass through as ordinary bytes.
            </p>
          </div>
          <div class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <h3 class="font-semibold">Right and below — the rule engines</h3>
            <p class="mt-3 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
              NeMo Guardrails, Guardrails AI, LLM Guard. They inspect content properly, and
              several do it better than this project. What they are not is a gateway: they are
              libraries you call, so an agent that does not call them is unprotected, and
              swapping harness loses them entirely.
            </p>
          </div>
          <div class="rounded-2xl border border-brand-blue/40 bg-brand-blue/5 p-6">
            <h3 class="font-semibold">Top right — empty except this</h3>
            <p class="mt-3 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
              Nobody else combines the gateway's position — every request, every client, no
              opt-out — with the rule engine's inspection and a budget the server counts. That is
              a claim about <em>coverage</em>, not about quality.
            </p>
          </div>
        </div>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-5 py-14">
      <h2 class="font-serif text-3xl font-semibold tracking-tight">Where this project is behind</h2>
      <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        Worth stating, since a landscape where one tool wins every column is a landscape nobody
        believes.
      </p>
      <dl class="mt-8 space-y-6">
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Provider breadth — LiteLLM, by a wide margin</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">A hundred
            providers against whatever you configure here. If the question is "call many providers
            through one client", LiteLLM is simply the answer — and ai-bunker can sit in front of
            it rather than compete.</dd>
        </div>
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Content classifiers — LLM Guard and Guardrails AI</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">Their scanners
            are trained models and curated validator hubs; this ships versioned regular
            expressions with an entropy gate. Reviewable, diffable and free to run — a deliberate
            trade, and on raw detection quality it is a trade, not a win.</dd>
        </div>
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Policy expressiveness and testing — OPA</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">Rego expresses
            conditions a regex cannot, and OPA's test tooling with coverage is better than
            <span class="font-mono text-sm">rules --check</span>. The idea of policy carrying its
            own tests was taken from there.</dd>
        </div>
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Maturity</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">This is
            <span class="font-mono text-sm">0.2.0-alpha</span> next to projects with years of
            production use.</dd>
        </div>
      </dl>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-14">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Ideas taken from the field</h2>
        <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          None of this was invented here, and saying so costs nothing.
        </p>
        <ul class="mt-8 grid gap-5 sm:grid-cols-2">
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">Open Policy Agent</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">Policy
              carries its own tests, and decisions are logged from day one. Both are now
              load-bearing here — and the first caught three wrong patterns before they reached a
              deployment.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">gitleaks</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">Regex
              <em>and</em> an entropy gate, plus per-rule allowlists. A scanner that cries wolf
              teaches its readers to ignore it.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">Microsoft's <em>spotlighting</em></p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">Mark
              retrieved content as data. Pattern matching catches clumsy injection attempts; the
              structural marking is what holds when the patterns miss.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">Agent-harness research</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">The
              "prevention versus cure" split: bound context structurally, or let it grow and
              compress. This project is prevention, moved server-side — which the taxonomy does
              not have a box for.</p>
          </li>
        </ul>
        <p class="mt-10">
          <a href="https://github.com/warith-harchaoui/ai-bunker/blob/main/LANDSCAPE.md"
            class="font-medium text-brand-linktext hover:underline">The full table, with a write-up per tool →</a>
        </p>
      </div>
    </section>
"""
