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

Relevé le 19/10/2026, re-relevé les 20/10/2026 et 29/10/2026.

## En un coup d'œil

<!-- TABLE:START -->
| Couche de service | Rien ne quitte le réseau | Filtre ce que l'agent lit | Filtre les déclarations d'outils | Refuse ce que l'agent exécute | Isole l'exécution des outils | Compte le budget côté serveur | Sert les standards d'équipe | Règles livrées avec tests | Tout client OpenAI | Largeur de fournisseurs |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ai-bunker** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| LiteLLM | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Bifrost | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Portkey | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Kong AI Gateway | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| agentgateway | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Envoy AI Gateway | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
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
La carte est tracée depuis `assets/paysage.csv`, qui est ce même tableau en chiffres —
et en français : jusqu'ici cette page montrait la carte anglaise, avec des axes et des
critères qu'aucun lecteur francophone n'avait demandés. `tests/test_landscape.py`
échoue si le tableau et le fichier de chiffres cessent de s'accorder.

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/ai-bunker/main/assets/paysage.png)

À lire comme une forme, pas comme un classement. Les axes se lisent **Horizontal —
Ouverture ↔ Rigueur** et **Vertical — Sécurité ↔ Adaptabilité**, et ce ne sont pas des
étiquettes fixes : ce sont ce en quoi les critères se décomposent, donc chaque ligne
ajoutée les fait tourner. Ensemble ils portent 58 % du tableau — 29,5 % et 28,2 %, ce
qu'il vaut mieux dire franchement : deux axes qui expliquent un peu plus de la moitié
de dix colonnes sont une esquisse du terrain, pas une mesure. Les 42 % qu'ils laissent
tomber sont la raison d'être de la prose ci-dessous.
<!-- FIGURE:END -->

## Ce que la carte montre vraiment

