"""Get started — English."""

TITLE = "Get started — ai-bunker"
DESCRIPTION = (
    "Install, size the machine, serve the gateway, point a client at it, and "
    "equip a repository. Every command with its real output."
)

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "HowTo",
    "name": "Set up a sovereign LLM gateway for coding agents",
    "description": "Install ai-bunker, size the machine, serve the gateway, point an OpenAI-compatible client at it, and equip a repository with a charter.",
    "step": [
      {"@type": "HowToStep", "name": "Install", "text": "Clone the repository and pip install with the api extra."},
      {"@type": "HowToStep", "name": "Size the machine", "text": "Run ai-bunker recommend --team N to see which machine carries the team, then ai-bunker sizing to get the vllm serve command."},
      {"@type": "HowToStep", "name": "Configure and check", "text": "Copy config/gateway.example.yaml, set an API key, and run ai-bunker doctor to verify everything the deployment claims."},
      {"@type": "HowToStep", "name": "Serve", "text": "Run ai-bunker serve, then point any OpenAI-compatible client at the gateway."},
      {"@type": "HowToStep", "name": "Equip a repository", "text": "Run ai-bunker adopt to write the charter and a thin client kit."}
    ]
  }
  </script>"""

BODY = r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Get started</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        From nothing to a gateway
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        Five steps. Every block below is real output — the project's own rule is that a claim is
        a measurement or it is removed, and that applies to its documentation too.
      </p>
    </section>

    <section class="mx-auto max-w-6xl px-5 pb-16">
      <ol class="space-y-10">

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">01</span>Install
          </h2>
          <p class="mt-3 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Python 3.10–3.13 and git. A GPU is needed only on the machine that <em>serves</em>;
            clients need neither.
          </p>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>git clone https://github.com/warith-harchaoui/ai-bunker.git
cd ai-bunker
python3 -m venv .venv &amp;&amp; source .venv/bin/activate
pip install -e ".[api]"</code></pre>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">02</span>Find out what you need
          </h2>
          <p class="mt-3 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Before buying anything. The cheapest answer is often the machine you already own,
            which is in the catalogue at $0 so that "buy nothing" is a costed option rather than
            a shrug.
          </p>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>$ ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b

  LOAD MODEL
    each person decodes 25% of a session, 50% of the team is in session at peak
    → 95th percentile of Binomial(2, 0.125) = 2 concurrent sequences
    the machine must sustain 2 sequence(s) above 20 tok/s

  ✔ BUY
      Apple MacBook Pro M2 Max 96GB (existing)
      90 GiB · 400 GB/s · $0
      carries 5 sequences (needs 2) at 20 tok/s each, 27 tok/s alone</code></pre>
          <p class="mt-4 text-sm text-neutral-500 dark:text-neutral-400">
            <a href="sizing.html" class="text-brand-linktext hover:underline">Why the sizing works this way →</a>
          </p>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">03</span>Configure, and check the claims
          </h2>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>cp config/gateway.example.yaml config/gateway.yaml
export AI_BUNKER_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

$ ai-bunker doctor
  [ok  ] charter carries operating rules
  [ok  ] 17 rules loaded
  [ok  ] 107 rule assertions pass
  [ok  ] 100% of rules carry evidence
  [WARN] upstream local answers at http://127.0.0.1:8001/v1   not reachable
  [ok  ] no route leaves this network
  12/14 checks pass</code></pre>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            <code class="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm dark:bg-neutral-800">doctor</code>
            reports what the deployment <em>actually</em> does, including that a gateway without
            an API key is open to anyone who can reach it. Open by accident and open on purpose
            look identical from outside; this is what tells them apart.
          </p>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">04</span>Serve, and point a client at it
          </h2>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>ai-bunker serve                      # localhost:8000

export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="$AI_BUNKER_API_KEY"</code></pre>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            That is the whole client configuration. Any client that speaks OpenAI now gets the
            charter, the rule engine and the budget without being configured for them.
          </p>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            The dashboard is at
            <code class="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm dark:bg-neutral-800">/gui</code>:
          </p>
          <figure class="mt-5">
            <img src="img/dashboard.png" width="1800" height="1290" loading="lazy"
              alt="The ai-bunker dashboard. A bar across the top shows the session floor as a small orange segment against a mostly green window, labelled 'floor 607 — under 1% of the window' and '193,108 left to work with'. Below it a second bar breaks the floor into its components, and a table lists each component with its token count and owner. A panel on the right reports the served and declared context and says the count came from the server's tokenizer."
              class="w-full rounded-2xl border border-neutral-200 dark:border-neutral-800">
            <figcaption class="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
              Two bars rather than one: a 300:1 ratio and a composition are two different
              questions, and one bar cannot carry both.
            </figcaption>
          </figure>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">05</span>Equip a repository
          </h2>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>$ ai-bunker adopt /path/to/project --list
Adopting ai-bunker into /path/to/project:
  + charter/AGENTS.md   (how to work here, injected every request)
  + charter/packs   (the standards pages, read on demand)
  + charter/rules   (the rules, with their own evidence)
  + opencode.json   (points at the gateway)
  + .opencode/plugins/bounded-reads.js   (the one thing the gateway cannot do)
  + .claude/settings.ai-bunker.json   (merge into .claude/settings.json)
  + CLAUDE.md   (what the gateway does to a session)</code></pre>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Nothing is overwritten without <code class="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm dark:bg-neutral-800">--force</code>.
            The client kit is deliberately <strong class="font-semibold">one config and one
            plugin</strong>: everything the gateway can see, the gateway enforces, so a kit
            carries only what happens <em>before a request exists</em> — bounded reads, no skill
            injection, compaction thresholds.
          </p>
        </li>

      </ol>

      <div class="mt-14 rounded-2xl border border-neutral-200 bg-neutral-50 p-6 dark:border-neutral-800 dark:bg-neutral-900/40">
        <h2 class="font-serif text-xl font-semibold tracking-tight">Before you depend on it</h2>
        <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">
          This is <code class="font-mono text-sm">0.1.0-alpha</code>: 383 tests and a green CI
          gate, next to projects with years of production use. Command screening does not apply
          to streamed completions, and <code class="font-mono text-sm">/health</code> reports
          which guarantees are live rather than implying all of them are.
        </p>
        <p class="mt-4">
          <a href="https://github.com/warith-harchaoui/ai-bunker/blob/main/EXAMPLES.md"
            class="font-medium text-brand-linktext hover:underline">Every command, with its real output →</a>
        </p>
      </div>
    </section>
"""
