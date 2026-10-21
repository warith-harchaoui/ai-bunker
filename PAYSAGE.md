# Paysage

🇫🇷 Français · [🇬🇧 LANDSCAPE.md](LANDSCAPE.md)

Les outils qui se placent entre un agent de code et un modèle, comparés à `ai-bunker`.
Notes de ⭐ (1) à ⭐⭐⭐⭐⭐ (5), évaluées sur le travail que ce projet se donne :
**se tenir devant votre propre processeur graphique (GPU) et imposer, à tous les
clients, une charte, un moteur de règles et un budget de contexte que le serveur
compte vraiment.**

Un outil conçu pour un autre travail n'est pas critiqué ; la note reflète l'adéquation à
**ce** créneau. Plusieurs des entrées ci-dessous sont excellentes dans le leur, et trois
d'entre elles battent ce projet sur une colonne du tableau.

Trois sigles traversent les noms du tableau et la prose qui suit : **AI** est l'anglais
pour intelligence artificielle, un **LLM** est un grand modèle de langue — le genre de
modèle devant lequel se tiennent tous les outils cités ici — et **MCP** est le Model
Context Protocol, la norme par laquelle un agent découvre et appelle des outils.

Relevé le 19/10/2026, re-relevé le 20/10/2026.

## En un coup d'œil

<!-- TABLE:START -->
| Couche de service | Rien ne quitte le réseau | Filtre ce que l'agent lit | Filtre les déclarations d'outils | Refuse ce que l'agent exécute | Isole l'exécution des outils | Compte le budget côté serveur | Sert les standards d'équipe | Règles livrées avec tests | Tout client OpenAI | Largeur de fournisseurs |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ai-bunker** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| LiteLLM | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Bifrost | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Portkey | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Kong AI Gateway | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| NeMo Guardrails | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Guardrails AI | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| LLM Guard | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| agent-scan (ex mcp-scan) | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
| ToolHive | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
| Docker MCP Gateway | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ |
| Open Policy Agent | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ |
| Configuration côté client | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ |
<!-- TABLE:END -->

## Carte de positionnement