![Un tour qui traverse de gauche à droite quatre boîtes — un agent de code, la position de passerelle, un moteur d'inférence et les serveurs d'outils — avec sous chacune les outils qui s'y tiennent : configuration côté client et bibliothèques de garde-fous chez l'agent ; LiteLLM, Kong, Portkey, Bifrost, agentgateway, l'Envoy AI Gateway et ai-bunker à la passerelle ; ToolHive, la Docker MCP Gateway et agent-scan autour des serveurs d'outils. Rien ne se tient au moteur d'inférence.](assets/figure-path.fr.svg)

La carte ci-dessus place un outil selon ses notes ; celle-ci le place selon l'endroit où il se tient, que les notes ne peuvent pas montrer. Deux outils séparés d'un centimètre dans le nuage peuvent se trouver de part et d'autre du moteur d'inférence.

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

**Au milieu en haut — les passerelles natives pour agents, et elles sont neuves.**
`agentgateway` et l'Envoy AI Gateway n'étaient pas dans ce tableau il y a dix jours et
c'est le changement le plus important qu'il ait connu. Ce sont deux proxys sur le
trajet de la requête, tous deux auto-hébergeables devant un moteur local, tous deux
porteurs d'une politique d'outils MCP, et tous deux comptent des jetons. Ils se placent
entre la grappe du routage et le coin de ce projet — exactement là où le terrain se
déplace.

**Le haut à droite est peu peuplé, et plus vide qu'il n'y paraît.** La combinaison sur
laquelle ce projet se tient — la position de la passerelle (chaque requête, chaque
client, sans échappatoire), plus l'inspection du moteur de règles, plus un budget que
le serveur compte — n'est toujours assemblée nulle part ailleurs dans un seul
processus. Mais l'écart s'est resserré deux fois ce mois-ci, et la version honnête de
l'affirmation se resserre avec lui.

Deux distinctions survivent, et deux seulement. La première est **quel comptage, et
pour quoi**. Les budgets de jetons à la passerelle sont désormais une fonctionnalité
ordinaire : `agentgateway` fait du jeton-par-minute, l'Envoy AI Gateway de la
limitation de débit sensible aux jetons avec attribution des coûts par équipe. Ceux-là
comptent une **dépense**, contre un quota, pour maîtriser une facture. Celui-ci compte
la **fenêtre de contexte** — le plancher qu'une session paie avant que quiconque parle,
mesuré par le tokeniseur du moteur de service lui-même, détaillé **par propriétaire**,
et refusé quand ce qui reste ne peut pas tenir une conversation. Une passerelle qui
vous limite à 10 000 jetons par minute n'a rien dit sur la question de savoir si votre
prochaine requête tient.

La seconde est **la charte**. La documentation d'`agentgateway` dit explicitement qu'il
ne modifie jamais une invite, et c'est une position raisonnable pour un proxy dont le
métier est le transport. C'est l'inverse de celui-ci. Un standard qui n'arrive que
lorsque le client pense à l'envoyer n'est pas un standard, et le seul endroit d'où il
peut arriver sans la coopération du client, c'est derrière l'endpoint.

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
  la requête — et cela se disait sans chiffre, ce qui n'est pas de la franchise mais du
  silence. `scripts/measure_overhead.py` le mesure : sur un Apple M2 Max, le pipeline
  entrant coûte **0,3 ms** pour un tour nu, **1,7 ms** pour un tour déclarant douze
  outils, et **56 ms (95ᵉ centile 95 ms)** pour un tour portant un résultat d'outil de
  40 kilooctets. Le filtrage croît avec ce qui arrive, et c'est la raison d'être du
  plafond de requête. Face à un modèle qui met des secondes à répondre, les deux
  premiers disparaissent ; le troisième non, et un proxy en Go ne le paierait pas.
- **Comptabilité à l'admission : `go-llmflow/gateway`, et là c'est un trou.** Son
  travail sur les budgets réserve le coût **pire cas** d'une requête avant de
  l'admettre, puis régularise après — parce que compter après la réponse laisse des
  requêtes concurrentes se mesurer toutes au même chiffre et dépasser ensemble :
  3,3× la limite sous concurrence là-bas, contre 0,03 % avec réservation. Ce projet
  filtre et mesure une requête, puis l'admet ; `max_tokens` n'entre pas du tout dans
  le plafond, donc une requête admise juste sous la ligne peut produire un tour
  au-dessus. C'est la même arithmétique, et elle n'est pas encore écrite ici.
- **Gouvernance : `agentgateway`.** C'est un projet de la Linux Foundation, avec un
  foyer institutionnel pour la couche passerelle. Ceci est le dépôt d'un seul auteur.
  Pour quiconque doit répondre à un achat qui demande à qui appartient la chose,
  c'est la réponse, et ce n'est pas celle-ci.
- **Maturité.** C'est un `0.2.0-alpha` à côté de projets qui ont des années de
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
- **`go-llmflow/gateway` : réserver, puis régulariser.** Le motif ci-dessus, nommé ici
  parce que c'est la meilleure idée de ce relevé que ce projet **n'a pas** prise. Une
  barrière qui vérifie puis admet est une barrière que deux requêtes concurrentes
  franchissent ensemble. Consignée dans `.private/ASSESSMENTS.md` comme le travail du
  tour suivant, plutôt que revendiquée ici comme une fonctionnalité.
- **Envoy AI Gateway : l'attribution vaut aussi pour l'argent.** L'attribution des
  coûts par équipe, c'est l'argument du plancher-par-propriétaire pointé vers la
  facture au lieu de la fenêtre. Les deux sont la même phrase — un nombre que personne
  ne peut décomposer est un nombre que personne ne peut réduire — et la voir arriver
  indépendamment dans un second produit est la meilleure preuve qu'elle est juste.
- **Le MCP Scanner de Cisco : des règles YARA pour les métadonnées d'outils.** Un
  format de règles avec dix ans d'outillage derrière lui, pointé vers les descriptions
  d'outils. Les règles de ce projet sont des expressions régulières versionnées avec
  leurs propres `examples:` ; un format de règles partagé et portable vaut strictement
  mieux qu'un format privé, et cela mérite d'être dit même si rien n'en a encore été
  repris.
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

### agentgateway

Le proxy Rust de Solo.io, donné à la Linux Foundation et quatrième projet de l'Agentic
AI Foundation depuis juin 2026 — la première fois que la couche passerelle elle-même
reçoit une gouvernance institutionnelle, ce qui compte davantage que n'importe quelle
fonctionnalité isolée. Un seul plan de données pour le trafic HyperText Transfer Protocol (HTTP), gRPC,
MCP, Agent2Agent (A2A) et LLM, donc les moitiés « agent » et « non-agent » d'un réseau
s'exploitent avec les mêmes motifs. Clés d'interface de programmation (API) virtuelles
par consommateur, contrôle d'accès par rôle au
niveau de l'outil, limites anti-*denial-of-wallet*, comptabilité en jetons par minute
plutôt qu'en requêtes par minute, bascule sur état de santé, OpenTelemetry d'origine.

C'est ce qui ressemble le plus, dans ce tableau, à la position de ce projet, et les
deux diffèrent sur exactement deux points. Sa comptabilité de jetons **règle après la
réponse**, en lisant l'usage renvoyé par le modèle — un quota de dépense, pas une
vérification que la requête suivante tient. Et il ne touche pas aux invites, par choix
et par documentation. C'est le bon arbitrage pour un proxy de transport, et c'est
pourquoi une charte ne peut pas y vivre.

Si la question est « une seule porte d'entrée gouvernée pour chaque protocole qu'un
agent parle », c'est la réponse, et ce projet ne la concurrence pas. Mettez
`ai-bunker` derrière.

### Envoy AI Gateway

Envoy et la Gateway API de Kubernetes, étendus par un routage conscient des LLM ;
rebaptisé Agent Router. Version 1.0 en juin 2026 : seize fournisseurs derrière une
surface compatible OpenAI, traduction entre fournisseurs, bascule de fournisseur,
limitation de débit sensible aux jetons, et une passerelle MCP dont l'autorisation par
outil s'écrit en Common Expression Language (CEL).

Deux choses méritent d'être prises au sérieux. **L'attribution des coûts par équipe**
est le même réflexe que le plancher-par-propriétaire de ce projet — un nombre que
personne ne peut décomposer est un nombre que personne ne peut réduire — appliqué à la
dépense plutôt qu'au contexte. Et **CEL pour l'autorisation par outil** est un vrai
langage de politique sur le trajet de la requête : plus qu'une expression régulière ne
sait exprimer, moins que Rego ; la comparaison qui compte est avec Open Policy Agent
ci-dessus, pas avec ce projet.

Le prix, c'est le modèle de configuration d'Envoy, long à apprendre quand on n'est pas
déjà dans cet écosystème, et une pile qui suppose Kubernetes. Pour un poste de travail
et une carte graphique, cela fait beaucoup de machinerie.

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
