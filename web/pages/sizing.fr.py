"""Dimensionnement — français."""

import pathlib as _p
import sys

sys.path.insert(0, str(_p.Path(__file__).parent))
import _figures as F

TITLE = "Quelle machine vous faut-il ? — ai-bunker"
DESCRIPTION = (
    "La vitesse de décodage est bornée par la bande passante mémoire divisée par les "
    "octets de poids actifs, pas par la capacité. Un modèle de plafond mémoire validé "
    "contre des mesures publiées, avec des prix relevés le 19/10/2026."
)

EXTRA_HEAD = """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    "headline": "Quelle machine pour auto-héberger un agent de code ?",
    "description": "Un modèle de plafond mémoire pour dimensionner un GPU destiné à des agents de code locaux, validé contre les mesures publiées du DGX Spark.",
    "inLanguage": "fr",
    "author": {"@type": "Person", "name": "Warith Harchaoui"}
  }
  </script>"""

ROOFLINE = F.roofline(
    {
        "title": "Vitesse de décodage selon la bande passante mémoire, pour un modèle dense et un mélange d'experts",
        "desc": (
            "Deux droites partant de l'origine. Le mélange d'experts, qui lit environ 9 Gio "
            "par token, monte fortement et dépasse 60 tokens par seconde à 819 Go/s. Le "
            "modèle dense de 24 milliards de paramètres, qui lit 25 Gio, monte environ trois "
            "fois moins vite. Une ligne rouge en pointillés marque le plancher de confort de "
            "20 tokens par seconde. Le DGX Spark, à 273 Go/s sur le modèle dense, est sous ce "
            "plancher."
        ),
        "x": "bande passante mémoire, Go/s",
        "y": "tokens/seconde",
        "polarity": "(plus haut est meilleur)",
        "floor": "20 tok/s — le plancher de confort",
        "l_moe": "Qwen3-Coder-Next 80B/3B, AWQ4 — ~9 Gio actifs",
        "l_dense": "Devstral Small 2 24B, dense FP8 — 25 Gio actifs",
        "p_m3": "Mac Studio M3 Ultra",
        "p_dense": "même machine, modèle dense",
        "p_spark": "DGX Spark — sous le plancher",
        "caption": (
            "Deux conclusions que la prose ne peut qu'affirmer. La droite du mélange d'experts "
            "est très au-dessus de celle du modèle dense : le meilleur modèle de code ouvert "
            "est aussi le plus rapide à servir. Et la bande passante du Spark le place sous le "
            "plancher quoi qu'il charge — la capacité ne rachète pas un mur de bande passante."
        ),
    }
)

