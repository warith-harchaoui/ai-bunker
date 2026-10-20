"""Glossary page — English."""

TITLE = "Glossary — ai-bunker"
DESCRIPTION = "Every acronym this project uses, defined once: A2A, A2UI, AP2, UCP, MCP, Agent Skills, JWS, JWKS, OTLP, KV cache, MoE, ReDoS, session floor, slopsquatting and Gherkin."

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "DefinedTermSet",
    "name": "ai-bunker glossary",
    "description": "Terms used by ai-bunker: agent protocols, serving arithmetic and security vocabulary.",
    "inLanguage": "en",
    "hasDefinedTerm": [
      {"@type": "DefinedTerm", "name": "A2A", "description": "Agent2Agent"},
      {"@type": "DefinedTerm", "name": "A2UI", "description": "Agent-to-User Interface"},
      {"@type": "DefinedTerm", "name": "AP2", "description": "Agent Payments Protocol"},
      {"@type": "DefinedTerm", "name": "UCP", "description": "Universal Commerce Protocol"},
      {"@type": "DefinedTerm", "name": "MCP", "description": "Model Context Protocol"},
      {"@type": "DefinedTerm", "name": "Agent Skills", "description": "Agent Skills"},
      {"@type": "DefinedTerm", "name": "JWS / JWT", "description": "JSON Web Signature / JSON Web Token"},
      {"@type": "DefinedTerm", "name": "JWKS", "description": "JSON Web Key Set"},
      {"@type": "DefinedTerm", "name": "OTLP / OpenTelemetry", "description": "OpenTelemetry Protocol"},
      {"@type": "DefinedTerm", "name": "KV cache", "description": "key–value cache"},
      {"@type": "DefinedTerm", "name": "MoE", "description": "Mixture of Experts"},
      {"@type": "DefinedTerm", "name": "ReDoS", "description": "Regular expression Denial of Service"},
      {"@type": "DefinedTerm", "name": "Session floor", "description": "Session floor"},
      {"@type": "DefinedTerm", "name": "Slopsquatting", "description": "Slopsquatting"},
      {"@type": "DefinedTerm", "name": "Gherkin", "description": "Gherkin"}
    ]
  }
  </script>"""

BODY = r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Glossary</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        Every acronym,<br>defined once.
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        A reader who does not know what the Agent Payments Protocol is cannot evaluate a claim about it. These are the terms this project uses, in the sense it uses them.
      </p>
    </section>

    <section class="mx-auto max-w-6xl px-5 pb-20">
      <div id="a2a" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">A2A</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Agent2Agent</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">An open protocol for agents to talk to each other: discovery through an agent card, then tasks and messages over HTTP, the HyperText Transfer Protocol of the web. ai-bunker publishes a card and screens inbound messages, because a message another agent wrote is text crossing a trust boundary.</p>
      </div>
      <div id="a2ui" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">A2UI</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Agent-to-User Interface</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">An agent describes an interface and a host renders it, instead of the agent returning prose. Useful, and a new attack surface: the description is agent-generated and the host executes it.</p>
      </div>
      <div id="ap2" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">AP2</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Agent Payments Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">How an agent proves a human authorised a payment. The user approves on a Trusted Surface, which the protocol defines as explicitly non-agentic, and the agent carries the signed result — a mandate.</p>
      </div>
      <div id="ucp" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">UCP</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Universal Commerce Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">The Checkout Object standard used alongside an AP2 mandate. The mandate says what was authorised, the checkout object says what is being charged, and somebody has to compare them.</p>
      </div>
      <div id="mcp" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">MCP</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Model Context Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">How a model reaches tools and data sources. ai-bunker exposes the charter over MCP, and only the charter.</p>
      </div>
      <div id="agent-skills" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Agent Skills</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">An open format for packaging knowledge an agent loads on demand: a folder with a SKILL.md, read natively by Claude Code, OpenCode, Cursor, Goose and others. ai-bunker publishes its charter in this format.</p>
      </div>
      <div id="jws-jwt" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">JWS / JWT</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">JSON Web Signature / JSON Web Token — JSON being JavaScript Object Notation</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">A signed, compact token in three dot-separated parts — header, payload, signature — encoded so it survives inside a URL, a uniform resource locator. AP2 mandates arrive as these.</p>
      </div>
      <div id="jwks" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">JWKS</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">JSON Web Key Set</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">The public keys a signature is checked against. ai-bunker reads one from a file by default, so verifying a payment needs no network.</p>
      </div>
      <div id="otlp-opentelemetry" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">OTLP / OpenTelemetry</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">OpenTelemetry Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">The standard for shipping traces to a collector. ai-bunker exports its decision log as spans, because that log is already a record of an agent&#x27;s trajectory.</p>
      </div>
      <div id="kv-cache" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">KV cache</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">key–value cache</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">What a model keeps about the tokens already in a conversation. It grows with context and is read on every generated token, which is why context costs throughput and not only memory.</p>
      </div>
      <div id="moe" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">MoE</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Mixture of Experts</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">A model where each token only activates a fraction of the weights. An 80B MoE with 3B active streams less memory per token than a dense 24B, which is why the best open coder is also the fastest to serve.</p>
      </div>
      <div id="redos" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">ReDoS</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Regular expression Denial of Service</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">A pattern that takes exponential time on crafted input. The rule loader rejects nested unbounded quantifiers before running them, because a timing probe cannot catch what never terminates.</p>
      </div>
      <div id="session-floor" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Session floor</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">The part of a context window paid on every single request — system prompt, tool schemas, charter, index — and which compaction cannot reduce. What is left is the only room a conversation has.</p>
      </div>
      <div id="slopsquatting" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Slopsquatting</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Registering a package name a model is likely to invent, so an agent installs it. No registry lookup helps: the malicious package is registered precisely so the lookup passes.</p>
      </div>
      <div id="gherkin" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Gherkin</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">A plain-language format for behaviour specifications: Given / When / Then. ai-bunker renders its rule set as Gherkin so the person who approves it does not have to read regular expressions.</p>
      </div>
    </section>
"""
