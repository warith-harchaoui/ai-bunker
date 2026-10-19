"""Paysage — français."""

TITLE = "Paysage — où se situe ai-bunker"
DESCRIPTION = (
    "Les passerelles routent, les garde-fous inspectent, aucun ne compte. Un relevé "
    "de LiteLLM, Portkey, Kong, NeMo Guardrails, Guardrails AI, LLM Guard et OPA, "
    "y compris là où ce projet est en retard."
)

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    "headline": "Où se situe ai-bunker parmi les passerelles LLM et les moteurs de garde-fous",
    "description": "Un relevé comparatif des passerelles LLM, bibliothèques de garde-fous et moteurs de politiques, avec une carte de positionnement par ACP et un compte rendu explicite de là où ai-bunker est en retard.",
    "inLanguage": "fr",
    "author": {"@type": "Person", "name": "Warith Harchaoui"}
  }
  </script>"""

BODY = r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Paysage</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        Les passerelles routent.<br>Les garde-fous inspectent.<br>Aucun ne compte.
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        Les outils qui se placent entre un agent de code et un modèle, relevés le 19/10/2026. Un
        outil conçu pour un autre travail n'est pas critiqué — et trois d'entre eux battent ce
        projet sur un point nommé ci-dessous.
      </p>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-14">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Trois grappes, et un coin vide</h2>
        <figure class="mt-8">
          <img src="../img/landscape.png" width="1800" height="1391" loading="lazy"
            alt="Une carte de positionnement produite par analyse en composantes principales. L'axe horizontal va de Ressource à gauche à Discipline à droite ; l'axe vertical de Protégé en bas à Piloté en haut. LiteLLM, Kong AI Gateway et Portkey forment une grappe à gauche. NeMo Guardrails, Guardrails AI et LLM Guard occupent le centre et le bas à droite, avec Open Policy Agent et la configuration de harnais client en dessous. ai-bunker est seul en haut à droite."
            class="w-full rounded-2xl border border-neutral-200 bg-white dark:border-neutral-800">
          <figcaption class="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
            À lire comme une forme, pas comme un classement. Produite par
            <a href="https://github.com/warith-harchaoui/standpoint" class="text-brand-linktext hover:underline">standpoint</a>
            à partir du tableau de notes, par ACP.
          </figcaption>
        </figure>
        <div class="mt-10 grid gap-5 md:grid-cols-3">
          <div class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <h3 class="font-semibold">À gauche — les passerelles</h3>
            <p class="mt-3 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
              LiteLLM, Kong, Portkey. Une seule surface compatible OpenAI sur une centaine de
              fournisseurs, avec clés, budgets, reprises et observabilité — et très bien faite.
              Ce qu'elles ne font pas : regarder ce que l'agent lit ou s'apprête à exécuter. Une
              sortie d'outil pleine de secrets et un <span class="font-mono text-xs">rm -rf ~</span>
              les traversent comme des octets ordinaires.
            </p>
          </div>
          <div class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <h3 class="font-semibold">À droite et en dessous — les moteurs de règles</h3>
            <p class="mt-3 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
              NeMo Guardrails, Guardrails AI, LLM Guard. Ils inspectent le contenu correctement,
              et plusieurs le font mieux que ce projet. Ce qu'ils ne sont pas : des passerelles.
              Ce sont des bibliothèques que vous appelez, donc un agent qui ne les appelle pas
              n'est pas protégé, et changer de harnais les perd entièrement.
            </p>
          </div>
          <div class="rounded-2xl border border-brand-blue/40 bg-brand-blue/5 p-6">
            <h3 class="font-semibold">En haut à droite — vide, sauf celui-ci</h3>
            <p class="mt-3 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
              Personne d'autre ne combine la position de la passerelle — chaque requête, chaque
              client, sans échappatoire — avec l'inspection du moteur de règles et un budget que
              le serveur compte. C'est une affirmation sur la <em>couverture</em>, pas sur la
              qualité.
            </p>
          </div>
        </div>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-5 py-14">
      <h2 class="font-serif text-3xl font-semibold tracking-tight">Là où ce projet est en retard</h2>
      <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        À dire, parce qu'un paysage où un seul outil gagne toutes les colonnes n'est pas
        crédible.
      </p>
      <dl class="mt-8 space-y-6">
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Largeur de fournisseurs — LiteLLM, et de loin</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">Une centaine de
            fournisseurs contre ce que vous configurez ici. Si la question est « appeler beaucoup
            de fournisseurs depuis un seul client », LiteLLM est simplement la réponse — et
            ai-bunker peut se placer devant lui plutôt que le concurrencer.</dd>
        </div>
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Classificateurs de contenu — LLM Guard et Guardrails AI</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">Leurs scanners
            sont des modèles entraînés et des catalogues de validateurs curatés ; ici ce sont des
            expressions régulières versionnées avec un seuil d'entropie. Relisibles, diffables et
            gratuites à l'exécution — un arbitrage assumé, et sur la qualité brute de détection
            c'est un arbitrage, pas une victoire.</dd>
        </div>
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Expressivité et test des politiques — OPA</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">Rego exprime des
            conditions qu'une regex ne peut pas, et son outillage de test avec couverture est
            meilleur que <span class="font-mono text-sm">rules --check</span>. L'idée qu'une
            politique porte ses propres tests vient de là.</dd>
        </div>
        <div class="rounded-2xl border border-neutral-200 p-6 dark:border-neutral-800">
          <dt class="font-semibold">Maturité</dt>
          <dd class="mt-2 leading-relaxed text-neutral-700 dark:text-neutral-300">C'est un
            <span class="font-mono text-sm">0.1.0-alpha</span> à côté de projets qui ont des
            années de production.</dd>
        </div>
      </dl>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-14">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Idées reprises au terrain</h2>
        <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          Rien de tout cela n'a été inventé ici, et le dire ne coûte rien.
        </p>
        <ul class="mt-8 grid gap-5 sm:grid-cols-2">
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">Open Policy Agent</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">La
              politique porte ses propres tests, et les décisions sont journalisées dès le premier
              jour. Les deux sont désormais porteurs ici — et le premier a attrapé trois motifs
              faux avant tout déploiement.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">gitleaks</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">Regex
              <em>et</em> seuil d'entropie, plus des listes d'exception par règle. Un scanner qui
              crie au loup apprend à ses lecteurs à l'ignorer.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">Le <em>spotlighting</em> de Microsoft</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">Marquer
              le contenu récupéré comme de la donnée. La reconnaissance de motifs attrape les
              tentatives maladroites ; le marquage structurel est ce qui tient quand les motifs
              ratent.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-semibold">La recherche sur les harnais d'agents</p>
            <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">La
              distinction « prévention / remède » : borner structurellement le contexte, ou le
              laisser croître et compresser. Ce projet est de la prévention, déplacée côté
              serveur — une case que la taxonomie n'a pas.</p>
          </li>
        </ul>
        <p class="mt-10">
          <a href="https://github.com/warith-harchaoui/ai-bunker/blob/main/PAYSAGE.md"
            class="font-medium text-brand-linktext hover:underline">Le tableau complet, avec une fiche par outil →</a>
        </p>
      </div>
    </section>
"""
