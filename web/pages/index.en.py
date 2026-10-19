"""Home page — English."""

import pathlib as _p
import sys

sys.path.insert(0, str(_p.Path(__file__).parent))
import _figures as F

FLOW = F.flow(
    {
        "title": "A request crossing the ai-bunker gateway",
        "desc": (
            "A client on the left sends a request to the gateway in the middle, which "
            "forwards it to the serving engine on the right. Inside the gateway, stage 1 "
            "screens inbound tool results, stage 2 injects the charter, stage 3 measures "
            "the budget and can refuse the request, and stage 4 screens the outbound tool "
            "calls and can refuse a command. A dashed line links stages 1 and 4, which are "
            "the two scopes of one rule engine."
        ),
        "gateway": "ai-bunker",
        "client": "Any OpenAI client",
        "client_sub": "Claude Code · OpenCode · curl",
        "engine": "Your GPU",
        "engine_sub": "vLLM, Ollama",
        "s1": "Screen what it reads",
        "s1a": "secrets out, injection in",
        "s1b": "mark the rest as data",
        "s2": "Serve the charter",
        "s2a": "index, not the pages",
        "s2b": "stable position, cacheable",
        "s3": "Measure the budget",
        "s3a": "with the engine's own tokenizer, not an estimate",
        "s3_refuse": "413 — names the culprit",
        "s4": "Screen what it runs",
        "s4a": "the command has not run yet",
        "s4_refuse": "refused as a tool result",
        "same1": "one rule engine,",
        "same2": "both ends of a turn",
        "caption": (
            "The order is load-bearing. Stages 1 and 4 are the same rule engine at the two "
            "ends of an agent's turn, and a gateway is the first position from which both "
            "are visible — a library called from an application sees neither reliably."
        ),
    }
)

TITLE = "ai-bunker — one GPU, one charter, every coding agent"
DESCRIPTION = (
    "A sovereign OpenAI-compatible gateway in front of your own GPU: a versioned "
    "charter, enforced rules, and a context budget the server counts with its own "
    "tokenizer instead of trusting the client's estimate."
)

EXTRA_HEAD = r"""
  <script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "name": "ai-bunker",
      "url": "https://deraison.ai/ai-bunker/",
      "description": "A sovereign OpenAI-compatible gateway in front of your own GPU: a versioned charter, enforced rules, and a context budget the server counts with its own tokenizer.",
      "inLanguage": [
        "en",
        "fr"
      ],
      "author": {
        "@type": "Person",
        "name": "Warith Harchaoui",
        "url": "https://linkedin.com/in/warith-harchaoui"
      }
    },
    {
      "@type": "SoftwareSourceCode",
      "name": "ai-bunker",
      "description": "Sovereign serving layer for coding agents: one GPU, one charter, a context budget the server actually counts.",
      "codeRepository": "https://github.com/warith-harchaoui/ai-bunker",
      "programmingLanguage": "Python",
      "runtimePlatform": "Python 3.10-3.13",
      "license": "https://opensource.org/licenses/BSD-3-Clause",
      "applicationCategory": "DeveloperApplication",
      "operatingSystem": "Linux, macOS, Windows",
      "author": {
        "@type": "Person",
        "name": "Warith Harchaoui"
      }
    },
    {
      "@type": "FAQPage",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "Why should the server count tokens instead of the client?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Because only the server holds the tokenizer. A client estimates with its own rule and under-counts: one measured session believed it was under 32,768 tokens and sent 40,433, and the server refused the whole request. Claude Code compacts at effective context minus a 13,000-token buffer, which is an estimate about an estimate. ai-bunker counts with the serving engine's own tokenizer, itemises the floor by owner, and refuses a session that has no room to work."
          }
        },
        {
          "@type": "Question",
          "name": "What is a session floor?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "The part of the context window paid on every single request and out of reach of compaction: the system prompt, the tool schemas, the charter, the knowledge index. Whatever is left is the only room the conversation has. One measured deployment had 59 locally-installed agent skills injected into every prompt, 17,754 tokens, 68% of a 26,226-token floor against a declared context of 26,000; compaction fired on turn one with nothing to compact and the session looped forever."
          }
        },
        {
          "@type": "Question",
          "name": "How does ai-bunker differ from LiteLLM or a guardrail library?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Gateways like LiteLLM route but do not inspect: a tool result full of secrets and a rm -rf pass through as ordinary bytes. Guardrail libraries like NeMo Guardrails, Guardrails AI and LLM Guard inspect but are libraries, so an agent that does not call them is unprotected. Neither counts the context budget. ai-bunker is the intersection: it stands in the request path like a gateway, inspects both ends of an agent's turn like a rule engine, and counts the budget with the server's tokenizer."
          }
        },
        {
          "@type": "Question",
          "name": "What hardware does a self-hosted coding agent need?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Decode speed is bounded by memory bandwidth divided by active weight bytes, not by capacity. For two people on a mixture-of-experts coding model, an existing 96 GB Apple Silicon machine already clears 20 tokens/second; a Mac Studio M3 Ultra at 819 GB/s reaches about 55. A DGX Spark has 128 GB and 273 GB/s, loads everything and answers at 6.5 tokens/second on a dense 24B, which is not a server at any quantity."
          }
        },
        {
          "@type": "Question",
          "name": "Is ai-bunker production ready?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "No. It is 0.1.0-alpha, with 422 tests and a green CI gate, next to projects with years of production use. The design is grounded in measurements from a GPU that served 6,565 messages under these constraints, but the code is new and the public interface can still move."
          }
        }
      ]
    }
  ]
}
  </script>
"""