<!-- FIGURE:START -->
Représentation en deux dimensions du tableau ci-dessus, par analyse en composantes
principales (ACP) (voir [`standpoint`](https://github.com/warith-harchaoui/standpoint)).

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/ai-bunker/main/assets/landscape.png)

À lire comme une forme, pas comme un classement. Les axes se lisent **Horizontal —
Ressource ↔ Vigilance** et **Vertical — Sécurité ↔ Discipline**, et ce ne sont pas des
étiquettes fixes : ce sont ce en quoi les critères se décomposent, donc ajouter les deux
colonnes ci-dessus les a fait tourner. Ensemble ils portent environ 60 % du tableau.
<!-- FIGURE:END -->

## Ce que la carte montre vraiment

Trois grappes, et un coin vide.

**À gauche — les passerelles.** LiteLLM, Kong, Portkey. Elles répondent à *« comment
poser une seule surface compatible OpenAI sur une centaine de fournisseurs, avec clés,
budgets, reprises et observabilité ? »* et y répondent très bien. Ce qu'elles ne font
pas : regarder ce que l'agent lit ou s'apprête à exécuter. Une sortie d'outil pleine de
secrets et un `rm -rf ~` traversent une passerelle comme des octets ordinaires.

**Au centre et en bas à droite — les moteurs de règles.** NeMo Guardrails, Guardrails
AI, LLM Guard. Ils inspectent le contenu correctement — données personnelles, toxicité,
injection, conformité de schéma — et plusieurs le font mieux que ce projet. Ce qu'ils ne
sont pas : des passerelles. Ce sont des bibliothèques que votre application appelle, donc
un agent qui ne les appelle pas n'est pas protégé, et changer de harnais les perd.

**En bas à droite — la couche Model Context Protocol.** ToolHive et la Docker MCP
Gateway font tourner chaque serveur d'outils dans son propre conteneur, injectent les
secrets au moment de l'appel, et tiennent un inventaire pour que personne n'exploite un
serveur dont l'équipe sécurité n'a jamais entendu parler — ce que l'Open Worldwide
Application Security Project (OWASP), dans son MCP Top 10, appelle un serveur *fantôme*.
`agent-scan` (l'ancien `mcp-scan`, désormais chez Snyk) lit les descriptions d'outils et
repère celles qui sont empoisonnées, détecte les **rug pulls** en hachant chaque
description et en remarquant qu'elle change, et repère l'éclipse d'outil en comparant les
descriptions d'un serveur à l'autre. C'est la grappe dont ce projet a le plus à
apprendre, et celle qu'il recoupe le moins : eux sécurisent les *serveurs* d'outils, lui
sécurise la *conversation*.

**En bas à droite aussi — la politique, hors du chemin.** Open Policy Agent écrit et
teste des politiques mieux que tout le reste ici, et n'est pas sur le trajet de la
requête. Une configuration de harnais client est sur le trajet, et c'est un fichier sur
un portable.

**Le haut à droite est peu peuplé, et moins vide qu'avant.** La combinaison sur laquelle
ce projet se tient — la position de la passerelle (chaque requête, chaque client, sans
échappatoire), plus l'inspection du moteur de règles, plus un budget que le serveur
compte — n'est toujours assemblée nulle part ailleurs dans un seul processus. Mais le
domaine a bougé pendant qu'on écrivait, et la version honnête de l'affirmation est plus
étroite qu'en 2025 : les budgets de jetons à la passerelle sont désormais un motif
décrit, avec des limites de contexte par route et de la limitation de débit par budget
dans plusieurs produits. Ce qui reste distinctif, c'est *quel* comptage est utilisé et
*à quoi* il sert — le tokeniseur du moteur de service lui-même plutôt qu'une estimation,
le plancher détaillé **par propriétaire**, et un refus qui nomme le composant
responsable. C'est une affirmation sur la couverture, pas sur la qualité.

## Positionnement

Les passerelles routent ; les garde-fous inspectent ; aucun ne compte. `ai-bunker` est
l'intersection, et trois choses en découlent.

**Les deux bouts du tour d'un agent sont visibles depuis un seul endroit.** Un message
`role: "tool"` est du texte que le monde vient de tendre à l'agent — là où les secrets
fuient et là où l'injection indirecte arrive. Un `tool_call` portant une commande shell
est une commande **qui n'a pas encore tourné**. Filtrer le premier et refuser la seconde
sont les deux portées du même moteur de règles, et une passerelle est le premier endroit
où les deux coexistent.

**Le budget est compté par celui qui tient le tokenizer.** Chaque harnais estime ses
propres tokens et sous-compte ; Claude Code compacte à « contexte effectif moins une
marge de 13 000 tokens », soit une estimation sur une estimation. Une session mesurée
s'est crue sous 32 768 et en a envoyé 40 433. `ai-bunker` compte avec le tokenizer du
moteur qui sert, détaille le plancher **par propriétaire**, et refuse une session sans
place pour travailler — en nommant le composant responsable plutôt qu'en échouant plus
loin sur une erreur de contexte sur laquelle personne ne peut agir.

**Les standards arrivent, que le client les ait demandés ou non.** Une charte dans les
dotfiles de chacun dérive. Derrière le point d'entrée, il en existe une copie, versionnée,
et aucun moyen d'utiliser le modèle sans elle.

## Là où ce projet est en retard

À dire, parce qu'un paysage où un seul outil gagne toutes les colonnes n'est pas crédible.

- **Largeur de fournisseurs : LiteLLM, et de loin.** Une centaine de fournisseurs contre
  ce que vous configurez ici. Si la question est « appeler beaucoup de fournisseurs
  depuis un seul client », LiteLLM est simplement la réponse — et `ai-bunker` peut se
  placer devant lui plutôt que le concurrencer.
- **Classificateurs de contenu : LLM Guard et Guardrails AI.** Leurs scanners sont des
  modèles entraînés et des catalogues de validateurs curatés ; ce projet livre des
  expressions régulières versionnées avec un seuil d'entropie. Les regex sont relisibles,
  diffables et gratuites à l'exécution — un arbitrage assumé, et sur la qualité brute de
  détection c'est un arbitrage, pas une victoire.
- **Expressivité et test des politiques : OPA.** Rego exprime des conditions qu'une regex
  ne peut pas, et son outillage de test avec couverture est meilleur que
  `rules --check`. L'idée qu'une politique porte ses propres tests vient de là.
- **Isolation : ToolHive et la Docker MCP Gateway, totalement.** Ils font tourner
  chaque serveur d'outils dans un conteneur aux privilèges restreints et injectent les
  secrets au moment de l'appel. Ce projet n'isole rien : il décide de ce qui peut
  s'exécuter, puis rend la commande à un harnais qui l'exécute sur l'hôte. C'est l'écart
  que le papier du Jour 4 appelle le Pilier 1, et le combler n'est pas le travail d'une
  passerelle — désigner celui dont c'est le travail, si.
- **Provenance des outils : `agent-scan`.** Il lit la configuration du client, donc il
  sait de quel serveur vient chaque outil et peut comparer les descriptions entre
  origines. Une requête au format OpenAI ne porte pas cette information : ce projet peut
  signaler une paire en collision et ne peut pas dire laquelle est l'imposteur.
- **Débit : Bifrost.** Écrit en Go précisément pour sortir de sous le verrou global de
  l'interpréteur Python, avec du cache sémantique. Ici c'est du Python sur le trajet de
  la requête, et c'est dit.
- **Maturité.** C'est un `0.1.0-alpha` à côté de projets qui ont des années de
  production.

## Idées reprises au terrain

Rien de tout cela n'a été inventé ici, et le dire ne coûte rien.

- **Open Policy Agent : la politique porte ses tests, et les décisions sont journalisées
  dès le premier jour.** Les deux sont désormais porteurs ici — chaque règle livrée a ses
  `examples:` vérifiés en intégration continue (CI), et ça a attrapé trois motifs
  faux avant tout déploiement.
- **gitleaks : regex **et** seuil d'entropie, plus des listes d'exception par règle.** Un
  scanner qui crie au loup apprend à ses lecteurs à l'ignorer. Le seuil d'entropie ici a
  été mesuré, pas deviné.
- **Le *spotlighting* de Microsoft : marquer le contenu récupéré comme de la donnée.** La
  reconnaissance de motifs attrape les tentatives maladroites ; le marquage structurel
  est ce qui tient quand les motifs ratent.
- **La distinction « prévention / remède » de la recherche sur les harnais d'agents.**
  Les agents de prévention bornent structurellement la croissance du contexte ; ceux du
  remède la laissent croître et compressent. Ce projet est de la prévention, déplacée
  côté serveur — une case que la taxonomie n'a pas.
- **`agent-scan` : une description d'outil mérite d'être filtrée, et d'être hachée.** La
  première moitié est arrivée ici sous forme de portée `tool`. La seconde — épingler
  chaque description et remarquer qu'un serveur en change une en douce après son
  approbation, le *rug pull* — était nommée ici comme la meilleure idée du relevé que ce
  projet n'avait pas prise ; elle l'est désormais : `tool.contract_changed`, en deux
  niveaux. Ce qui leur reste en propre, c'est de savoir de quel serveur vient un outil,
  ce qu'une requête au format OpenAI ne dit pas.
- **Le cours 5-Day AI Agents de Google, Jour 4.** Il nomme deux techniques
  d'obscurcissement contre lesquelles ce projet ne s'était jamais testé. Trois sondes sur
  six passaient devant toutes les règles, et deux devant un `BLOCKER`. La valeur était la
  liste de contrôle, pas la connaissance : le papier dit que les charges invisibles
  contournent la *relecture humaine* et ne prétend nulle part qu'elles contournent la
  reconnaissance de motifs — c'est cette partie-là que les sondes ont trouvée.

## Fiche par outil

### LiteLLM

La passerelle open-source de référence : sous la licence qui porte le nom du
Massachusetts Institute of Technology (MIT), auto-hébergeable, une surface compatible
OpenAI sur plus de cent fournisseurs, avec clés virtuelles, budgets, replis et reprises.
Pour un déploiement souverain, c'est la réponse standard, et à juste titre.

Elle route ; elle n'inspecte pas. Rien en elle ne lit une sortie d'outil, ne refuse un
appel d'outil, ni ne compte un plancher de session. Complémentaire plutôt que
concurrente : `ai-bunker` devant LiteLLM donne les deux, et c'est un déploiement
raisonnable.

### Portkey

Passerelle plus garde-fous plus versionnement de prompts, avec la liste de
fonctionnalités la plus large du domaine. Le hic pour ce créneau est l'endroit où ces
fonctionnalités s'exécutent : cache sémantique, garde-fous et versionnement sont d'abord
du SaaS hébergé — du logiciel en tant que service, tournant sur les machines du
fournisseur — et l'option sur site est réservée à l'offre entreprise. Un garde-fou qui
s'évalue sur les serveurs d'un tiers est un garde-fou qui a déjà vu le prompt.

### Kong AI Gateway

Pertinent quand une passerelle doit vivre dans une infrastructure que vous exploitez
déjà — et seulement alors. Lourd à opérer sinon, avec la censure des données personnelles
et le SSO entreprise — *single sign-on*, l'authentification unique — derrière une
licence payante.

### NeMo Guardrails

NVIDIA, Apache 2.0. Rails programmables en Colang sur cinq types, avec un vrai contrôle
de flux de dialogue que les expressions régulières ne savent pas exprimer. Le plus
expressif des moteurs de règles.

L'arbitrage, c'est le langage dédié. Colang est un coût d'apprentissage payé par chaque
lecteur d'un fichier de règles ; ici ce sont des regex en YAML, un format de fichier de
configuration, avec une description, et elles se relisent sans manuel. Cet arbitrage se
défend à deux personnes et se dégrade à mesure que les règles se raffinent.

### Guardrails AI

Apache 2.0, avec un Hub de validateurs couvrant hallucination, données personnelles,
toxicité et conformité de format. Les validateurs sont meilleurs que tout ce qu'il y a
ici sur la classification de contenu, et sa culture de test est la plus proche de celle
de ce projet.

C'est une bibliothèque, pas une passerelle. Une application qui oublie de l'appeler n'est
pas protégée.

### LLM Guard

Le plus orienté sécurité des trois, avec le meilleur jeu de scanners spécifiquement sur
l'injection de prompt et la fuite de données. Même limite structurelle : appelé depuis
votre application plutôt que posté sur le trajet.

### Open Policy Agent

Pas un outil LLM du tout, et le meilleur moteur de politiques ici. Rego exprime des
conditions qu'une regex ne peut pas, `opa test` rapporte une couverture, et les journaux
de décision sont structurés et de première classe. Les deux idées que ce projet lui a
prises — la politique livrée avec ses tests, les décisions journalisées par défaut — sont
celles qui l'ont le plus amélioré.

Ce qu'il n'est pas : sur le trajet, et conscient des LLM. Il n'a aucune notion de sortie
d'outil, de budget de tokens ou de prompt système.

### Bifrost

Écrit en Go précisément pour sortir de sous le verrou global de l'interpréteur Python,
le goulot que partage toute passerelle en Python — celle-ci comprise. Elle parle le
Model Context Protocol dans les deux sens, à la fois client et serveur, si bien qu'un
agent se connecte à un seul point d'entrée pendant que Bifrost courtier les outils
derrière ; et elle livre regex, détection de secrets, modèle-juge et règles de garde-fou
MCP.

La réserve pertinente ici, c'est l'étagement : les garde-fous de sûreté du contenu sont
une fonction entreprise, là où Portkey livre les équivalents dans sa passerelle
open-source. Sur le débit, elle est simplement devant tout ce qui est écrit en Python.

### agent-scan (anciennement mcp-scan)

Invariant Labs l'a construit, Snyk le publie désormais, et il fait ce que fait la portée
`tool` de ce projet — lire les descriptions d'outils et repérer celles qui sont
empoisonnées — plus deux choses que ce projet ne peut pas. Il hache chaque description
et signale un **rug pull** quand un serveur en change une en douce après approbation, et
il compare les descriptions d'un serveur à l'autre pour trouver l'éclipse d'outil, ce
qu'il peut faire parce qu'il lit la configuration du client et sait donc d'où vient
chaque outil.

Un arbitrage mérite d'être nommé, puisque la première colonne de ce projet porte
là-dessus : par défaut, `agent-scan` envoie les noms et descriptions d'outils à une
interface de garde-fou hébergée, et le dit — `--local-only` garde tout sur la machine,
au prix annoncé d'une précision moindre.

### ToolHive

Fait tourner chaque serveur Model Context Protocol dans son propre conteneur aux
privilèges restreints, avec un registre, des journaux d'audit et une application de
l'identité, visant précisément la fin des serveurs *fantômes* — ceux que personne n'a
mis à l'inventaire. Application de bureau, outil en ligne de commande et opérateur
Kubernetes.

C'est l'illustration la plus nette de l'écart de ce projet : `ai-bunker` décide de ce
qui peut s'exécuter, puis rend la commande à un harnais qui l'exécute sur l'hôte.
ToolHive répond à la question que celui-ci ne tente pas.

### Docker MCP Gateway

La même idée avec la distribution de Docker derrière : un conteneur par serveur
d'outils, les secrets injectés au moment de l'appel plutôt que posés dans un fichier de
configuration. Plus étroit que ToolHive et, pour une équipe qui fait déjà tourner
Docker, presque gratuit.

### Configuration du harnais client

La réponse par défaut : `opencode.json`, `.claude/settings.json`, un dossier de plugins.
C'est le seul endroit où **certaines** choses peuvent vivre — une lecture de fichier est
bornée avant qu'elle n'arrive, et aucun point d'entrée ne peut atteindre ça. Ce projet
livre exactement celles-là et rien de plus (voir [`clients/`](clients/README.md)).

Ce qu'elle ne peut pas faire, c'est tenir : c'est un fichier sur un portable, désactivé
par une édition, et absent dès que quelqu'un ouvre un autre harnais.

Il vaut la peine de séparer les deux moitiés de cette ligne, parce qu'elles ne valent pas
la même chose et que l'éditeur les sépare aussi. Un hook **est** de l'application — c'est
pourquoi cette colonne n'est pas à une étoile. Un fichier d'instructions ne l'est pas, et
Anthropic le dit de ses propres fichiers :

> Claude treats them as context, **not enforced configuration**. To block an action
> regardless of what Claude decides, use a PreToolUse hook instead.
>
> (« Claude les traite comme du contexte, **pas comme de la configuration appliquée**.
> Pour bloquer une action quoi que Claude décide, utilisez plutôt un hook PreToolUse. »)
>
> — Anthropic, [*How Claude remembers your project*](https://code.claude.com/docs/en/memory)

Un `CLAUDE.md` n'est donc pas une version faible d'un moteur de règles ; c'est une chose
d'une autre nature, et l'écart est la description qu'en fait l'éditeur lui-même plutôt
qu'une caractérisation d'un concurrent par ce projet. Ce qui reste, pour le hook qui,
lui, applique, c'est la portée : il lie un harnais sur une machine, et la ligne est notée
là-dessus.
