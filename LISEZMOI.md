# ai-bunker

[🇫🇷](https://github.com/warith-harchaoui/ai-bunker/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/ai-bunker/blob/main/README.md)

![Licence](https://img.shields.io/badge/licence-BSD--3--Clause-blue)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![Local-first](https://img.shields.io/badge/local--first-oui-brightgreen)
![État](https://img.shields.io/badge/état-0.2.0--alpha-orange)

`ai-bunker` fait partie de la suite **AI Helpers**, où AI est l'anglais pour
intelligence artificielle. C'est la couche de service souveraine : **un GPU,
une charte, tous les agents de code** — un GPU étant un processeur graphique,
la carte ou la puce qui tient les poids d'un modèle et fait l'arithmétique de
la réponse.

[🌍 AI Helpers](https://deraison.ai/ai-helpers)

---

Un agent de code — Claude Code, OpenCode, Cursor, Continue — est un programme
qui dépense votre fenêtre de contexte à votre place. Il lit des fichiers, appelle
des outils, et paie chaque token qu'il charge. Quand cet agent parle à un modèle
que vous hébergez vous-même, deux choses décident si l'installation est
utilisable : **combien de contexte le serveur sert vraiment**, et **qui compte
les tokens**.

ai-bunker répond aux deux. C'est une passerelle compatible OpenAI, posée devant
votre propre GPU, qui porte trois choses qu'aucun harnais d'agent ne porte seul :

1. **Une charte** — les standards de l'équipe, versionnés, stockés une fois,
   servis à tous les clients sous forme d'**index** plutôt que de mur de texte.
2. **Des règles appliquées, pas suggérées** — des expressions régulières
   versionnées qui censurent les secrets avant qu'ils n'entrent dans une session
   et refusent les commandes qui font exploser un contexte.
3. **Un budget que le serveur compte vraiment** — avec son propre tokenizer, et
   non avec l'estimation du client.

Le troisième point est la raison d'être du projet. Voir
[Pourquoi c'est au serveur de compter](#pourquoi-cest-au-serveur-de-compter).

## La promesse

ai-bunker est **souverain par construction** : c'est un serveur que vous lancez,
sur un GPU que vous contrôlez. Trois cas honnêtes, dans l'ordre habituel de la
suite :

1. **Local garanti.** La passerelle, la charte, le moteur de règles, la
   comptabilité du budget et le dimensionnement matériel tournent tous sur votre
   infrastructure. Pas de télémétrie, pas de compte, aucune dépendance SaaS —
   du *software as a service*, autrement dit du logiciel en tant que service,
   donc l'ordinateur de quelqu'un d'autre. Rien de ce qui entre dans un prompt
   ne quitte la machine qui sert.

2. **Les réserves, nommées.** Trois, et seulement trois. **(a)** Les poids des
   modèles sont téléchargés une fois, depuis Hugging Face ou le registre Ollama,
   au premier service. **(b)** Si vous configurez délibérément une **route
   premium** — les 20 % de requêtes que le document stratégique envoie vers un
   modèle frontière — alors ces requêtes-là, et elles seules, sortent de votre
   réseau, vers le fournisseur que vous avez nommé. La passerelle les journalise
   toutes. **(c)** `ai-bunker catalog update` rafraîchit le catalogue de modèles
   depuis un annuaire public ; c'est optionnel, et le catalogue embarqué
   fonctionne hors ligne.

3. **Votre décision.** La route premium est coupée par défaut et doit être
   écrite dans un fichier de configuration par un humain. Un déploiement sans
   fournisseur `remote` configuré ne peut pas atteindre Internet à l'inférence,
   et `ai-bunker doctor` le dit à voix haute.

## Principes de conception

Trois, et ils décident de tout le reste.

1. **Les règles et les savoirs appartiennent à l'infrastructure, pas à la
   configuration de chaque développeur.** Un standard qui vit dans les dotfiles
   de chacun est un standard qui dérive : adopté inégalement, contourné sous
   pression, et silencieusement différent sur la machine où ça compte. Mis
   derrière le point d'entrée, il en existe exactement une copie, versionnée, et
   aucun moyen d'utiliser le modèle sans elle.

   Anthropic dit la même chose de ses propres fichiers d'instructions, ce qui est
   un aveu plus fort que tout ce que ce projet pourrait affirmer à sa place :

   > Claude treats them as context, **not enforced configuration**. To block an
   > action regardless of what Claude decides, use a PreToolUse hook instead.
   >
   > (« Claude les traite comme du contexte, **pas comme de la configuration
   > appliquée**. Pour bloquer une action quoi que Claude décide, utilisez
   > plutôt un hook PreToolUse. »)
   >
   > — Anthropic, [*How Claude remembers your project*](https://code.claude.com/docs/en/memory),
   > à propos de `CLAUDE.md` et de la mémoire automatique

   Rien dans cette phrase n'est propre à un éditeur. Un `CLAUDE.md`, l'`AGENTS.md`
   que lisent OpenCode, Aider et goose, un style maison collé dans un prompt
   système : ce sont tous des choses qu'on *dit* au modèle, et une chose qu'on dit
   au modèle est une chose que le modèle peut mettre en balance avec une autre.
   Appliquer est un mécanisme différent d'instruire, et cela doit vivre quelque
   part où le modèle n'a pas voix au chapitre. La réponse d'Anthropic est un hook
   sur la machine du développeur, et les harnais open source offrent leurs propres
   équivalents ; les deux sont le bon outil pour ce qui se passe avant qu'une
   requête existe. La réponse de ce projet est le point d'entrée, pour la raison du
   paragraphe au-dessus : un hook reste un fichier sur un portable, et il ne lie
   que le harnais qui le lit.

   C'est pourquoi la charte est appliquée pour **tous** les clients — les
   propriétaires comme les open source — et pourquoi les kits de
   [`clients/`](clients/README.md) sont volontairement minces. Tout client qui
   parle le protocole compatible OpenAI reçoit les mêmes règles, qu'on lui ait
   écrit un kit ou non.

2. **Indexer, ne pas concaténer.** La façon tentante de donner ses standards à un
   modèle est de tout coller dans le prompt système. Sur une fenêtre de 32k, cela
   dépense le contexte avant la première question ; sur une fenêtre de 256k, cela
   coûte encore de l'argent réel à chaque tour, et le modèle n'en lit rien.
   Annoncer plutôt un index d'environ 1 000 caractères et laisser le modèle
   ouvrir la seule fiche dont il a besoin. Une fiche ne coûte rien tant qu'elle
   n'est pas ouverte : la charte peut donc être vaste.

3. **Mesurer, ne pas supposer.** Chaque chiffre de ce document a été compté, pas
   estimé — et les deux problèmes les plus coûteux rencontrés jusqu'ici étaient
   tous deux invisibles à l'inspection et évidents à la mesure. Voir la section
   suivante.

## Pourquoi c'est au serveur de compter

Le 25/09/2026, une session OpenCode s'est crue sous sa limite et a envoyé
**40 433 tokens** à un serveur configuré pour 32 768. Le serveur a compté pour de
vrai, a refusé la requête entière, et la session est morte.

Le client ne mentait pas. Il estimait, avec sa propre règle de tokenisation, plus
optimiste que celle de Mistral sur le français et sur le code. L'écart était de
55 %.

Le correctif habituel est de **déclarer au client un contexte plus bas que ce
que le serveur sert** — 26 000 contre 32 768 — pour que l'optimisme du client
soit absorbé par une marge. Ça marche, à condition qu'un test empêche quelqu'un
de « réparer » ce nombre vers le haut plus tard. Mais c'est le contournement
d'un problème structurel : **le seul qui peut compter juste est
celui qui tient le tokenizer**, et c'est le serveur.

Donc ai-bunker compte. `GET /v1/budget` renvoie, pour un client donné et une
charte donnée, le plancher mesuré d'une session et ce qu'il reste pour
travailler :

```text
schémas des outils (7) — client                      3164 tokens    47 %
prompt système du client + instructions du poste     2345 tokens    35 %
charte du projet (équivalent AGENTS.md)               905 tokens    13 %
index des savoirs                                     353 tokens     5 %
PLANCHER                                             6767 tokens

contexte déclaré                                    26000
  − marge de compaction                              6000
  = la compaction part à                            20000
  − plancher                                         6767
  = conversation avant compaction                   13233 tokens
```

Ce sont des chiffres réels, mesurés au relais le 28/09/2026. La même mesure a
attrapé ce qu'aucune convention n'aurait vu : avant correction, **59 skills**
installées sur un poste étaient injectées dans chaque prompt — **17 754 tokens,
68 % d'un plancher de 26 226** pour un contexte déclaré à 26 000. La session
compactait au premier tour, n'avait rien à compacter, et bouclait
`build → compaction → build` indéfiniment, en renvoyant 8 tokens par tour et en
occupant le GPU pour rien. Le harnais n'en disait pas un mot.

ai-bunker **refuse de servir** une session dont le plancher laisse moins qu'un
nombre configurable de tokens (5 000 par défaut) à la conversation, et nomme le
composant responsable. Un garde-fou ne sert que s'il se déclenche avant le
travail.

`ai-bunker budget` le fait aujourd'hui, poste par poste et de façon bloquante :

```text
  COMPONENT                        TOKENS   SHARE  OWNER
  agent skills (59)                17,754    68%  client
  tool schemas (7)                  3,164    12%  client
  client system prompt              2,345     9%  client
  charter                             905     3%  ai-bunker
  knowledge index                     353     1%  ai-bunker
  FLOOR — paid on every request    24,521

  VERDICT  UNUSABLE — this session cannot work
  ⚠  Le plancher (24 521) atteint ou dépasse le seuil de compaction (20 000).
     La compaction partira à chaque tour sans rien pouvoir réduire.
  Attaquer agent skills (59) en premier : 68 % du plancher, propriété du client.
```

Deux détails qui font tout. **L'attribution** : un plancher qu'on ne peut pas
décomposer est un plancher qu'on ne peut pas réduire, donc chaque token est
imputé à un propriétaire nommé — y compris le nôtre, ce qui permet de vérifier
l'affirmation selon laquelle la charte et l'index coûtent moins de 5 % de la
fenêtre. Et **`--gate`** : le verdict devient le code de sortie, parce qu'une
vérification qui signale un échec et sort en zéro n'est pas une vérification.

## Quelle machine faut-il

C'est la question à laquelle ai-bunker existe pour répondre concrètement.
L'étude complète, prix relevés le 19/10/2026 et commande derrière chaque
chiffre, est dans **[docs/SIZING.md](docs/SIZING.md)**. Voici le raisonnement
et la réponse.

Une ligne de notation traverse tout ce qui suit ; la voici une fois pour
toutes. **B** compte les milliards de paramètres : un modèle *24B* porte
24 milliards de poids. **bf16**, **FP8**, **Q4** et **AWQ4** disent sur combien
de bits chacun de ces poids est stocké — bf16 est le format *brain floating
point* sur 16 bits dans lequel les modèles sont entraînés, FP8 de la virgule
flottante sur 8 bits, Q4 une quantification sur 4 bits, et AWQ4 une
quantification des poids sur 4 bits tenant compte des activations, qui choisit
ce qu'elle arrondit en regardant quels poids les activations utilisent
vraiment. **Go** est le gigaoctet ; **Gio** le gibioctet, 2³⁰ octets, environ
7 % de plus qu'un gigaoctet — d'où un modèle 24B à 8 bits par poids qui se lit
25 Gio et non 24. **tok/s** compte les tokens par seconde, la seule vitesse que
ressente le lecteur d'un texte généré. Et le **VRAM** est la *video
random-access memory*, la mémoire vidéo rapide posée contre un processeur
graphique, qui sur une carte dédiée est toute la place dont dispose un modèle.

### La contrainte est la bande passante, pas la capacité

Générer un token exige de lire une fois chaque poids **actif** depuis la
mémoire. La capacité décide si le modèle charge ; la bande passante décide à
quelle vitesse il répond :

```
tokens/seconde  ≤  bande passante mémoire  /  octets de poids actifs
```

Les mesures publiées du DGX Spark le confirment presque exactement. Le GB10 a
273 Go/s : Qwen3 8B en bf16 (~16 Go) est mesuré à **13,6 tok/s** contre un
plafond de 17,1, et Llama 3.1 70B en Q4 (~40 Go) à **4,4 tok/s** contre 6,8.
`ai-bunker` suppose 70 % de rendement, conservateur face aux deux.

### Le mot qui fait tout le travail est *actif*

Pour un modèle dense, les poids actifs sont tout le checkpoint. Pour un
**mélange d'experts**, ils n'en sont qu'une fraction — et cette fraction
déplace le mur de presque un ordre de grandeur :

| Modèle | Total | Actif/token | Plafond à 819 Go/s |
|---|---:|---:|---:|
| Devstral Small 2 24B, dense, FP8 | 25 Gio | 25 Gio | ~23 tok/s |
| Qwen3-Coder-Next 80B/3B MoE, AWQ4 | 45 Gio | ~9 Gio | ~62 tok/s |

**Le meilleur modèle de code ouvert disponible est aussi le plus rapide à
servir.** Choisir un modèle plus petit pour aller plus vite est ici exactement
à l'envers — et c'est pourquoi la recommandation ci-dessous coûte moins cher
qu'il n'y paraît.

### Pour une petite équipe, le VRAM achète de la qualité, pas du débit

Deux personnes ont besoin de deux séquences concurrentes au-dessus de 20 tok/s.
C'est une barre basse : la mémoire doit donc aller dans un meilleur modèle,
pas dans de la concurrence.

```bash
ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b
```

| Machine | Coût | Vitesse | Séquences | Contexte |
|---|---:|---:|---:|---:|
| **L'Apple Silicon que vous avez déjà** (M2 Max 96 Go) | **0 $** | 27 tok/s | 5 | 256k |
| **Mac Studio M3 Ultra 96 Go** | **5 600 $** | **55 tok/s** | 23 | 256k |
| RTX PRO 5000 Blackwell 72 Go | 12 600 $ | 90 tok/s | 16 | 256k |
| RTX PRO 5000 Blackwell 48 Go | 10 200 $ | *le meilleur modèle n'y tient pas* | — | — |
| DGX Spark 128 Go | 6 950 $ | 18 tok/s — sous le plancher | 0 | — |

Deux choses méritent d'être dites à voix haute. **La carte NVIDIA 48 Go ne peut
pas faire tourner le meilleur modèle du tout** — sur NVIDIA, le ticket d'entrée
est la carte 72 Go à 12 600 $, là où sur Apple c'est un Mac Studio à 5 600 $,
parce que la mémoire unifiée est bon marché et pas la GDDR7 — *graphics double
data rate*, septième génération, la mémoire rapide des cartes dédiées. Et **le
DGX Spark
perd sur la bande passante, pas sur la mémoire** : il a 128 Go et sert le
meilleur modèle de code à 18 tok/s. En acheter plusieurs n'y change rien : la
bande passante ne s'additionne pas entre machines pour un même flux.

### La recommandation

**L'étape zéro est gratuite : mesurez le Mac que vous avez déjà.** L'arithmétique
dit qu'un M2 Max 96 Go sert déjà Qwen3-Coder-Next à ~27 tok/s avec une fenêtre
de 256k. C'est une projection, pas une mesure, et cette différence est tout
l'argument de ce projet — donc tirez le modèle, lancez une vraie session, et
chronométrez un vrai patch avant de dépenser quoi que ce soit.

**Si ça ne suffit pas : Mac Studio M3 Ultra 96 Go, ~5 600 $.** 819 Go/s, le
double du M2 Max, ~55 tok/s sur le meilleur modèle de code ouvert, tenant le
modèle 80B plus un modèle vision-langue 8B — un VLM, qui lit les images aussi
bien que le texte — plus l'embedder en même temps. Une machine complète —
pas de châssis à spécifier, pas de carte 600 W, pas de rack, 270 W et
silencieuse. Pour une structure de deux personnes, c'est la différence entre
avoir un serveur et avoir un projet de serveur à construire.

**S'il vous faut la vision avec une sortie contrainte par schéma : RTX PRO 5000
Blackwell 72 Go, ~12 600 $.** C'est la seule chose qu'Apple ne sait pas faire
aujourd'hui. Piloter un VLM depuis un agent implique du décodage contraint,
vLLM a le guided decoding, et vLLM n'a pas de runtime macOS — donc *vision +
schéma ⇒ Linux + NVIDIA discret*. La 72 Go est la moins chère qui tienne le
meilleur modèle de code ; la 48 Go est la même puce, le même bus et les mêmes
300 W, et ne le tient pas.

### Acheter n'est pas évidemment la bonne décision à cette taille

| Voie | Coût | |
|---|---:|---|
| Mesurer le Mac existant | **0 $** | Commencer ici |
| Mac Studio M3 Ultra | 5 600 $ une fois | Rentabilisé face à deux abonnements en ~14 mois |
| Nœud RTX PRO 5000 72 Go | 12 600 $ une fois | Justifié par la seule exigence de vision |
| Louer un GPU équivalent | ~350 $/mois | Seuil face au Mac Studio : ~16 mois |
| Routes premium seules | ~400 $/mois | Pas de matériel, pas d'exploitation, pas de souveraineté |

Si la souveraineté est une préférence, louez ou routez. Si c'est une exigence —
code client sous NDA, un accord de confidentialité ; résidence des données
dans un appel d'offres — le tableau
est sans objet et la réponse est la machine.

### La mise à niveau la moins chère n'est pas du matériel

Le dimensionnement est plus sensible au **contexte vivant moyen par session**
qu'à presque toute la facture, et ce chiffre appartient au harnais, pas à la
carte.

| Contexte vivant moyen | Séquences sur un Mac Studio M3 Ultra |
|---:|---:|
| 32k — lectures bornées, charte indexée, compaction précoce | **23** |
| 64k — un agent à qui on donne une fenêtre et qu'on laisse la remplir | **11** |

Un agent qui colle tout le document de standards dans chaque prompt, lit les
fichiers en entier plutôt que par tranches, et ne compacte jamais, divise la
machine par deux pour une production identique. C'est l'argument mesurable
derrière tout le reste de ce dépôt.

Et il est désormais **mesuré**, plus seulement calculé. Sur un Apple M2 Max
servant un modèle 4B via Ollama, le débit de décodage tombe d'un **facteur
deux environ** entre un prompt de 216 tokens et un prompt de 32k — 1,67×,
1,93× et 2,20× sur trois exécutions, la pente ajustée tenant entre 0,99 et
1,35 ms par millier de tokens de contexte. Le contexte n'est pas qu'un coût
mémoire qui décide si un modèle tient : c'est une lecture payée sur chaque
token, indéfiniment.

La même mesure dit quelque chose de moins confortable : le débit absolu a bougé
de **1,6× entre exécutions** sur un portable par ailleurs au repos, alors que
l'écart *à l'intérieur* d'une exécution restait sous 1,6 tok/s. Un chiffre
unique et assuré, tiré d'une machine qui fait aussi tourner un éditeur, ne vaut
pas grand-chose : `scripts/bench_context.py` signale donc les écarts larges et
les points non monotones au lieu d'imprimer un tableau propre. Chiffres,
méthode et limites dans [`docs/SIZING.md`](docs/SIZING.md).

### Une note sur les prix

Ils ont bougé violemment et ils n'ont pas fini. La RTX PRO 6000 est sortie à
8 565 $ en mars 2025 et se vend ~16 000 $ aujourd'hui ; le DGX Spark est passé
de 3 999 $ à 6 950 $ pour sa configuration 128 Go. **Un dimensionnement 2026
fait sur des prix 2025 est faux d'un facteur deux.** Relever les prix avant
d'acheter ; le catalogue enregistre ce qui a été vu, et quand.

## La charte

Les standards de l'équipe, annoncés plutôt que livrés.

La façon tentante de donner ses standards à un modèle est de les coller dans le
prompt système. C'est aussi celle qui ne marche pas, pour une raison
arithmétique et non esthétique : le prompt système est le **plancher** de la
session — payé à chaque requête, hors d'atteinte de la compaction. Des
standards collés là sont dépensés avant la première question, à chaque tour,
que le modèle en ait eu besoin ou non.

ai-bunker livre donc un index :

```text
$ ai-bunker charter
charter      charter
fingerprint  aa9fcf72c7ff3e40ef72b92d659c589f40fbdfee
packs        3  (default, javascript, python)
pages        5
floor cost   972 tokens  (operating rules + index, every request)
not loaded   2,608 characters across the pages, read on demand
index vs all   4.6x  (1,043 tokens if every page were pasted in, 228 as an index)
```

L'index nomme les packs et leurs fiches ; le modèle ouvre la seule fiche que la
tâche appelle, par tranches, avec l'outil de lecture habituel.

Quatre choses que l'index doit dire — et leur formulation est choisie, pas
générée, parce que chaque mot est payé à chaque requête : les fiches existent ;
elles ne sont **pas** dans ce prompt (sinon un modèle interrogé sur le nommage
répond par habitude au lieu d'ouvrir la fiche) ; **quand** en ouvrir une
(« disponible si besoin » n'est pas une instruction qu'un modèle exécute) ; et
**une à la fois** (un agent à qui l'on dit de consulter la charte lira sinon le
pack entier et dépensera la fenêtre qu'il économisait).

L'empreinte sert deux fois : clé de cache — un moteur de service ressert un
préfixe inchangé quasi gratuitement — et provenance, car une session peut
enregistrer sous quelle charte elle a tourné, ce qui fait la différence entre
« les règles ont été suivies » et « certaines règles ont été suivies ».

## Les règles

Un format, deux portées, trois sévérités — et chaque règle est livrée avec les
cas qu'elle doit attraper et ceux qu'elle doit laisser passer, qui tournent en
intégration continue.

```text
$ ai-bunker rules --check
  rules loaded                          27
  assertions passed                    247
  assertions failed                      0
  rules carrying evidence            100%
```

Les règles **`output`** filtrent ce que le monde tend à l'agent : un secret en
route vers la transcription, une instruction glissée dans une page web. Les
règles **`command`** filtrent ce que le modèle demande d'exécuter, avant que ça
tourne — le point d'application qu'aucun client ne contourne. Un **`BLOCKER`**
refuse, une règle **`GATED`** refuse jusqu'à ce qu'un motif écrit soit
enregistré, un **`WARNING`** annote et laisse passer.

L'essentiel de l'intérêt est dans les contournements : un motif ancré sur
`secret\s*=` qui passait à côté d'`AWS_SECRET_ACCESS_KEY=`, un préfixe `sudo`
qui défaisait trois règles distinctes, une affectation d'environnement qui
défaisait les ancres, une ligne qui n'était pas une seule commande, et les
options propres de `git` qui franchissaient les neuf règles git. Chacun a été
trouvé en envoyant une charge dans le vrai moteur, chacun est un test, et
chacun est expliqué avec son raisonnement dans
**[`docs/REGLES.md`](docs/REGLES.md)**.

## La passerelle

La pièce qui rend les trois autres applicables. Tout client qui parle OpenAI
parle ai-bunker, et reçoit la charte, le moteur de règles et un vrai budget de
tokens **sans avoir été configuré pour** — c'est tout l'argument qui justifie
de mettre cela au point d'entrée plutôt que dans le harnais de chaque
développeur. Un plugin se désactive en éditant un fichier ; un autre harnais ne
l'a simplement jamais eu.

```bash
ai-bunker serve                    # localhost:8000
export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="$AI_BUNKER_API_KEY"
```

### Quatre étapes, et l'ordre porte le sens

**1 — Filtrer les sorties d'outils entrantes.** Un message `role: "tool"` est
du texte que le monde vient de tendre à l'agent. Il est filtré et marqué avant
que quoi que ce soit d'autre le regarde. Les tours utilisateur et assistant
sont laissés intacts : censurer les propres mots de l'utilisateur serait à la
fois surprenant et inutile.

**2 — Injecter la charte.** En premier bloc système, à position stable, parce
que le cache de préfixe d'un moteur de service ne sert que tant que la tête du
prompt est identique octet pour octet. Idempotent : une conversation rejouée
n'accumule pas de copies.

**3 — Mesurer et faire respecter le budget.** Compté avec le tokenizer du
moteur lui-même. Une session sans place pour travailler est refusée **ici**,
avec le composant responsable nommé, plutôt que de tomber plus loin en erreur
de longueur de contexte sur laquelle personne ne peut agir :

```json
HTTP 413
{ "error": {
    "code": "context_budget_exhausted",
    "attack_first": "agent skills (59)",
    "budget": { "floor_tokens": 24521, "working_tokens": -4521, "verdict": "unusable" }
}}
```

**4 — Filtrer les appels d'outils sortants.** Quand le modèle répond par un
`tool_call` portant une commande shell, **cette commande n'a pas encore
tourné**. C'est le seul point d'application qu'aucun client ne peut contourner.
Le refus revient sous la forme d'un résultat d'outil, parce qu'un agent qui
reçoit un 4xx réessaie le même appel, tandis qu'un agent qui reçoit un résultat
d'outil le lit.

Les étapes 1 et 4 sont les deux portées du moteur de règles, et une passerelle
est le premier endroit où les deux existent en même temps.

### Surface

| | |
|---|---|
| `GET /health` | Vivacité, et les faits qu'un déploiement ne devrait pas avoir à deviner |
| `GET /v1/models` | Modèles routables, chacun avec le contexte **déclaré** |
| `POST /v1/chat/completions` | Atomique et streaming. Le pipeline complet |
| `POST /v1/embeddings` | Relayé tel quel |
| `POST /v1/images/generations` | Relayé vers le besoin `image`, ou un 501 disant qu'aucun n'est configuré |
| `POST /v1/budget` | Mesurer le plancher d'une requête sans l'envoyer |
| `GET /v1/charter`, `GET /v1/charter/{ref}` | L'index, et une fiche à la demande |
| `GET /v1/decisions` | La fin du journal d'audit, jamais le texte apparié |
| `GET /gui` | Le tableau de bord d'exploitation |

`/v1/models` annonce un contexte **inférieur** au réel, délibérément. Déclarer
la vérité serait honnête et casserait : la marge est la seule protection
pendant qu'un tour grossit.

`/v1/budget` permet à un client de demander ce que coûtera une session *avant*
de la payer — la différence entre un budget seulement imposé et un budget sur
lequel on peut planifier.

`/v1/images/generations` est la seule route sans défaut raisonnable. Toutes les
autres retombent sur l'upstream par défaut quand elles ne reconnaissent pas un
modèle, et c'est ce qui permet à un client codé en dur sur le nom d'un modèle
tiers de fonctionner tel quel. Un moteur de langage ne sait pas répondre à une
demande d'image : retomber produirait un 502 qui parle d'une socket au lieu
d'une phrase sur le déploiement. Elle refuse donc par un 501 qui nomme la ligne
à écrire, et `ai-bunker doctor` dit si la route existe avant que quelqu'un ne
le découvre dans une erreur. vLLM ne sert pas de modèles de diffusion ;
`best-engine-ai-helper serve` si, et `ai-bunker sizing --image auto` dit quel
modèle y mettre et ce qu'il coûte au modèle de code.

### Ce qu'elle dit d'elle-même

```bash
$ ai-bunker doctor
  [ok  ] charter carries operating rules
  [ok  ] 27 rules loaded
  [ok  ] 247 rule assertions pass
  [ok  ] 100% of rules carry evidence
  [WARN] upstream local answers at http://127.0.0.1:8001/v1   not reachable
  [WARN] an API key is configured   no key: this gateway is open to anyone who
                                    can reach it…
  [ok  ] no route leaves this network
  12/14 checks pass
```

`/health` publie les mêmes faits à l'exécution : si le déploiement est
**souverain** (aucune route configurée ne quitte le réseau), s'il est
**authentifié** (une passerelle ouverte par accident ressemble exactement à une
passerelle ouverte exprès), et lesquelles des trois étapes d'application sont
réellement actives.

### Limites assumées

- ~~Le filtrage des commandes ne s'applique pas au streaming.~~ **Fermé en
  0.2.0.** C'était vrai, et c'était le plus gros trou dans ce que cette
  passerelle promet : `stream: true` est ce que tout client d'agent demande
  par défaut, donc la seule garantie vendue était absente exactement là où
  elle comptait. L'argument pour la laisser — refuser un appel fragmenté
  obligerait à tamponner toute la réponse — ne tient pas, car **aucun client
  ne peut agir sur un demi-appel d'outil**. Les deltas de contenu passent
  intacts ; seuls les fragments d'appel sont retenus, assemblés, jugés par le
  même `apply_outbound` que la voie atomique, puis relâchés : **le filtrage
  des commandes s'applique au streaming exactement comme à l'atomique.**
  `/health` dit toujours quelles garanties sont actives.
- **Le journal d'audit grossit sans borne.** `audit_log` est ajouté, jamais
  rotaté : une passerelle qui tourne des mois écrit un objet JavaScript Object
  Notation (JSON) par décision
  jusqu'à ce que le disque dise non. La rotation revient à ce qui rotate déjà
  les journaux sur cette machine, et `/v1/decisions` ne lit que la queue, en se
  plaçant depuis la fin plutôt qu'en chargeant le fichier : il faisait
  l'inverse, ce qui coûtait 1,01 seconde et 470 Mio de pointe mémoire sur un
  journal de 200 Mio pour renvoyer cinquante lignes. Rien ici ne vous dira
  que le fichier est gros. L'état en mémoire, lui, **est**
  borné : le disjoncteur garde 4 096 sessions et les épingles d'outils 512, les
  plus anciennes évincées d'abord.
- ~~Le comptage bloque la boucle d'événements.~~ **Fermé.** La sonde du
  tokenizer et les comptages sont des appels synchrones, et ils tournaient dans
  des gestionnaires asynchrones : mesuré contre une socket qui accepte et ne
  répond jamais, `/health` mettait **9,73 secondes** pendant qu'une requête
  était préparée — deux dialectes à la durée de sonde — donc pendant dix
  secondes la passerelle ne servait personne. Le pipeline entrant tourne
  maintenant dans un thread de travail et `/health` répond en 0,01 seconde sous
  le même blocage. **Le comptage reste sérialisé**, par un verrou et à dessein :
  `counters`, `pins`, `approved_tools` et le disjoncteur n'ont jamais eu besoin
  de verrou parce que rien n'était jamais concurrent, et un correctif de
  disponibilité payé par une course de données n'est pas un correctif. Ce qui
  change, c'est que la boucle est libre pendant que la passerelle **attend** :
  `/health`, `/v1/models`, le tableau de bord et chaque flux en cours
  continuent de répondre. **Pas pendant qu'elle calcule** : `re` garde le
  verrou global de l'interpréteur, donc un filtrage en thread gèle la boucle
  par tranches plutôt que pas du tout — mesuré à 35,8 ms de gel pour 170 ms de
  recherche de motifs, contre 3,4 ms pour une seconde entière d'attente sur
  une socket. Ce qui borne cela, c'est le plafond de requête ci-dessous, et
  c'est pourquoi il devait atteindre chaque surface qui porte un corps.
- **Une requête au-delà de trente-deux caractères par token de contexte servi
  est refusée sans être lue.** Le filtrage coûte du temps linéairement dans la
  longueur de ce qui arrive, et rien d'autre ne bornait le total :
  `MAX_SCREEN_CHARS` borne une *tranche*, et une sortie d'outil arrive en
  autant de tranches que sa longueur l'exige. Le budget ne l'attrape pas non
  plus, à dessein — `measure_request` compte le plancher, et la conversation
  n'est pas le plancher — donc une seule sortie d'outil de 40 Mo passait le
  budget, coûtait des minutes de filtrage synchrone pendant lesquelles la
  passerelle ne servait personne, puis partait vers un moteur qui l'aurait
  refusée pour longueur de contexte de toute façon. Le plafond est environ
  treize fois la plus grande requête qui pourrait tenir, parce que refuser une
  requête qui aurait tenu est le pire des deux échecs ; le 413 nomme les deux
  nombres, pour qu'un client découpe sa requête au lieu de deviner.
- **Les données personnelles ne sont pas filtrées, et rien ici ne prétend le
  contraire.** Les 27 règles couvrent les identifiants, l'injection de prompt,
  les commandes shell dangereuses et les descriptions d'outils. Elles ne
  cherchent ni noms, ni adresses, ni identifiants nationaux, ni numéros de
  carte, ni détail médical — et `global.generic_secret` attrapant au passage
  une chaîne à forte entropie n'est pas une couverture. Un déploiement avec une
  obligation sur les données personnelles a besoin d'un inspecteur de contenu :
  NeMo Guardrails, Guardrails AI, LLM Guard le font correctement et aucun n'est
  une passerelle ; [`PAYSAGE.md`](PAYSAGE.md) dit où chacun se situe. Énoncé
  ici parce que ce projet parle de journaux de décision et de traçabilité, et
  qu'un lecteur peut légitimement entendre « gouvernance » et supposer plus
  que ce qui est offert.
- **Le vocabulaire d'outils shell est un défaut, pas une prétention à
  l'exhaustivité.** `SHELL_TOOLS` est surchargeable.
- **Écoute sur localhost par défaut.** Un outil de souveraineté qui écoute sur
  toutes les interfaces dès son démarrage a pris la décision qui revenait à son
  utilisateur.

### Audit

Chaque règle qui se déclenche ajoute une ligne, avec l'empreinte de charte et
jamais le texte apparié :

```json
{"rule":"global.generic_secret","severity":"BLOCKER","scope":"output",
 "outcome":"redacted","count":1,"charter":"aa9fcf72c7ff3e40","at":"2026/10/19-08:38:17"}
{"rule":"shell.destructive_rm","severity":"BLOCKER","scope":"command",
 "outcome":"refused","count":1,"charter":"aa9fcf72c7ff3e40","at":"2026/10/19-08:38:17"}
```

Un échec d'écriture avertit sans faire échouer la requête : perdre une ligne
est fâcheux, refuser de servir parce qu'un disque est plein l'est davantage, et
l'avertissement est ce qui fait réparer.

## Router par besoin, pas par nom de modèle

Un client code en dur un nom de modèle parce qu'il faut bien mettre *quelque
chose* dans le champ. Ce qu'il sait vraiment, c'est **ce qu'est le travail** —
et c'est là-dessus qu'il vaut la peine de router, parce que ça survit au
remplacement du modèle.

```yaml
needs:
  code: local
  prose: local
  structured:
    upstream: local
    model: devstral
  reasoning:              # les 20 %
    upstream: premium
    model: claude-sonnet-5
```

Un client déclare un besoin avec `X-AI-Bunker-Need`, ou en demandant le besoin
comme nom de modèle — les besoins sont listés dans `/v1/models` précisément
pour ça, puisque la plupart des clients ont un menu de modèles et pas de champ
d'en-tête. Les besoins sont résolus **avant** les noms de modèles : un besoin
est une affirmation sur le travail, un nom de modèle est un détail
d'implémentation que le client n'aurait pas dû avoir à apprendre.

C'est le partage 80/20 de la stratégie rendu configurationnel. Le travail
courant sur le modèle local, le raisonnement lourd sur une route premium, et
**changer l'un ou l'autre est un changement de configuration plutôt qu'une
édition dans chaque client**.

Deux détails qui existent à cause de la façon dont ça rate en pratique. Un
besoin non configuré retombe sur le défaut **et avertit**, parce que l'ignorer
en silence est la façon dont un exploitant découvre son routage sur une
facture. Et chaque route hors réseau est journalisée avec la règle qui l'y a
envoyée — `"model" -> premium by need 'reasoning'` — parce qu'une requête
partie au mauvais endroit n'est bon marché à corriger que si le journal dit
quelle règle l'a envoyée.

> **Où vit la *sélection* de modèle.** Choisir quel modèle correspond le mieux
> à un besoin et à un budget est le travail de
> [`best-engine-ai-helper`](https://github.com/warith-harchaoui/best-engine-ai-helper),
> pas celui-ci : il classe déjà les modèles locaux par ajustement matériel et
> les modèles payants sur une courbe qualité/prix, choisit parmi les
> fournisseurs dont la clé d'interface de programmation applicative (API) est
> effectivement présente, et retombe du
> payant vers le local. Cette question se pose *avant* qu'il y ait un serveur —
> dans un script, sur un portable, en CI — donc elle appartient à une
> bibliothèque. ai-bunker route ; il ne choisit pas.

## Tableau de bord

`GET /gui` sert un tableau de bord d'exploitation d'une seule page : le
plancher de session détaillé par propriétaire, la charte et ce qu'elle coûte,
les blocs que le modèle voit réellement, et le journal de décisions.

Une tuile est tout le projet en une image — une barre empilée du plancher,
**par propriétaire**, pour voir d'un coup d'œil qui mange la fenêtre. Orange
c'est le client, bleu c'est ai-bunker, vert c'est ce qu'il reste pour
travailler. Dans un déploiement sain, les trois segments clients doivent
écraser les nôtres, et quand ce n'est pas le cas, la tuile dit lequel attaquer.

**Aucune étape de compilation, aucune requête externe.** Le style maison pour
ce genre de page est Tailwind, ce qui sans compilation veut dire le CDN Play,
un réseau de diffusion de contenu —
et une passerelle dont la promesse est que rien ne quitte le réseau ne peut pas
servir à son exploitant une page qui va chercher une feuille de style chez un
tiers au chargement. La première chose que ferait le tableau de bord serait de
contredire ce qu'il affiche. Les *Cascading Style Sheets* (CSS) sont donc
écrites à la main avec la même discipline de tokens, et les polices sont celles
du système.

Deux portes déterministes tournent dessus, et elles sont dans la suite de
tests :

```bash
python scripts/audit_contrast.py   # WCAG, chaque paire de tokens, les 2 schémas
python scripts/lint_a11y.py        # 14 règles statiques, sans navigateur
```

L'auditeur de contraste a justifié sa place immédiatement : il a trouvé
**quatre vrais défauts** au premier passage, aucun visible à l'œil. Les teintes
saturées de la palette curatée sont superbes sur fond sombre et échouent sur du
blanc — `#28CD41` score 2,12:1 contre une carte, là où le plancher est 3:1. Le
schéma clair utilise désormais des variantes assombries des mêmes teintes ; le
schéma sombre, où les originales scorent 8:1, les garde.

Les deux portes sont testées pour leur capacité à **échouer**, contre une page
délibérément fautive. Un linter incapable d'échouer produit une coche verte et
l'illusion que quelque chose a été vérifié.

**Vérifié visuellement.** Trois tours de rendu-regard-correction avec Chrome
headless, dans les deux schémas. Le compte rendu est dans
`.private/ralph-loop/`. Six problèmes trouvés, dont **deux vrais bugs que
327 tests d'alors n'attrapaient pas** : deux statistiques jamais remplies, et un budget
annonçant `ratio (estimate)` alors que le moteur pouvait donner un compte
exact — le tableau de bord du module budget reproduisant exactement la
défaillance que ce module existe pour empêcher.

Le troisième n'était pas un bug et comptait le plus : l'élément le plus grand
de la page ne disait rien. Un plancher de 607 contre 193 108 de libre se rendait
en un filet de 2 pixels, donc la barre montrait « il y a de la place » et
cachait **qui la mange**. Une barre ne peut pas porter un rapport de 300:1 et
une composition en même temps : il y en a donc deux, chacune honnête à son
échelle. **Une page peut passer toutes les portes statiques et ne rien dire, et
aucun test unitaire ne trouve ça.**

## Kits clients

**Minces à dessein**, et l'asymétrie est la conception. Tout ce que la
passerelle peut voir, elle l'impose — à tous les clients, sans possibilité de
s'y soustraire en changeant de harnais. Ce qu'un kit client porte, c'est
exactement l'ensemble des choses qui se passent *avant qu'une requête
n'existe*, et qu'aucun point d'entrée ne peut atteindre.

| | Imposé par | Pourquoi là et pas ailleurs |
|---|---|---|
| Secrets dans une sortie d'outil | **passerelle** | Elle voit le message `role: "tool"` |
| Injection de prompt | **passerelle** | Même message, même point de passage |
| Commandes shell dangereuses | **passerelle** | Elle voit le `tool_call` avant exécution |
| Plancher / budget de session | **passerelle** | Seul le serveur tient le tokenizer |
| La charte | **passerelle** | Injectée dans chaque requête, quel que soit l'émetteur |
| **Lectures bornées** | **client** | La passerelle ne voit jamais une lecture. Quand le résultat arrive, les tokens sont déjà dépensés |
| **Injection de skills / schémas** | **client** | La passerelle peut *détecter* un plancher gonflé et refuser ; elle ne peut pas empêcher un client de construire ce prompt |
| **Seuils de compaction** | **client** | La compaction se fait entièrement côté client, entre deux tours |

Un kit client n'est pas digne de confiance — c'est un fichier de configuration
sur le portable de quelqu'un — donc rien de porteur n'y vit. Mais ces trois
lignes **client** sont structurellement hors d'atteinte, et les ignorer coûte
du matériel : un agent qui lit des fichiers entiers et ne compacte jamais divise
par deux le nombre de sessions qu'un GPU porte, pour une production identique.

Le kit OpenCode est donc une configuration plus **un seul** plugin,
`bounded-reads.js`. S'il grossit un jour, c'est que quelque chose a été mis au
mauvais endroit.

### Les frameworks d'agents, où la boucle est la vôtre

Le tableau ci-dessus décrit un **agent de code** : la boucle de quelqu'un
d'autre, dans laquelle un kit doit aller mettre les mains puisque c'est le
harnais qui décide ces trois lignes. Dans un framework d'agents, c'est vous qui
écrivez la boucle, donc elles vous appartiennent déjà — et un kit qui les
fixerait devinerait au sujet d'une application qu'il ne voit pas. Le kit est
alors un module que vous importez, et il ne porte que les deux choses qu'un
framework ne peut pas deviner : quel point d'entrée appeler, et quelle fenêtre
de contexte croire.

```bash
ai-bunker adopt . --client langgraph     # ChatOpenAI, donc tout LangChain
ai-bunker adopt . --client llamaindex    # OpenAILike
ai-bunker adopt . --client smolagents    # OpenAIModel
```

```python
from ai_bunker_langgraph import make_model
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(make_model(), tools=[])
```

Sur demande plutôt que par défaut : écrire du Python dans un dépôt, c'est
rédiger du code applicatif, ce qui n'est pas le même acte que configurer un
outil.

Plus mince ne veut pas dire plus faible, et cela a été **vérifié** et pas
affirmé. Un résultat d'outil portant `AWS_ACCESS_KEY_ID=AKIA…` envoyé à travers
le kit LangGraph est revenu **caviardé**, journalisé en
`global.aws_access_key`, avant que le modèle ne le lise. La charte arrive aussi
sur cette route — un plancher exact de 595 tokens, compté par le tokenizer du
moteur lui-même.

Un avertissement que le kit smolagents porte dans sa propre docstring, parce
que c'est le seul risque qu'une passerelle ne couvre pas : un `CodeAgent`
exécute le Python du modèle **localement** par défaut. La passerelle refuse les
commandes *shell* dangereuses parce qu'elle les voit comme des appels d'outil
avant qu'elles ne tournent ; elle ne voit pas du tout un `exec` à l'intérieur
du harnais. Utilisez `executor_type="docker"` pour autre chose qu'un jouet.

### Les clients sans kit : publier la charte en Agent Skill

Un kit s'écrit par client, donc un client dont ce projet n'a jamais entendu
parler n'obtient rien. [Agent Skills](https://agentskills.io) est un format
ouvert fait exactement pour ce problème, lu nativement par Claude Code,
OpenCode, Cursor, Goose, Amp, Roo, Codex, Copilot et Gemini CLI — CLI pour
*command-line interface*, l'interface en ligne de commande.

```bash
ai-bunker skill                      # écrit .claude/skills/team-charter/
ai-bunker skill --client opencode    # ou .opencode/skills/
ai-bunker skill --check .claude/skills/team-charter
```

Le défaut est `.claude/skills/` parce qu'OpenCode documente ce chemin comme
compatible Claude : une seule copie sert les deux, sans écrire les fichiers
deux fois.

L'export tient presque du renommage, car les deux conceptions se rejoignent.
La divulgation progressive du format charge le `name` et la `description` au
démarrage, le corps du `SKILL.md` à l'activation, et les fichiers joints
seulement quand une tâche en a besoin. Ce sont, dans l'ordre, l'index, les
règles d'opération et les pages de ce projet — trouvés séparément, pour la
même raison.

```
.claude/skills/team-charter/
├── SKILL.md                     # règles d'opération + index (~700 tokens)
└── references/
    ├── default-00_principles.md # une page, chargée seulement si ouverte
    └── python-10_style.md
```

Deux choses que ce n'est **pas**, délibérément. Ce n'est pas une seconde
source de vérité : la passerelle reste la copie qui fait foi, et l'empreinte
de la charte voyage dans les `metadata` de la skill, de sorte que n'importe
qui peut voir si une copie sur disque a dérivé de celle qui est appliquée. Et
ce n'est pas un remplacement de kit : une skill porte des standards, pas les
lectures bornées ni les seuils de compaction — les trois lignes du tableau
ci-dessus que seul un client peut tenir.

### L'autre sens : un arbre de skills écrit par quelqu'un d'autre

L'export a prouvé que les deux formats s'accordent, donc l'import est presque
gratuit — et c'est le sens le plus utile, parce que les standards qu'une
équipe veut le plus faire servir sont en général ceux qu'elle n'a pas écrits.

```bash
ai-bunker skill --import ~/skore-skills/skills --pack ml \
                --source probabl-ai/skore-skills
```

Mesuré contre [`probabl-ai/skore-skills`](https://github.com/probabl-ai/skore-skills),
un jeu de skills pour piloter des expériences d'apprentissage automatique avec
scikit-learn, skrub et skore :

| | |
|---|---|
| skills lus | 5 |
| leurs corps `SKILL.md` | 103 788 caractères |
| pages de charte écrites | 77 |
| plus grosse page | 8 183 caractères (budget : 12 000) |
| pages hors budget | **0** |
| ce que l'invite porte ensuite | **~597 tokens**, règles d'opération et index réunis |

C'est tout l'intérêt énoncé comme une mesure : cent kilo-octets de standards
deviennent quelque chose dont un agent est *informé* pour six cents tokens, et
dont il lit une page quand une tâche l'exige.

**Un corps au-delà du budget de page est découpé à ses titres `##`, et le texte
est réparti, pas réécrit.** Le recollage est identique octet pour octet —
affirmé, pas supposé, sur chaque skill réel testé. C'est la ligne que ce projet
trace ailleurs sur le fait de toucher du contenu qu'il n'a pas écrit : une
passerelle peut décider où une page s'arrête, elle ne peut pas décider ce
qu'elle dit.

**La provenance voyage, et l'empreinte de la source est préférée.**
`skore-skills` livre un `.catalog.json` avec un `catalog_hash` sur l'ensemble
et une empreinte par skill ; ce sont celles-là qui sont enregistrées plutôt
qu'un digest calculé ici, parce qu'un digest inventé par ce projet ne
prouverait que la cohérence interne de l'import, pas la correspondance avec
l'amont.

**Deux trouvailles à dire, parce que c'est l'import qui les a fait sortir.**
D'abord, les cinq skills portent une `description` plus longue que la limite
de 1 024 caractères du format Agent Skills — entre 1 783 et 2 431 — parce
qu'ils s'en servent pour la prose de déclenchement et de périmètre. L'import le
**signale** et continue : ce sont les skills de quelqu'un d'autre et le rôle
d'ai-bunker est de les servir, pas de les police, mais un import muet cacherait
un vrai problème d'interopérabilité derrière un message de succès. Ensuite,
importer un paquet de 77 pages a révélé un bug dans l'index de ce projet : le
plafond dégradait la liste **entière**, donc un gros paquet transformait
`python: 10_style.md, tests.md` en `python (2 pages)` — en dépensant la
connaissance qu'un agent avait de deux noms de page pour économiser les
quarante-cinq caractères qui les nommaient. Le plafond dégrade désormais **par
paquet, le plus gros d'abord**.

**`modelTier` est enregistré et délibérément pas suivi.** Ces skills déclarent
`metadata.modelTier: small | medium | big`, ce qui recoupe exactement le
[routage par besoin](#routage-par-besoin-pas-par-nom-de-modèle) plutôt que par
nom de modèle, et câbler les deux est tentant. Ce n'est pas câblé. Un dossier
tiers qui peut relever le palier est un dossier tiers qui décide ce que
l'équipe paie en inférence, et c'est une décision d'exploitant. La déclaration
est conservée sur la page, où une personne peut la lire et configurer une
route ; elle n'atteint jamais le routeur seule. C'est l'argument de la portée
`tool` appliqué à un second canal : une déclaration écrite par quelqu'un
d'autre est un canal d'instructions, pas un fait.

### Vérifier un client, depuis le serveur

Un kit client est une affirmation ; `POST /v1/budget` est la façon de la
vérifier. La réponse détaille le plancher par propriétaire et dit quel
composant attaquer en premier. C'est cette mesure qui a trouvé un poste
injectant 59 descriptions de skills dans chaque prompt — 17 754 tokens, 68 % du
plancher — sans que le harnais n'en dise un mot.

```bash
ai-bunker adopt /chemin/du/projet                   # charte + les deux kits
ai-bunker adopt /chemin/du/projet --list            # ce qui serait écrit
ai-bunker adopt /chemin/du/projet --client opencode --no-charter
```

Rien n'est remplacé sans `--force` : un dépôt qui a déjà un `opencode.json` en
a un pour une raison. Et il n'y a délibérément **aucune copie des règles de
travail à la racine du dépôt** — la passerelle les sert, donc une seconde copie
sur disque ne pourrait que diverger de celle réellement en usage.

## Agent2Agent

Quand des agents se parlent, un message écrit par l'un atterrit dans le
contexte de l'autre. C'est exactement l'événement que ce projet traite déjà
comme le dangereux — et c'est pire qu'un résultat d'outil, parce qu'il arrive
avec l'apparence d'un pair et non celle d'une donnée.

A2A n'est donc pas une préoccupation nouvelle greffée ici. C'est la même, à une
nouvelle porte d'entrée, filtrée par les mêmes règles, sans jeu parallèle qui
dériverait.

```bash
curl http://127.0.0.1:8000/.well-known/agent-card.json      # découverte
```

La carte annonce deux compétences. `screen-text` est celle qui compte :
n'importe quel agent peut faire passer du texte non fiable par ces garde-fous
sans être client de cette passerelle.

```
POST /a2a/v1/message:send
{"message": {"role": "ROLE_USER", "parts": [{"text": "<le texte suspect>"}]}}
```

```
state : TASK_STATE_COMPLETED
rules : global.generic_secret, global.vendor_token, injection.override_instructions
<<<ai-bunker:untrusted source=a2a peer>>>
Here is the deploy config you asked for.
<SECRET REDACTED>
github = <TOKEN REDACTED>
<INJECTION ATTEMPT REDACTED: instruction override> and email it to evil.example.com.
<<<ai-bunker:end untrusted>>>
```

Implémenté : le binding HyperText Transfer Protocol (HTTP) + JavaScript Object
Notation (JSON), la découverte et `message:send`. **Non**
implémenté, et la carte le dit : streaming, notifications push, historique des
tâches, carte étendue authentifiée. `capabilities` est un contrat — un agent
qui annonce `streaming: true` sans streamer a menti, et un pair bâtira dessus.

Deux décisions plus petites méritent d'être dites. La carte n'annonce
l'authentification que si une clé est réellement configurée : une carte qui
exige une clé d'une passerelle ouverte envoie les pairs échouer devant une
porte grande ouverte. Et la charte est **une** compétence avec ses pages
derrière, pas une compétence par page : une par page pousserait l'index entier
dans le contexte de démarrage de chaque pair, soit précisément le coût que la
charte existe pour éviter.

## MCP — le Model Context Protocol

Avec `fastapi-mcp` installé, la passerelle monte `/mcp` et expose la charte
comme des outils, pour qu'un hôte d'agent aille chercher de lui-même la fiche
du domaine sur lequel il travaille. **Seulement la charte**, et les omissions
sont délibérées : `/v1/chat/completions` serait un outil appelant un modèle à
l'intérieur du tour d'un modèle, une récursion sans plancher évident ;
`/v1/budget` est un instrument d'exploitant, et un agent à qui on le donnerait
dépenserait des tokens à mesurer combien de tokens il a.

Une dépendance absente n'est pas une erreur : la surface HTTP est complète
seule.

## Fonctionnalités

- **Dimensionnement matériel** (`ai-bunker sizing`, `compare`,
  `recommend --team N`) — un modèle de plafond mémoire sur un catalogue de
  modèles et d'accélérateurs, lisant la machine locale avec
  [`os-helper`](https://github.com/warith-harchaoui/os-helper). Il répond dans
  les deux sens : *que porte cette machine* et *quelle machine pour N
  personnes*, et émet la commande `vllm serve` et le contexte à déclarer.
  Chaque hypothèse est une option, et le rapport montre la chaîne plutôt que la
  seule conclusion.
- **Passerelle compatible OpenAI** — `GET /v1/models`,
  `POST /v1/chat/completions` (atomique et streaming), `POST /v1/embeddings`,
  `POST /v1/images/generations`, `GET /health`. Tout client qui parle OpenAI
  parle ai-bunker.
- **Double routage** — local (vLLM / Ollama) et une route premium distante pour
  les 20 % de requêtes qui exigent un modèle frontière, choisie modèle par
  modèle dans un registre versionné.
- **La charte comme index** (`ai-bunker charter`) — les standards restent du
  Markdown et sont annoncés par un index d'environ 600 tokens au lieu d'être
  collés dans chaque prompt. Une fiche ne coûte rien tant qu'elle n'est pas
  ouverte : la charte peut donc être vaste. Voir [La charte](#la-charte).
- **Règles appliquées** (`ai-bunker rules`) — un seul format, deux portées,
  trois sévérités, et chaque règle est livrée avec ses preuves. Les secrets
  sont censurés à l'entrée, les commandes dangereuses refusées, et
  **l'injection indirecte de prompt est attrapée au seul point de passage où
  elle arrive**. Voir [Les règles](#les-règles).
- **Budget côté serveur** (`ai-bunker budget`) — mesure le vrai plancher avec
  le tokenizer du moteur qui sert, **attribue chaque token au composant qui l'a
  causé**, et sort en code non nul sur une configuration qui ne laisse pas de
  place pour travailler. Trois backends par ordre de confiance décroissant
  (`server`, `local`, `ratio`), et le rapport dit toujours lequel a produit le
  chiffre.
- **MCP** — la passerelle s'expose via le Model Context Protocol, pour qu'un
  hôte d'agent découvre la charte et les règles comme des outils.
- **Kits clients** (`ai-bunker adopt`) — configurations OpenCode et Claude Code
  pointant un harnais existant vers la passerelle, plus le seul plugin que la
  passerelle ne peut structurellement pas remplacer. Voir
  [Kits clients](#kits-clients).

## État

C'est un `0.2.0-alpha` honnête, et le tableau dit exactement où en est le
projet. Rien de ce qui précède n'est une affirmation sur du code livré, sauf si
ce tableau le dit.

| Composant | État |
|---|---|
| Décisions, conception de la charte | ✅ ce document |
| `.gitignore`, `pyproject.toml`, squelette de projet | ✅ |
| `ai_bunker/sizing.py` + `report.py` — modèle, catalogue, CLI | ✅ |
| `docs/SIZING.md` — la décision d'achat, chiffrée | ✅ |
| `ai_bunker/budget.py` — comptabilité de tokens, détaillée et bloquante | ✅ |
| 1287 tests, `ruff` propre | ✅ |
| `scripts/lint_acronyms.py` — chaque sigle explicité avant usage | ✅ |
| `ai_bunker/budget.py` — comptabilité de tokens côté serveur | ✅ |
| `ai_bunker/charter.py` — index, fiches à la demande, empreinte | ✅ |
| `ai_bunker/rules.py` — deux portées, entropie, exceptions, règles auto-testées | ✅ |
| `charter/` — 16 règles livrées avec 95 exemples, tous verts | ✅ |
| `ai_bunker/gateway.py` + `pipeline.py` + `config.py` — la surface OpenAI | ✅ |
| `ai-bunker doctor` — le déploiement fait-il ce qu'il prétend | ✅ |
| `clients/opencode`, `clients/claude-code` + `ai-bunker adopt` | ✅ |
| Surface MCP (`fastapi-mcp`), charte seulement | ✅ |
| `GET /gui` — tableau de bord, sans compilation ni requête externe | ✅ |
| `scripts/audit_contrast.py`, `scripts/lint_a11y.py` — portes déterministes | ✅ |
| Routage par besoin (`X-AI-Bunker-Need`) | ✅ |
| Revue visuelle (3 tours, Chrome headless, les 2 schémas) | ✅ |
| `CHANGELOG.md`, `CONTRIBUTING.md`, CI GitHub Actions | ✅ |
| `LANDSCAPE.md` / `PAYSAGE.md` — champ concurrentiel, relevé | ✅ |
| `docs/EXAMPLES.md` | 🚧 suivant |

La conception, elle, n'est pas en alpha. Chaque chiffre de ce document vient
d'un GPU qui a servi 6 565 messages en production sous exactement ces
contraintes. Le code est neuf ; les preuves qui le fondent ne le sont pas.

## Documentation

[📋 Exemples](EXEMPLES.md) — chaque commande, avec sa vraie sortie. Rien n'y est
illustratif : chaque bloc a été produit en lançant la ligne au-dessus.

[📐 Dimensionnement](docs/SIZING.md) — quelle machine acheter, chiffré.

[🛡️ Règles](docs/REGLES.md) — le moteur en entier : les deux portées, les trois
sévérités, et chaque contournement trouvé en sondant, avec le raisonnement
derrière le motif qui l'a attrapé.

## Où cela se situe

[🗺️ Paysage](PAYSAGE.md) — les passerelles, les moteurs de règles et les moteurs
de politiques, comparés, avec une carte de positionnement et une section franche
sur **là où ce projet est en retard**. En bref : les passerelles routent, les
garde-fous inspectent, aucun ne compte, et le coin où les trois se rejoignent est
vide.

## Construit sur la suite

ai-bunker implémente délibérément le moins de choses possible :

- [`os-helper`](https://github.com/warith-harchaoui/os-helper) — détection
  matérielle, chargement de configuration, journalisation, hachage, chronométrage,
  sous-processus sans shell. Il tient lieu de trois modules que ce projet aurait
  sinon écrits à la main, puis dû maintenir.
- [`best-engine-ai-helper`](https://github.com/warith-harchaoui/best-engine-ai-helper)
  — **quel modèle servir, pour les quatre emplacements.** ai-bunker décrit en
  mots ce à quoi il sert (`engine.TASK` : une passerelle souveraine pour des
  agents de code autonomes qui appellent des outils et renvoient du JSON
  contraint par schéma sur un contexte long), lui passe son propre catalogue de
  service, et prend la réponse. Il ne nomme aucun modèle nulle part :
  `--model auto` est le défaut de chaque commande de dimensionnement, et
  `tests/test_engine.py` échoue si un littéral réapparaît — y compris un
  préfixe de famille, ce par quoi `devstral` a survécu dans `adopt.py` pendant
  plusieurs versions. Le choix suit la machine : la carte de 72 Gio se voit
  confier le 80B et celle de 48 Gio le 24B — ce que
  [docs/SIZING.md](docs/SIZING.md) démontrait à la main, maintenant dérivé.

  Les emplacements **code** et **vision** sont classés sur le catalogue de
  service de ce projet, chacun sur l'axe de benchmark qui le concerne
  réellement. L'**embedder** est répondu directement : il y en a un, et classer
  un ensemble d'un seul élément serait du théâtre. L'emplacement
  **texte-vers-image** est délégué entièrement, catalogue compris — un modèle
  de diffusion est trois ou quatre réseaux qui se relaient, donc son empreinte
  dépend de s'ils sont tenus tous à la fois ou passés un par un dans
  l'accélérateur, et son coût se compte en pas de débruitage plutôt qu'en
  tokens. Aucune des colonnes pour lesquelles `catalog/serving.yaml` existe ne
  décrit cela, et le helper porte déjà les entrées comme l'arithmétique.

  Ce que ce projet ajoute à la réponse du helper tient en une règle : un modèle
  co-résident prend le candidat le plus léger à dix points de benchmark du
  meilleur, plutôt que le meilleur. Mesuré sur une carte de 80 Gio, le modèle
  de vision glouton coûte le modèle de code 80B, et le modèle d'image glouton
  le coûte aussi — `ai-bunker sizing --image auto` imprime cet arbitrage au
  lieu de le faire en silence.
  Ce qui reste ici, c'est l'arithmétique : le helper choisit **quel** modèle,
  et `sizing.py` calcule le plafond de bande passante, la géométrie du cache
  clé-valeur et le nombre de personnes. Sur un poste de travail, il peut aussi
  être ce qui sert : il expose un `/v1` compatible OpenAI, donc
  `upstreams.local` peut pointer sur lui plutôt que sur vLLM — voir
  `config/gateway.example.yaml`, qui explique aussi pourquoi y épingler un
  modèle concret plutôt que son alias `best`.
- [`ann-router`](https://github.com/warith-harchaoui/ann-router) — prévu, pour le
  jour où la charte dépassera la recherche par chemin et demandera un vrai index
  de récupération.

Même philosophie dans toute la suite : **mesurer les critères → sélectionner le
moteur → rendre une justification discutable.**

## Installation

**Prérequis** : **Python 3.10–3.13** et **git**. Un GPU n'est nécessaire que sur
la machine qui **sert** ; les clients n'en ont pas besoin.

- 🍎 **macOS** ([Homebrew](https://brew.sh)) : `brew install python git`
- 🐧 **Ubuntu/Debian** : `sudo apt update && sudo apt install -y python3 python3-venv python3-pip git`
- 🪟 **Windows** (PowerShell) : `winget install Python.Python.3.12 Git.Git`

```bash
git clone https://github.com/warith-harchaoui/ai-bunker.git
cd ai-bunker
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Sur la machine qui sert, ajouter le runtime serveur :

```bash
pip install -e ".[serve]"     # vLLM
```

## Utilisation

Livré aujourd'hui — la surface de dimensionnement :

```bash
# Quelle machine pour une équipe de N ?
ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b
ai-bunker recommend --team 2

# Que porte une machine, et pourquoi ?
ai-bunker sizing --accelerator rtx-pro-6000-blackwell
ai-bunker sizing --vram 96 --bandwidth 1792        # une machine hors catalogue

# Avec un modèle texte-vers-image co-résident. Éteint par défaut, et le rapport
# dit ce qu'il coûte : ses poids sont des poids que le modèle de code n'a pas.
ai-bunker sizing --accelerator h100-80 --image auto

# Toutes les machines, une ligne chacune, avec le coût par personne portée
ai-bunker compare

# Les faits derrière tout cela, avec leur provenance
ai-bunker catalog

# Ce qu'os-helper voit de cette machine
ai-bunker detect
```

Chaque hypothèse est une option, et celles qui bougent le plus la réponse sont
nommées :

```bash
--comfort-tps 30        # un plancher par flux plus strict : machine plus grosse
--live-context 65536    # un harnais indiscipliné : divise par deux chaque machine
--duty-cycle 0.4        # usage agentique plus lourd
--simultaneity 1.0      # dimensionner sur la pire heure, pas sur la moyenne
```

Ce que coûte une session avant d'avoir travaillé :

```bash
# Détailler le plancher d'une requête capturée, compté par le moteur qui sert
ai-bunker budget requete.json \
  --served-context 131072 --declared-context 104000 --reserve 16000 \
  --base-url http://bunker.internal:8000/v1 \
  --model-name mistralai/Devstral-Small-2-24B-Instruct-2512 \
  --charter charter/AGENTS.md --index charter/index.md

# En CI : refuser le déploiement plutôt que le signaler
ai-bunker budget requete.json --served-context 32768 --exact --gate
```

La charte et les règles :

```bash
ai-bunker charter                        # ce qu'elle contient et ce qu'elle coûte
ai-bunker charter --index                # l'index exactement tel qu'injecté
ai-bunker charter --page python/tests.md # une fiche, à la demande

ai-bunker rules --check                  # chaque règle contre ses preuves (porte CI)
ai-bunker rules --command "git push --force origin main"
cat README.md | ai-bunker rules --provenance "https://untrusted.example"
```

La passerelle :

```bash
cp config/gateway.example.yaml config/gateway.yaml   # puis éditer
export AI_BUNKER_API_KEY=...

ai-bunker doctor                    # tout ce que le déploiement prétend est-il vrai ?
ai-bunker serve                     # localhost:8000
ai-bunker serve --host 0.0.0.0      # avertit, parce que c'est une décision
```

Équiper un dépôt :

```bash
ai-bunker adopt /chemin/du/projet --list   # ce qui serait écrit
ai-bunker adopt /chemin/du/projet          # charte + kits clients
```

Pointer n'importe quel client compatible OpenAI vers la passerelle :

```bash
export OPENAI_BASE_URL="http://bunker.internal:8000/v1"
export OPENAI_API_KEY="<votre clé de passerelle>"
```

## Auteur

- [Warith Harchaoui](https://linkedin.com/in/warith-harchaoui)

## Licence

BSD-3-Clause — la licence à trois clauses de la *Berkeley Software
Distribution*. Voir
[LICENSE](https://github.com/warith-harchaoui/ai-bunker/blob/main/LICENSE).
