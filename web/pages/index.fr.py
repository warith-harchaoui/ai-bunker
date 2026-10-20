"""Page d'accueil — français."""

import pathlib as _p
import sys

sys.path.insert(0, str(_p.Path(__file__).parent))
import _figures as F

TITLE = "ai-bunker — un GPU, une charte, tous les agents de code"
DESCRIPTION = (
    "Une passerelle souveraine compatible OpenAI devant votre propre GPU : une "
    "charte versionnée, des règles appliquées, et un budget de contexte que le "
    "serveur compte avec son propre tokenizer au lieu de croire l'estimation du client."
)

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [
      {"@type": "WebSite", "name": "ai-bunker", "url": "https://deraison.ai/ai-bunker/fr/",
       "description": "Passerelle souveraine compatible OpenAI devant votre propre GPU.",
       "inLanguage": "fr",
       "author": {"@type": "Person", "name": "Warith Harchaoui"}},
      {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": "Pourquoi le serveur doit-il compter les tokens plutôt que le client ?",
         "acceptedAnswer": {"@type": "Answer", "text": "Parce que seul le serveur tient le tokenizer. Un client estime avec sa propre règle et sous-compte : une session mesurée s'est crue sous 32 768 tokens et en a envoyé 40 433, et le serveur a refusé la requête entière. Claude Code compacte à « contexte effectif moins 13 000 tokens », soit une estimation sur une estimation."}},
        {"@type": "Question", "name": "Qu'est-ce que le plancher d'une session ?",
         "acceptedAnswer": {"@type": "Answer", "text": "La part de la fenêtre de contexte payée à chaque requête et hors d'atteinte de la compaction : prompt système, schémas d'outils, charte, index. Ce qui reste est la seule place dont dispose la conversation. Un poste mesuré injectait 59 descriptions de skills dans chaque prompt : 17 754 tokens, 68 % d'un plancher de 26 226 pour un contexte déclaré à 26 000, et la session bouclait sans jamais répondre."}},
        {"@type": "Question", "name": "Quelle différence avec LiteLLM ou une bibliothèque de garde-fous ?",
         "acceptedAnswer": {"@type": "Answer", "text": "Les passerelles routent mais n'inspectent pas : une sortie d'outil pleine de secrets et un rm -rf les traversent comme des octets ordinaires. Les bibliothèques de garde-fous inspectent mais restent des bibliothèques, donc un agent qui ne les appelle pas n'est pas protégé. Aucune ne compte le budget. ai-bunker est l'intersection."}}
      ]}
    ]
  }
  </script>"""

FLOW = F.flow(
    {
        "title": "Une requête traversant la passerelle ai-bunker",
        "desc": (
            "Un client à gauche envoie une requête à la passerelle au centre, qui la "
            "transmet au moteur d'inférence à droite. Dans la passerelle, l'étape 1 filtre "
            "les sorties d'outils entrantes, l'étape 2 injecte la charte, l'étape 3 mesure "
            "le budget et peut refuser la requête, l'étape 4 filtre les appels d'outils "
            "sortants et peut refuser une commande. Un trait pointillé relie les étapes 1 "
            "et 4, qui sont les deux portées d'un même moteur de règles."
        ),
        "gateway": "ai-bunker",
        "client": "Tout client OpenAI",
        "client_sub": "Claude Code · OpenCode · curl",
        "engine": "Votre GPU",
        "engine_sub": "vLLM, Ollama",
        "s1": "Filtrer ce qu'il lit",
        "s1a": "secrets qui sortent, injection qui entre",
        "s1b": "le reste marqué comme donnée",
        "s2": "Servir la charte",
        "s2a": "l'index, pas les fiches",
        "s2b": "position stable, donc cachable",
        "s3": "Mesurer le budget",
        "s3a": "avec le tokenizer du moteur, pas une estimation",
        "s3_refuse": "413 — nomme le coupable",
        "s4": "Filtrer ce qu'il exécute",
        "s4a": "la commande n'a pas encore tourné",
        "s4_refuse": "refus en résultat d'outil",
        "same1": "un seul moteur de règles,",
        "same2": "aux deux bouts d'un tour",
        "caption": (
            "L'ordre porte le sens. Les étapes 1 et 4 sont le même moteur de règles aux deux "
            "bouts du tour d'un agent, et une passerelle est la première position d'où les "
            "deux sont visibles — une bibliothèque appelée depuis une application ne voit ni "
            "l'une ni l'autre de façon fiable."
        ),
    }
)

BODY = (
    r"""
    <section class="mx-auto max-w-6xl px-5 pt-16 pb-12 sm:pt-24">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">AI Helpers</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
        Un GPU, une charte,<br>tous les agents de code.
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        Une passerelle souveraine compatible OpenAI, posée devant votre propre GPU — votre
        propre processeur graphique. Elle porte
        les standards de l'équipe, applique des règles qu'on ne peut pas contourner, et compte
        le budget de contexte <em class="font-serif">avec le tokenizer du serveur</em> au lieu
        de croire l'estimation du client.
      </p>
      <div class="mt-8 flex flex-wrap items-center gap-3">
        <a href="start.html"
          class="inline-flex min-h-11 items-center rounded-full bg-brand-blue px-6 py-3 font-medium text-white hover:bg-brand-bluedark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue focus-visible:ring-offset-2">Démarrer</a>
        <a href="https://github.com/warith-harchaoui/ai-bunker"
          class="inline-flex min-h-11 items-center rounded-full border border-neutral-300 px-6 py-3 font-medium hover:border-neutral-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue dark:border-neutral-700 dark:hover:border-neutral-600">Lire
          le code</a>
        <span class="text-sm text-neutral-500 dark:text-neutral-400">BSD-3-Clause · 566 tests · 0.1.0-alpha</span>
      </div>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-16">
        <div class="grid gap-10 md:grid-cols-[1.1fr_1fr] md:items-center">
          <div>
            <h2 class="font-serif text-3xl font-semibold tracking-tight">Pourquoi c'est au serveur de compter</h2>
            <p class="mt-5 leading-relaxed text-neutral-700 dark:text-neutral-300">
              Le 25/09/2026, une session s'est crue sous sa limite et a envoyé
              <strong class="font-semibold text-brand-linktext">40 433 tokens</strong> à un
              serveur configuré pour 32 768. Le serveur a compté pour de vrai, a refusé la
              requête entière, et la session est morte.
            </p>
            <p class="mt-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
              Le client ne mentait pas. Il estimait, avec sa propre règle de tokenisation, plus
              optimiste que celle du modèle sur le français et sur le code. L'écart était de
              55 %. Tous les harnais font cela : Claude Code compacte à
              <span class="font-mono text-sm">contexte effectif − 13 000</span>, soit une
              estimation sur une estimation.
            </p>
            <p class="mt-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
              Le seul qui puisse compter juste est celui qui tient le tokenizer, et c'est le
              serveur.
            </p>
          </div>
          <figure class="rounded-2xl border border-neutral-200 bg-white p-6 font-mono text-[13px] leading-relaxed shadow-sm dark:border-neutral-800 dark:bg-[#141416]">
            <figcaption class="mb-4 font-sans text-xs font-medium uppercase tracking-widest text-neutral-500 dark:text-neutral-400">Un
              plancher de session, détaillé par propriétaire</figcaption>
            <table class="w-full">
              <tbody class="[&amp;_td]:py-1">
                <tr><td>schémas d'outils (7)</td><td class="text-right tabular-nums">2 875</td><td class="pl-4 text-brand-orange">client</td></tr>
                <tr><td>prompt système du client</td><td class="text-right tabular-nums">960</td><td class="pl-4 text-brand-orange">client</td></tr>
                <tr><td>charte</td><td class="text-right tabular-nums">465</td><td class="pl-4 text-brand-linktext">ai-bunker</td></tr>
                <tr><td>index des savoirs</td><td class="text-right tabular-nums">142</td><td class="pl-4 text-brand-linktext">ai-bunker</td></tr>
                <tr class="border-t border-neutral-200 font-semibold dark:border-neutral-700"><td class="pt-2">PLANCHER</td><td class="pt-2 text-right tabular-nums">4 442</td><td></td></tr>
              </tbody>
            </table>
            <p class="mt-4 font-sans text-xs text-neutral-500 dark:text-neutral-400">
              <span class="font-mono">backend=server exact=True</span> — compté par le moteur,
              pas estimé. Un plancher qu'on ne peut pas décomposer est un plancher qu'on ne peut
              pas réduire.
            </p>
          </figure>
        </div>
      </div>
    </section>

    <section id="budget" class="mx-auto max-w-6xl px-5 py-16">
      <h2 class="font-serif text-3xl font-semibold tracking-tight">Quatre étapes, et l'ordre compte</h2>
      <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        Tout client qui parle OpenAI parle ai-bunker, et reçoit les quatre sans avoir été
        configuré pour. C'est l'argument qui justifie de mettre cela au point d'entrée plutôt
        que dans le harnais de chaque développeur : un plugin se désactive en éditant un
        fichier, et un autre harnais ne l'a simplement jamais eu.
      </p>
      """
    + FLOW
    + r"""
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-16">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Des règles livrées avec leurs preuves</h2>
        <p class="mt-4 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          Une expression régulière est la chose la plus facile à se tromper ici, et une regex
          fausse échoue en silence : elle cesse d'apparier, personne ne le voit, le garde-fou a
          disparu. Chaque règle porte donc ses propres exemples, et ils tournent en
          intégration continue (CI).
        </p>
        <pre class="mt-8 overflow-x-auto rounded-2xl border border-neutral-200 bg-white p-6 font-mono text-[13px] leading-relaxed dark:border-neutral-800 dark:bg-[#141416]"><code>$ ai-bunker rules --check
  rules loaded                          19
  assertions passed                    120
  assertions failed                      0
  rules carrying evidence            100%</code></pre>
        <p class="mt-6 max-w-2xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          Trois motifs livrés étaient faux au premier jet — dont un dont la borne ne pouvait pas
          franchir le point de <span class="font-mono text-sm">~/.aws/credentials</span>. Les
          exemples ont attrapé les trois avant tout déploiement.
        </p>
        <div class="mt-10 grid gap-5 sm:grid-cols-3">
          <div class="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-2xl font-semibold text-brand-linktext">2</p>
            <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">portées : le texte qui <em>entre</em>, les commandes qui <em>sortent</em></p>
          </div>
          <div class="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-2xl font-semibold text-brand-linktext">3,85</p>
            <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">bits/car. — le seuil d'entropie mesuré qui distingue un identifiant d'un espace réservé</p>
          </div>
          <div class="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-2xl font-semibold text-brand-linktext">0</p>
            <p class="mt-1 text-sm text-neutral-600 dark:text-neutral-400">motif catastrophique autorisé à charger — le garde-fou en a attrapé deux dans un jeu de règles en production</p>
          </div>
        </div>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-5 py-16">
      <div class="grid gap-10 md:grid-cols-2">
        <div>
          <h2 class="font-serif text-3xl font-semibold tracking-tight">Ce que ce n'est pas</h2>
          <ul class="mt-6 space-y-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
            <li><strong class="font-semibold">Pas un routeur à cent fournisseurs.</strong>
              LiteLLM est simplement meilleur là-dessus, et ai-bunker se place devant lui plutôt
              que de le concurrencer.</li>
            <li><strong class="font-semibold">Pas un classificateur de contenu.</strong> LLM
              Guard et Guardrails AI livrent des modèles entraînés ; ici ce sont des expressions
              régulières versionnées. Relisibles et gratuites à l'exécution — un arbitrage, pas
              une victoire.</li>
            <li><strong class="font-semibold">Pas mature.</strong> C'est un
              <span class="font-mono text-sm">0.1.0-alpha</span> à côté de projets qui ont des
              années de production.</li>
          </ul>
          <p class="mt-6">
            <a href="landscape.html" class="font-medium text-brand-linktext hover:underline">Voir le paysage complet →</a>
          </p>
        </div>
        <div>
          <h2 class="font-serif text-3xl font-semibold tracking-tight">Ce que c'est</h2>
          <p class="mt-6 leading-relaxed text-neutral-700 dark:text-neutral-300">
            Les passerelles routent. Les garde-fous inspectent. Aucun ne compte.
          </p>
          <p class="mt-4 leading-relaxed text-neutral-700 dark:text-neutral-300">
            ai-bunker est l'intersection — et le coin de la carte où les trois se rejoignent
            était vide au moment du relevé.
          </p>
          <p class="mt-6 text-sm text-neutral-500 dark:text-neutral-400">
            Chaque chiffre de ce site a été mesuré. Là où une valeur est une estimation, elle le
            dit.
          </p>
        </div>
      </div>
    </section>
"""
)