BODY = (
    r"""
    <section class="mx-auto max-w-6xl px-5 pt-14 pb-10 sm:pt-20">
      <p class="mb-4 text-sm font-medium uppercase tracking-widest text-brand-linktext">Dimensionnement</p>
      <h1 class="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        Quelle machine vous faut-il ?
      </h1>
      <p class="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-700 dark:text-neutral-300">
        La capacité décide si un modèle charge. <strong class="font-semibold">La bande passante
        décide s'il est utilisable.</strong> Dimensionner sur la première en ignorant la seconde,
        c'est acheter une machine pleine de mémoire qui répond trop lentement pour être gardée.
      </p>
      <p class="mt-5 max-w-2xl text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">
        La notation de cette page, une fois pour toutes. Un <strong class="font-semibold">GPU</strong>
        est un processeur graphique, et le <strong class="font-semibold">VRAM</strong> sa mémoire
        vidéo. <strong class="font-semibold">B</strong> compte les milliards de paramètres : un
        modèle <em>24B</em> porte 24 milliards de poids.
        <strong class="font-semibold">bf16</strong>, <strong class="font-semibold">FP8</strong>,
        <strong class="font-semibold">Q4</strong> et <strong class="font-semibold">AWQ4</strong>
        disent sur combien de bits chaque poids est stocké : le format <em>brain floating
        point</em> sur 16 bits, la virgule flottante sur 8 bits, une quantification sur 4 bits,
        et une quantification des poids sur 4 bits tenant compte des activations.
        <strong class="font-semibold">Go</strong> est le gigaoctet ;
        <strong class="font-semibold">Gio</strong> le gibioctet, celui des puissances de deux,
        environ 7 % plus grand. <strong class="font-semibold">tok/s</strong> compte les tokens par
        seconde. Un <strong class="font-semibold">MoE</strong> est un mélange d'experts, un modèle
        où chaque token n'active qu'une fraction des poids, et un
        <strong class="font-semibold">VLM</strong> est un modèle vision-langue, qui lit les images
        aussi bien que le texte.
      </p>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-14">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">Le fait qui décide de tout</h2>
        <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          Générer un token exige de lire une fois chaque poids <em>actif</em> depuis la mémoire.
          Le plafond de vitesse est donc arithmétique :
        </p>
        <p class="mt-6 rounded-2xl border border-neutral-200 bg-white px-6 py-5 text-center font-mono text-sm dark:border-neutral-800 dark:bg-[#141416] sm:text-base">
          tokens/seconde &nbsp;≤&nbsp; bande&nbsp;passante &nbsp;/&nbsp; octets&nbsp;de&nbsp;poids&nbsp;actifs
        </p>
        <p class="mt-6 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          Les mesures publiées du DGX Spark le confirment presque exactement. Le GB10 a
          273&nbsp;Go/s : Qwen3&nbsp;8B en bf16 (~16&nbsp;Go) est mesuré à
          <strong>13,6&nbsp;tok/s</strong> contre un plafond de 17,1, et
          Llama&nbsp;3.1&nbsp;70B en Q4 (~40&nbsp;Go) à <strong>4,4&nbsp;tok/s</strong> contre
          6,8. Ce projet suppose 70 % de rendement, ce qui est conservateur face aux deux.
        </p>
        """
    + ROOFLINE
    + r"""
        <p class="mt-6 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
          <strong class="font-semibold">Le meilleur modèle de code ouvert disponible est aussi le
          plus rapide à servir.</strong> Choisir un modèle plus petit pour aller plus vite est
          ici exactement à l'envers — et c'est pourquoi la recommandation ci-dessous coûte moins
          cher qu'il n'y paraît.
        </p>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-5 py-14">
      <h2 class="font-serif text-3xl font-semibold tracking-tight">Pour une petite équipe, le VRAM achète de la qualité</h2>
      <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        Deux personnes ont besoin de deux séquences concurrentes au-dessus de 20&nbsp;tok/s.
        C'est une barre basse : la mémoire doit donc aller dans un meilleur modèle, pas dans de
        la concurrence.
      </p>
      <div class="mt-8 overflow-x-auto">
        <table class="w-full min-w-[40rem] text-left text-sm">
          <thead class="border-b border-neutral-300 text-xs uppercase tracking-widest text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
            <tr><th class="py-3 pr-4 font-medium">Machine</th><th class="py-3 pr-4 text-right font-medium">Coût</th><th class="py-3 pr-4 text-right font-medium">Vitesse</th><th class="py-3 pr-4 text-right font-medium">Séquences</th><th class="py-3 text-right font-medium">Contexte</th></tr>
          </thead>
          <tbody class="[&amp;_td]:border-b [&amp;_td]:border-neutral-200 [&amp;_td]:py-3 dark:[&amp;_td]:border-neutral-800">
            <tr class="bg-brand-blue/5"><td class="pr-4 font-medium">L'Apple Silicon que vous avez déjà (M2 Max 96 Go)</td><td class="pr-4 text-right font-mono font-semibold">0 $</td><td class="pr-4 text-right font-mono">27 tok/s</td><td class="pr-4 text-right font-mono">5</td><td class="text-right font-mono">256k</td></tr>
            <tr class="bg-brand-blue/5"><td class="pr-4 font-medium">Mac Studio M3 Ultra 96 Go</td><td class="pr-4 text-right font-mono font-semibold">5 600 $</td><td class="pr-4 text-right font-mono">55 tok/s</td><td class="pr-4 text-right font-mono">23</td><td class="text-right font-mono">256k</td></tr>
            <tr><td class="pr-4">RTX PRO 5000 Blackwell 72 Go</td><td class="pr-4 text-right font-mono">12 600 $</td><td class="pr-4 text-right font-mono">90 tok/s</td><td class="pr-4 text-right font-mono">16</td><td class="text-right font-mono">256k</td></tr>
            <tr><td class="pr-4">RTX PRO 5000 Blackwell 48 Go</td><td class="pr-4 text-right font-mono">10 200 $</td><td class="pr-4 text-right text-neutral-500 dark:text-neutral-400" colspan="3">le meilleur modèle n'y tient pas</td></tr>
            <tr><td class="pr-4">DGX Spark 128 Go</td><td class="pr-4 text-right font-mono">6 950 $</td><td class="pr-4 text-right font-mono text-brand-red">18 tok/s</td><td class="pr-4 text-right font-mono">0</td><td class="text-right text-neutral-500 dark:text-neutral-400">sous le plancher</td></tr>
          </tbody>
        </table>
      </div>
      <div class="mt-8 grid gap-5 sm:grid-cols-2">
        <p class="rounded-2xl border border-neutral-200 p-5 leading-relaxed text-neutral-700 dark:border-neutral-800 dark:text-neutral-300">
          <strong class="font-semibold text-neutral-900 dark:text-neutral-100">La carte NVIDIA
          48 Go ne peut pas faire tourner le meilleur modèle du tout.</strong> Sur NVIDIA le
          ticket d'entrée est la carte 72 Go à 12 600 $ ; sur Apple c'est un Mac Studio à
          5 600 $, parce que la mémoire unifiée est bon marché et pas la GDDR7 — <em>graphics
          double data rate</em>, septième génération.
        </p>
        <p class="rounded-2xl border border-neutral-200 p-5 leading-relaxed text-neutral-700 dark:border-neutral-800 dark:text-neutral-300">
          <strong class="font-semibold text-neutral-900 dark:text-neutral-100">Le DGX Spark perd
          sur la bande passante, pas sur la mémoire.</strong> Il a 128 Go et sert le meilleur
          modèle de code à 18 tok/s. En acheter plusieurs n'aide pas : la bande passante ne
          s'additionne pas entre machines pour un même flux.
        </p>
      </div>
    </section>

    <section class="border-y border-neutral-200/70 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/40">
      <div class="mx-auto max-w-6xl px-5 py-14">
        <h2 class="font-serif text-3xl font-semibold tracking-tight">La recommandation</h2>
        <ol class="mt-8 space-y-6">
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-xs uppercase tracking-widest text-neutral-500 dark:text-neutral-400">Étape zéro — gratuite</p>
            <h3 class="mt-2 text-lg font-semibold">Mesurer le Mac que vous avez déjà</h3>
            <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">L'arithmétique
              dit qu'un M2&nbsp;Max 96&nbsp;Go sert déjà Qwen3-Coder-Next à ~27&nbsp;tok/s avec
              une fenêtre de 256k. C'est une <em>projection, pas une mesure</em>, et cette
              différence est tout l'argument du projet — donc tirez le modèle, lancez une vraie
              session, et chronométrez un vrai patch avant de dépenser quoi que ce soit.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-xs uppercase tracking-widest text-neutral-500 dark:text-neutral-400">Si ça ne suffit pas — 5 600 $</p>
            <h3 class="mt-2 text-lg font-semibold">Mac Studio M3 Ultra 96 Go</h3>
            <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">819&nbsp;Go/s,
              le double du M2&nbsp;Max, ~55&nbsp;tok/s sur le meilleur modèle de code ouvert,
              tenant le modèle 80B plus un VLM 8B plus l'embedder en même temps. Une machine
              complète : pas de châssis à spécifier, pas de carte 600&nbsp;W, pas de rack,
              270&nbsp;W et silencieuse.</p>
          </li>
          <li class="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-[#141416]">
            <p class="font-mono text-xs uppercase tracking-widest text-neutral-500 dark:text-neutral-400">S'il faut la vision sous schéma — 12 600 $</p>
            <h3 class="mt-2 text-lg font-semibold">RTX PRO 5000 Blackwell 72 Go</h3>
            <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">La seule chose
              qu'Apple ne sait pas faire aujourd'hui. Piloter un modèle de vision depuis un agent
              implique du décodage contraint, vLLM a le guided decoding, et vLLM n'a pas de
              runtime macOS — donc <em>vision&nbsp;+&nbsp;schéma ⇒ Linux&nbsp;+&nbsp;NVIDIA
              discret</em>.</p>
          </li>
        </ol>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-5 py-14">
      <h2 class="font-serif text-3xl font-semibold tracking-tight">La mise à niveau la moins chère n'est pas du matériel</h2>
      <p class="mt-5 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        Le dimensionnement est plus sensible au <strong class="font-semibold">contexte vivant
        moyen par session</strong> qu'à presque toute la facture — et ce chiffre appartient au
        harnais, pas à la carte.
      </p>
      <div class="mt-8 grid gap-5 sm:grid-cols-2">
        <div class="rounded-2xl border border-brand-green/40 bg-brand-green/5 p-6">
          <p class="font-mono text-3xl font-semibold text-brand-green">23</p>
          <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">séquences
            sur un Mac Studio M3 Ultra à <strong>32k</strong> de contexte vivant — lectures
            bornées, charte indexée, compaction précoce</p>
        </div>
        <div class="rounded-2xl border border-brand-orange/40 bg-brand-orange/5 p-6">
          <p class="font-mono text-3xl font-semibold text-brand-orange">11</p>
          <p class="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">à
            <strong>64k</strong> — un agent à qui on donne une fenêtre et qu'on laisse la
            remplir, pour une production identique</p>
        </div>
      </div>
      <p class="mt-8 max-w-3xl leading-relaxed text-neutral-700 dark:text-neutral-300">
        Un agent qui colle tout le document de standards dans chaque prompt, lit les fichiers en
        entier plutôt que par tranches, et ne compacte jamais
        <strong class="font-semibold">divise la machine par deux pour une production
        identique</strong>. C'est l'argument mesurable derrière tout le reste.
      </p>
      <div class="mt-10 rounded-2xl border border-neutral-200 bg-neutral-50 p-6 dark:border-neutral-800 dark:bg-neutral-900/40">
        <h3 class="font-semibold">Une note sur les prix</h3>
        <p class="mt-3 leading-relaxed text-neutral-700 dark:text-neutral-300">
          Ils ont bougé violemment et ils n'ont pas fini. La RTX PRO 6000 est sortie à 8 565 $ en
          mars 2025 et se vend ~16 000 $ aujourd'hui ; le DGX Spark est passé de 3 999 $ à
          6 950 $ pour sa configuration 128&nbsp;Go. <strong class="font-semibold">Un
          dimensionnement 2026 fait sur des prix 2025 est faux d'un facteur deux.</strong> Relevé
          le 19/10/2026 ; relever à nouveau avant d'acheter.
        </p>
      </div>
      <p class="mt-10">
        <a href="https://github.com/warith-harchaoui/ai-bunker/blob/main/docs/SIZING.md"
          class="font-medium text-brand-linktext hover:underline">L'étude complète, avec la commande derrière chaque chiffre →</a>
      </p>
    </section>
"""
)
