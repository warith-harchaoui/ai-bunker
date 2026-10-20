"""Glossary page — français."""

TITLE = "Glossaire — ai-bunker"
DESCRIPTION = "Chaque sigle employé par ce projet, défini une fois : A2A, A2UI, AP2, UCP, MCP, Agent Skills, JWS, JWKS, OTLP, cache KV, MoE, ReDoS, plancher de session, slopsquatting et Gherkin."

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "DefinedTermSet",
    "name": "Glossaire ai-bunker",
    "description": "Les termes employés par ai-bunker : protocoles d'agents, arithmétique de service et vocabulaire de sécurité.",
    "inLanguage": "fr",
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
      {"@type": "DefinedTerm", "name": "KV cache", "description": "cache clé–valeur"},
      {"@type": "DefinedTerm", "name": "MoE", "description": "Mélange d'experts"},
      {"@type": "DefinedTerm", "name": "ReDoS", "description": "Déni de service par expression régulière"},
      {"@type": "DefinedTerm", "name": "Session floor", "description": "Plancher de session"},
      {"@type": "DefinedTerm", "name": "Slopsquatting", "description": "Slopsquatting"},
      {"@type": "DefinedTerm", "name": "Gherkin", "description": "Gherkin"}
    ]
  }
  </script>"""

BODY = r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Glossaire</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        Chaque sigle,<br>défini une fois.
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        Un lecteur qui ne sait pas ce qu'est l'Agent Payments Protocol ne peut pas juger une affirmation à son sujet. Voici les termes employés par ce projet, au sens où il les emploie.
      </p>
    </section>

    <section class="mx-auto max-w-6xl px-5 pb-20">
      <div id="a2a" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">A2A</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Agent2Agent</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un protocole ouvert permettant aux agents de se parler : découverte par une carte d&#x27;agent, puis tâches et messages en HTTP, l'HyperText Transfer Protocol du web. ai-bunker publie une carte et filtre les messages entrants, car un message écrit par un autre agent est du texte qui franchit une frontière de confiance.</p>
      </div>
      <div id="a2ui" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">A2UI</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Agent-to-User Interface</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un agent décrit une interface qu&#x27;un hôte affiche, au lieu de renvoyer du texte. Utile, et nouvelle surface d&#x27;attaque : la description est produite par l&#x27;agent et l&#x27;hôte l&#x27;exécute.</p>
      </div>
      <div id="ap2" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">AP2</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Agent Payments Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Comment un agent prouve qu&#x27;un humain a autorisé un paiement. L&#x27;utilisateur approuve sur une Trusted Surface, que le protocole définit comme explicitement non-agentique, et l&#x27;agent porte le résultat signé — un mandat.</p>
      </div>
      <div id="ucp" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">UCP</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Universal Commerce Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">La norme d&#x27;objet Checkout, utilisée avec un mandat AP2. Le mandat dit ce qui a été autorisé, l&#x27;objet Checkout dit ce qui est débité, et quelqu&#x27;un doit comparer les deux.</p>
      </div>
      <div id="mcp" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">MCP</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Model Context Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Comment un modèle atteint des outils et des sources de données. ai-bunker expose la charte via MCP, et seulement la charte.</p>
      </div>
      <div id="agent-skills" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Agent Skills</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un format ouvert pour empaqueter des connaissances qu&#x27;un agent charge à la demande : un dossier avec un SKILL.md, lu nativement par Claude Code, OpenCode, Cursor, Goose et d&#x27;autres. ai-bunker y publie sa charte.</p>
      </div>
      <div id="jws-jwt" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">JWS / JWT</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">JSON Web Signature / JSON Web Token — JSON pour JavaScript Object Notation</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un jeton signé et compact, en trois parties séparées par des points — en-tête, charge utile, signature — encodé pour survivre dans une URL, une adresse web. Les mandats AP2 arrivent sous cette forme.</p>
      </div>
      <div id="jwks" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">JWKS</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">JSON Web Key Set</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Les clés publiques contre lesquelles une signature est vérifiée. ai-bunker en lit un depuis un fichier par défaut, de sorte que vérifier un paiement ne demande aucun réseau.</p>
      </div>
      <div id="otlp-opentelemetry" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">OTLP / OpenTelemetry</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">OpenTelemetry Protocol</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">La norme d&#x27;envoi de traces vers un collecteur. ai-bunker exporte son journal de décision en spans, car ce journal est déjà l&#x27;enregistrement de la trajectoire d&#x27;un agent.</p>
      </div>
      <div id="kv-cache" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">KV cache</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">cache clé–valeur</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Ce qu&#x27;un modèle conserve des tokens déjà présents dans une conversation. Il croît avec le contexte et est relu à chaque token produit : c&#x27;est pourquoi le contexte coûte du débit et pas seulement de la mémoire.</p>
      </div>
      <div id="moe" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">MoE</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Mixture of Experts — mélange d'experts</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un modèle où chaque token n&#x27;active qu&#x27;une fraction des poids. Un MoE de 80 milliards dont 3 sont actifs lit moins de mémoire par token qu&#x27;un modèle dense de 24 : c&#x27;est pourquoi le meilleur codeur ouvert est aussi le plus rapide à servir.</p>
      </div>
      <div id="redos" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">ReDoS</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Regular expression Denial of Service — déni de service par expression régulière</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un motif dont le temps d&#x27;exécution explose sur une entrée fabriquée. Le chargeur de règles rejette les quantificateurs imbriqués non bornés avant de les exécuter : une sonde de temps ne peut pas attraper ce qui ne se termine jamais.</p>
      </div>
      <div id="session-floor" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Session floor</h2>
        <p class="mt-1 text-sm italic text-neutral-500 dark:text-neutral-400">Plancher de session</p>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">La part d&#x27;une fenêtre de contexte payée à chaque requête — invite système, schémas d&#x27;outils, charte, index — et que la compaction ne peut pas réduire. Ce qui reste est le seul espace dont dispose une conversation.</p>
      </div>
      <div id="slopsquatting" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Slopsquatting</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Enregistrer un nom de paquet qu&#x27;un modèle est susceptible d&#x27;inventer, pour qu&#x27;un agent l&#x27;installe. Interroger un registre n&#x27;aide pas : le paquet malveillant est enregistré précisément pour que la réponse soit « oui ».</p>
      </div>
      <div id="gherkin" class="border-t border-neutral-200/70 py-6 dark:border-neutral-800">
        <h2 class="font-mono text-lg font-semibold">Gherkin</h2>
        <p class="mt-3 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">Un format de spécification comportementale en langage ordinaire : Given / When / Then. ai-bunker rend son jeu de règles en Gherkin pour que la personne qui l&#x27;approuve n&#x27;ait pas à lire des expressions régulières.</p>
      </div>
    </section>
"""
