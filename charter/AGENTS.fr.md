# Comment travailler ici

Ce déploiement sert un modèle derrière une fenêtre de contexte bornée.
Travaillez par petites étapes autonomes par défaut : le plancher d'une session
est payé à chaque requête, et ce qui reste est la seule place dont vous
disposez.

## Règles de fonctionnement

1. Ne chargez jamais d'un seul coup un gros fichier, un journal, un diff, un
   arbre de dépendances ou la sortie d'une commande. Lisez par tranches d'une
   quatre-vingtaine de lignes et ne continuez que si la tranche suivante est
   réellement nécessaire.
2. Cherchez avant de lire : `grep`, `rg`, `find`, `git diff --stat`, un `sed -n`
   étroit. Une recherche ciblée coûte une fraction d'un fichier.
3. Bornez explicitement les commandes bavardes (`head`, `tail`, `sed -n`, un
   grep précis).
4. Ne relisez pas un fichier inchangé. Tenez plutôt une courte carte de
   travail : objectif, fichiers concernés, décisions prises, action suivante.
5. Une sortie tronquée n'est pas une erreur. Demandez la tranche suivante ;
   n'essayez pas de récupérer l'ensemble.
6. Gardez chaque étape étroite : inspecter, décider, modifier, vérifier. Aucun
   balayage de tout le dépôt une fois les fichiers concernés connus.
7. Avant un remaniement large, établissez d'abord la liste des fichiers, puis
   traitez-la un fichier à la fois.
8. À la compaction, gardez l'objectif, les décisions, les fichiers actifs et
   l'action suivante. Gardez les chemins et les plages de lignes, jamais les
   transcriptions brutes.

## La charte

`packs/**` porte les standards écrits de cette équipe. Seul un index de ces
pages est dans votre prompt ; lisez la page du domaine dans lequel vous
travaillez, une fois, et gardez la conclusion plutôt que le texte. À la
compaction, gardez le chemin.

## Les règles sont appliquées, pas suggérées

La sortie des outils est filtrée avant de vous parvenir : les secrets sont
expurgés et une courte note `[rules]` nomme ce qui s'est déclenché. Une valeur
expurgée est absente volontairement.

Une commande refusée revient sous la forme `[rules] <id> refuses this command`.
C'est une décision, pas une défaillance passagère : reformulez avec une cible
plus étroite ou une plage bornée. Ne la réessayez jamais à l'identique.