BODY = (
    r"""

    <!-- Hero -->
    <section class="mx-auto max-w-6xl px-5 pt-16 pb-12 sm:pt-24">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">AI Helpers</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
        One GPU, one charter,<br>every coding agent.
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        A sovereign OpenAI-compatible gateway in front of your own GPU. It carries your
        team's standards, enforces rules that cannot be bypassed, and counts the context
        budget <em class="font-serif">with the server's own tokenizer</em> instead of
        trusting the client's estimate.
      </p>
      <div class="mt-8 flex flex-wrap items-center gap-3">
        <a href="start.html"
          class="inline-flex min-h-11 items-center rounded-full bg-brand-blue px-6 py-3 font-medium text-white hover:bg-brand-bluedark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue focus-visible:ring-offset-2">Get
          started</a>
        <a href="https://github.com/warith-harchaoui/ai-bunker"
          class="inline-flex min-h-11 items-center rounded-full border border-neutral-300 px-6 py-3 font-medium hover:border-neutral-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue dark:border-neutral-700 dark:hover:border-neutral-600">Read
          the source</a>
        <span class="text-sm text-neutral-500 dark:text-neutral-400">BSD-3-Clause · 422 tests · 0.1.0-alpha</span>
      </div>
    </section>

    <!-- The incident -->
    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-16">
        <div class="grid gap-10 md:grid-cols-[1.1fr_1fr] md:items-center">
          <div>
            <h2 class="font-serif text-3xl font-semibold tracking-tight">Why the server has to count</h2>
            <p class="mt-5 leading-relaxed text-neutral-700 dark:text-neutral-300">
              On 2026-09-25 an agent session believed it was under its limit and sent
              <strong class="font-semibold text-brand-linktext">40,433 tokens</strong> to a
              server configured for 32,768. The server counted for real, refused the whole
              request, and the session died.
            </p>
            <p class="mt-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
              The client was not lying. It was estimating, with its own tokenizer rule,
              which is more optimistic than the model's on French and on code. The gap was
              55%. Every harness does this: Claude Code compacts at
              <span class="font-mono text-sm">effective context − 13,000</span>, an estimate
              about an estimate.
            </p>
            <p class="mt-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
              The only party that can count correctly is the one holding the tokenizer, and
              that party is the server.
            </p>
          </div>
          <figure class="rounded-2xl border border-neutral-200 bg-white p-6 font-mono text-[13px] leading-relaxed shadow-sm dark:border-neutral-800 dark:bg-[#141416]">
            <figcaption class="mb-4 font-sans text-xs font-medium uppercase tracking-widest text-neutral-500 dark:text-neutral-400">A
              session floor, itemised by owner</figcaption>
            <table class="w-full">
              <tbody class="[&_td]:py-1">
                <tr><td>tool schemas (7)</td><td class="text-right tabular-nums">2,875</td><td class="pl-4 text-brand-orange">client</td></tr>
                <tr><td>client system prompt</td><td class="text-right tabular-nums">960</td><td class="pl-4 text-brand-orange">client</td></tr>
                <tr><td>charter</td><td class="text-right tabular-nums">465</td><td class="pl-4 text-brand-linktext">ai-bunker</td></tr>
                <tr><td>knowledge index</td><td class="text-right tabular-nums">142</td><td class="pl-4 text-brand-linktext">ai-bunker</td></tr>
                <tr class="border-t border-neutral-200 font-semibold dark:border-neutral-700"><td class="pt-2">FLOOR</td><td class="pt-2 text-right tabular-nums">4,442</td><td></td></tr>
              </tbody>
            </table>
            <p class="mt-4 font-sans text-xs text-neutral-500 dark:text-neutral-400">
              <span class="font-mono">backend=server exact=True</span> — counted by the
              engine, not estimated. A floor nobody can decompose is a floor nobody can
              reduce.
            </p>
          </figure>
        </div>
      </div>
    </section>

    <!-- Four stages -->
    <section id="budget" class="mx-auto max-w-6xl px-5 py-16">
      <h2 class="font-serif text-3xl font-semibold tracking-tight">Four stages, and the order matters</h2>
      <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        Any client that speaks OpenAI speaks ai-bunker, and gets all four without being
        configured for them. That is the argument for putting this at the endpoint rather
        than in each developer's harness: a plugin can be disabled by editing a file, and a
        different harness simply never had it.
      </p>
      <ol class="mt-10 grid gap-5 sm:grid-cols-2">
        <li class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <p class="font-mono text-xs text-neutral-500 dark:text-neutral-400">01 — inbound</p>
          <h3 class="mt-2 text-lg font-semibold">Screen what the agent reads</h3>
          <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">A
            <span class="font-mono text-sm">role:&nbsp;"tool"</span> message is text the world
            just handed the agent. Secrets leak out here, and indirect prompt injection
            arrives here. Both are caught, and what remains is marked as data rather than
            instruction.</p>
        </li>
        <li class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <p class="font-mono text-xs text-neutral-500 dark:text-neutral-400">02 — charter</p>
          <h3 class="mt-2 text-lg font-semibold">Serve the standards</h3>
          <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">Your team's
            pages, advertised as a ~600-token index rather than pasted into every prompt. A
            page costs nothing until it is opened, so the charter can be large.</p>
        </li>
        <li class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <p class="font-mono text-xs text-neutral-500 dark:text-neutral-400">03 — budget</p>
          <h3 class="mt-2 text-lg font-semibold">Measure, then refuse</h3>
          <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">A session
            with no room to work is refused <em>here</em>, with the component responsible
            named — rather than failing downstream as a context-length error nobody can act
            on.</p>
        </li>
        <li class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <p class="font-mono text-xs text-neutral-500 dark:text-neutral-400">04 — outbound</p>
          <h3 class="mt-2 text-lg font-semibold">Refuse what the agent runs</h3>
          <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">When the
            model answers with a tool call carrying a shell command, that command
            <strong>has not run yet</strong>. This is the one enforcement point no client can
            bypass.</p>
        </li>
      </ol>
      """
    + FLOW
    + r"""
    </section>

    <!-- Rules -->
    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-16">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Rules that ship with their evidence</h2>
        <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          A regular expression is the easiest thing here to get subtly wrong, and a wrong one
          fails silently: it stops matching, nobody notices, the guardrail is gone. So every
          rule carries its own examples, and they run in CI.
        </p>
        <pre class="mt-8 overflow-x-auto rounded-2xl border border-neutral-200 bg-white p-6 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>$ ai-bunker rules --check
  rules loaded                          17
  assertions passed                    107
  assertions failed                      0
  rules carrying evidence            100%</code></pre>
        <p class="mt-6 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          Three shipped patterns were wrong on first write — including one whose bound could
          not cross the dot in <span class="font-mono text-sm">~/.aws/credentials</span>. The
          examples caught all three before they reached a deployment.
        </p>
        <div class="mt-10 grid gap-5 sm:grid-cols-3">
          <div class="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-2xl font-semibold text-brand-linktext">2</p>
            <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">scopes: text on its way <em>in</em>, commands on their way <em>out</em></p>
          </div>
          <div class="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-2xl font-semibold text-brand-linktext">3.85</p>
            <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">bits/char — the measured entropy threshold that tells a credential from a placeholder</p>
          </div>
          <div class="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-2xl font-semibold text-brand-linktext">0</p>
            <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">catastrophic patterns allowed to load — the guard caught two in a working production rule set</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Honest status -->
    <section class="mx-auto max-w-6xl px-5 py-16">
      <div class="grid gap-10 md:grid-cols-2">
        <div>
          <h2 class="font-serif text-3xl font-semibold tracking-tight">What it is not</h2>
          <ul class="mt-6 space-y-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
            <li><strong class="font-semibold">Not a router with a hundred providers.</strong>
              LiteLLM is simply better at that, and ai-bunker sits in front of it rather than
              competing.</li>
            <li><strong class="font-semibold">Not a content classifier.</strong> LLM Guard
              and Guardrails AI ship trained models; this ships versioned regular
              expressions. Reviewable and free to run — a trade, not a win.</li>
            <li><strong class="font-semibold">Not mature.</strong> This is
              <span class="font-mono text-sm">0.1.0-alpha</span> next to projects with years
              of production use.</li>
          </ul>
          <p class="mt-6">
            <a href="landscape.html" class="font-medium text-brand-linktext hover:underline">See the full landscape →</a>
          </p>
        </div>
        <div>
          <h2 class="font-serif text-3xl font-semibold tracking-tight">What it is</h2>
          <p class="mt-6 leading-relaxed text-neutral-700 dark:text-neutral-300">
            The gateways route. The guardrails inspect. Neither counts.
          </p>
          <p class="mt-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
            ai-bunker is the intersection — and the corner of the map where all three meet
            was empty when we surveyed it.
          </p>
          <p class="mt-6 text-sm text-neutral-500 dark:text-neutral-400">
            Every number on this site was measured. Where a figure is an estimate, it says
            so.
          </p>
        </div>
      </div>
    </section>

"""
)
