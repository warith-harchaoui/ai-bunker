"""Démarrer — français."""

TITLE = "Démarrer — ai-bunker"
DESCRIPTION = (
    "Installer, dimensionner la machine, lancer la passerelle, y pointer un client, "
    "et équiper un dépôt. Chaque commande avec sa vraie sortie."
)

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "HowTo",
    "name": "Mettre en place une passerelle LLM souveraine pour agents de code",
    "description": "Installer ai-bunker, dimensionner la machine, lancer la passerelle, y pointer un client compatible OpenAI, et équiper un dépôt d'une charte.",
    "inLanguage": "fr",
    "step": [
      {"@type": "HowToStep", "name": "Installer", "text": "Cloner le dépôt et installer avec l'extra api."},
      {"@type": "HowToStep", "name": "Dimensionner", "text": "Lancer ai-bunker recommend --team N pour voir quelle machine porte l'équipe, puis ai-bunker sizing pour obtenir la commande vllm serve."},
      {"@type": "HowToStep", "name": "Configurer et vérifier", "text": "Copier config/gateway.example.yaml, définir une clé d'API, et lancer ai-bunker doctor."},
      {"@type": "HowToStep", "name": "Servir", "text": "Lancer ai-bunker serve, puis pointer n'importe quel client compatible OpenAI vers la passerelle."},
      {"@type": "HowToStep", "name": "Équiper un dépôt", "text": "Lancer ai-bunker adopt pour écrire la charte et un kit client mince."}
    ]
  }
  </script>"""

BODY = r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Démarrer</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        De rien à une passerelle
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        Cinq étapes. Chaque bloc ci-dessous est une vraie sortie — la règle du projet est qu'une
        affirmation est une mesure ou elle est retirée, et cela vaut aussi pour sa documentation.
      </p>
    </section>

    <section class="mx-auto max-w-6xl px-5 pb-16">
      <ol class="space-y-10">

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">01</span>Installer
          </h2>
          <p class="mt-3 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Python 3.10–3.13 et git. Un GPU — un processeur graphique — n'est nécessaire que
            sur la machine qui
            <em>sert</em> ; les clients n'en ont pas besoin.
          </p>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>git clone https://github.com/warith-harchaoui/ai-bunker.git
cd ai-bunker
python3 -m venv .venv &amp;&amp; source .venv/bin/activate
pip install -e ".[api]"</code></pre>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">02</span>Savoir ce qu'il vous faut
          </h2>
          <p class="mt-3 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Avant d'acheter quoi que ce soit. La réponse la moins chère est souvent la machine
            que vous avez déjà, qui figure au catalogue à 0 $ pour que « ne rien acheter » soit
            une option chiffrée plutôt qu'un haussement d'épaules.
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
            <a href="sizing.html" class="text-brand-linktext hover:underline">Pourquoi le dimensionnement fonctionne ainsi →</a>
          </p>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">03</span>Configurer, et vérifier les promesses
          </h2>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>cp config/gateway.example.yaml config/gateway.yaml
export AI_BUNKER_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

$ ai-bunker doctor
  [ok  ] charter carries operating rules
  [ok  ] 27 rules loaded
  [ok  ] 218 rule assertions pass
  [ok  ] 100% of rules carry evidence
  [WARN] upstream local answers at http://127.0.0.1:8001/v1   not reachable
  [ok  ] no route leaves this network
  12/14 checks pass</code></pre>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            <code class="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm dark:bg-neutral-800">doctor</code>
            rapporte ce que le déploiement fait <em>vraiment</em>, y compris qu'une passerelle
            sans clé d'API — une clé d'interface de programmation — est ouverte à quiconque
            peut l'atteindre. Ouverte par accident et
            ouverte exprès se ressemblent vues de dehors ; c'est ce qui les distingue.
          </p>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">04</span>Servir, et y pointer un client
          </h2>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>ai-bunker serve                      # localhost:8000

export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="$AI_BUNKER_API_KEY"</code></pre>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            C'est toute la configuration client. Tout client qui parle OpenAI reçoit désormais la
            charte, le moteur de règles et le budget sans avoir été configuré pour.
          </p>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Le tableau de bord est sur
            <code class="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm dark:bg-neutral-800">/gui</code> :
          </p>
          <figure class="mt-5">
            <img src="../img/dashboard-light.png" width="1800" height="1290" loading="lazy"
              alt="Le tableau de bord d'ai-bunker dans son thème clair. Un bandeau en haut porte les pastilles « sovereign », « open to anyone who can reach it », « 10 output rules », « 12 command rules » et « 3 tool rules », ainsi qu'un bouton soleil qui bascule vers le thème sombre. En dessous, une barre fine montre le plancher de session en un filet orange sur une fenêtre presque vide, légendée « floor 595 — under 1% of the window » et « 193,120 left to work with ». Une seconde barre, plus large, décompose ce plancher en ses deux composants, la charte à 448 tokens (75 %) et l'index de connaissance à 147 (25 %), tous deux détenus par ai-bunker, et un tableau les reprend avec leurs parts. Un panneau à droite indique 262 144 tokens servis par le moteur, 209 715 déclarés aux clients, une marge de compaction de 16 000 et 193 120 d'espace de conversation, et précise que le compte vient du tokenizer du serveur plutôt que d'une estimation."
              class="w-full rounded-2xl border border-neutral-200 dark:border-neutral-800">
            <figcaption class="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
              Deux barres plutôt qu'une : un rapport de 300:1 et une composition sont deux
              questions différentes, et une seule barre ne peut pas porter les deux.
            </figcaption>
          </figure>
        </li>

        <li>
          <h2 class="font-serif text-2xl font-semibold tracking-tight">
            <span class="mr-3 font-mono text-base text-neutral-500 dark:text-neutral-400">05</span>Équiper un dépôt
          </h2>
          <pre class="mt-5 overflow-x-auto rounded-2xl border border-neutral-200 bg-neutral-50 p-5 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>$ ai-bunker adopt /chemin/du/projet --list
Adopting ai-bunker into /chemin/du/projet:
  + charter/AGENTS.md   (how to work here, injected every request)
  + charter/packs   (the standards pages, read on demand)
  + charter/rules   (the rules, with their own evidence)
  + opencode.json   (points at the gateway)
  + .opencode/plugins/bounded-reads.js   (the one thing the gateway cannot do)
  + .claude/settings.ai-bunker.json   (merge into .claude/settings.json)
  + CLAUDE.md   (what the gateway does to a session)</code></pre>
          <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
            Rien n'est remplacé sans <code class="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm dark:bg-neutral-800">--force</code>.
            Le kit client est délibérément <strong class="font-semibold">une configuration et un
            plugin</strong> : tout ce que la passerelle peut voir, elle l'impose, donc un kit ne
            porte que ce qui se passe <em>avant qu'une requête n'existe</em> — lectures bornées,
            pas d'injection de skills, seuils de compaction.
          </p>
        </li>

      </ol>

      <div class="mt-14 rounded-2xl border border-neutral-200 bg-neutral-50 p-6 dark:border-neutral-800 dark:bg-neutral-900/40">
        <h2 class="font-serif text-xl font-semibold tracking-tight">Avant d'en dépendre</h2>
        <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">
          C'est un <code class="font-mono text-sm">0.2.0-alpha</code> : une porte d'intégration continue (CI)
          verte, à côté de projets qui ont des années de production. Le filtrage des commandes ne
          s'applique pas au streaming, et <code class="font-mono text-sm">/health</code> publie
          quelles garanties sont actives plutôt que de laisser croire qu'elles le sont toutes.
        </p>
        <p class="mt-4">
          <a href="https://github.com/warith-harchaoui/ai-bunker/blob/main/EXEMPLES.md"
            class="font-medium text-brand-linktext hover:underline">Chaque commande, avec sa vraie sortie →</a>
        </p>
      </div>
    </section>
"""
