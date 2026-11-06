# Contexte du projet — à lire avant toute intervention

Ce document existe parce que la méthode de ce fonds a été construite ailleurs
que dans ce dépôt, et qu'une session qui n'aurait que le code sous les yeux
reproduirait des erreurs qui nous ont déjà coûté cher.

Le `README.md` décrit **comment la plateforme marche**. Ce document-ci dit
**pourquoi elle marche comme ça**, où en est le fonds, et ce qui reste ouvert.

---

## 1. Le fonds

Simulation de gestion du Master 222 (Asset Management, Paris Dauphine-PSL),
année 2026-2027, groupe G2, fonds **Polaris**. Quatre étudiants, Jad Ghannam
et trois coéquipiers ; le compte StockTrak est au nom de Hugo Do Cao.

- Capital : **1 000 000 €**, **400 transactions** maximum
- Négociation ouverte le **2 novembre 2026**, clôture le **31 mars 2027**
- Mandat : « Diversifié Dynamique »
- Indice de référence : **70 % STOXX Europe 600 Net Return EUR** + 25 %
  (65 % iBoxx € Corporates + 35 % iBoxx € Liquid High Yield) + 5 % €STR capitalisé

Ce n'est pas un portefeuille réel, mais il est noté : chaque règle doit être
**écrite avant d'être appliquée**, et toute exception doit être datée et
justifiée. C'est la contrainte dominante du projet. Une règle ajustée après
avoir vu le résultat qu'elle produit sur une société qu'on aimerait garder est
une faute de méthode, pas une optimisation.

## 2. La philosophie de sélection

Elle repose sur un seul article : **Novy-Marx (2013), « The Other Side of
Value: The Gross Profitability Premium », JFE 108(1)**.

- Rentabilité brute rapportée à l'actif : `GP/A = (CA − coût des ventes) / actif total`
- Ajustée de la **médiane de son secteur GICS**, parce que l'intensité
  capitalistique varie énormément d'un secteur à l'autre
- Combinée **moitié-moitié** avec le book-to-market. Les deux jambes sont
  négativement corrélées (−0,57 dans l'article), donc le mélange a une
  volatilité plus faible que chacune prise isolément
- **Planchers** : 40e percentile de rentabilité, 30e de valorisation. Ajoutés
  à la demande du professeur. Un excellent rang sur une jambe ne doit pas
  racheter un rang catastrophique sur l'autre
- Liste de suivi : les **60 premiers**. Le DCF inversé s'applique à ces 60, pas
  au portefeuille

**Principe directeur : un filtre classe, un veto exclut.** Le classement ne
décide de rien tout seul ; il produit une liste sur laquelle on applique
ensuite des exclusions documentées.

## 3. Le DCF inversé

On ne cherche pas la valeur d'une action. On part de la valeur d'entreprise
observée et on résout la seule inconnue laissée libre : la croissance du flux
de trésorerie disponible pendant la phase explicite. Cette croissance implicite
`g1` est comparée à celle que la société a **réellement réalisée**. Si le marché
demande nettement plus que ce que l'entreprise a su faire, le titre sort.

Le détail du modèle est dans `polaris/dcf.py`, chaque fonction porte son
commentaire. Les points qui ne se devinent pas :

- Le **FCFF est moyenné sur trois exercices**. Un seul suffit à faire mentir le
  modèle : un exercice où le capex tombe produit un flux qui ne se répétera pas
- Les **minoritaires s'ajoutent** à la VE (le FCFF est généré par tout le
  périmètre consolidé), les **mises en équivalence se retranchent** (leur
  résultat ne passe pas par l'EBIT, les laisser serait payer deux fois)
- Le **plancher du seuil de veto** à la croissance perpétuelle existe parce que
  sans lui, une société au CAGR négatif pour cause de cessions (SSE, Solvay,
  Telefónica) serait vetée quel que soit son prix
- Le **WACC est sectoriel, pas individuel**. Un bêta propre à chaque société
  serait estimé sur un historique court et ajouterait du bruit qu'on ne saurait
  pas interpréter. Limite assumée : les bêtas désendettés viennent de
  l'échantillon **américain** de Damodaran, le fichier européen n'étant pas
  téléchargeable. Le levier et le taux d'impôt qui servent à les ré-endetter
  viennent, eux, de notre propre univers

## 4. Où en est le fonds

**Poche actions investie le 2 novembre : 26 lignes**, équipondérées autour de
27 000 € chacune, pour environ 700 000 €. Elles sont dans `data/positions.csv`,
et le détail du cheminement — 192 titres investissables, 72 passent les
planchers, 60 en liste de suivi, 32 survivent au DCF, 26 après veto qualitatif
— est reconstituable depuis les fichiers de `data/`.

**27 transactions consommées** sur 400 : 26 achats plus une part de test d'un
ETF obligataire.

**La poche obligataire n'est pas constituée.** StockTrak ne permet pas
d'acheter des obligations en direct, ce que la note décrit pourtant. Le repli
est un ETF, et c'est là qu'on a découvert que la plateforme cote certaines
lignes à un centième de leur valeur. Deux candidats identifiés et vérifiés :
`IEAC` (iShares Core € Corp Bond, IE00B3F81R35, ~116 €) et `HIGH` (iShares €
High Yield Corp Bond, IE00BF3N7094, ~6 €, ligne suisse uniquement, la ligne
londonienne est fausse).

**Un veto qualitatif a écarté 6 titres** au 23 octobre : AkzoNobel (fusion avec
Axalta), Rio Tinto (discussions Glencore confirmées), Coca-Cola HBC (prise de
contrôle de CCBA), DCC (offre KKR), Reckitt (contentieux NEC), Associated
British Foods (enquête de concurrence). Chaque exclusion porte sa source dans
l'historique du projet. La règle appliquée : on exclut **sur un fait établi**,
jamais sur une rumeur.

## 5. Ce qui est en place, et ce qui ne l'est pas

**En place.** La chaîne quotidienne tourne seule sur GitHub Actions et publie
sur `jadghannam.github.io/Polaris-Suivi`. Le classement et le DCF se
recalculent chaque soir, les zones de surveillance et de sortie fonctionnent,
la liste des remplaçants éligibles est produite, le budget de transactions est
suivi.

**Pas en place.**

- **L'allocation 70/22/8 n'est pas suivie.** La note macro prévoit des bandes
  et sept déclencheurs écrits ; personne ne les surveille. C'est le plus gros
  trou fonctionnel
- **La Suisse n'est pas dans l'univers.** Elle pèse 14,6 % de l'indice. Elle
  avait été écartée en septembre sur des cotations gelées en 2015-2017 ; cette
  raison a disparu, vérifié le 5 novembre sur Nestlé, Novartis, ABB, Sika et
  Holcim, tous avec cours du jour, amplitude et volume réels
- **L'Allemagne et l'Italie restent inaccessibles.** Vérifié : SAP ne renvoie
  rien, BASF et Heidelberg affichent « pas disponible pour le trading simulé »,
  et Adidas ne sort qu'une ligne secondaire suisse sans volume. L'entrée
  « Francfort » du menu StockTrak ne donne pas accès aux actions allemandes
- **L'écart sectoriel est hors contrainte.** L'industrie pèse 34,3 % du
  portefeuille contre 15,2 % dans l'indice, soit **+19 points** pour une
  contrainte de ±10. Ce n'est pas un choix : c'est ce que le filtre produit,
  parce que GP/A récompense les modèles peu capitalistiques. À arbitrer
  explicitement, pas à subir

## 6. Les pièges de données, et pourquoi ils sont dans le code

Chacun nous a coûté une erreur réelle. Ils sont tous déjà traités, mais il faut
savoir qu'ils existent avant de toucher à `collecte.py`.

**Les sous-unités.** Yahoo cote Londres en pence et le signale par « GBp », avec
un p minuscule. Sans conversion, les 64 valeurs britanniques ressortent avec un
book-to-market cent fois trop faible et sont toutes éliminées sans que rien ne
le signale. Arrivé deux fois : en septembre sur la collecte, le 5 novembre sur
la plateforme.

**Les lignes cotées dans une autre devise que celle de leur place.** La règle
« `.L` donc pence » est fausse pour au moins trois titres : **Compass Group,
InterContinental Hotels et Metlen**. Leur flux renvoie un nombre de l'ordre de
33, 176 et 45, que Yahoo *et StockTrak* traitent comme des pence. StockTrak
affiche Compass Group à 0,33 £ alors que son graphique montre 34. Ces trois
titres sont dans `data/blocages.csv`. **Un garde-fou générique manque encore** :
tout book-to-market absurdement élevé devrait être signalé automatiquement,
parce qu'il n'y a aucune raison que ces trois-là soient les seuls.

**Les lignes fantômes.** Certaines cotations existent mais ne sont jamais
traitées : volume vide, amplitude nulle, carnet à 0,00 / 0,00. Le test de
liquidité les attrape. Mais il ne détecte pas les erreurs propres à StockTrak :
l'ETF HIGH se négocie normalement à Londres et aurait passé le test, alors que
StockTrak le cotait à un centième de sa valeur. D'où la colonne
`verifie_stocktrak` et le fichier `blocages.csv`, qui sont la part humaine du
contrôle.

**Le débit de Yahoo.** La première version du collecteur interrogeait Yahoo
titre par titre, soit près de quatre cents appels. Depuis une adresse
résidentielle ça passait ; depuis un serveur GitHub, Yahoo a coupé à 64 titres
sur 192. Le résultat était une poche à 240 000 € au lieu de 700 000 et **20
titres affichés en zone de sortie**. D'où le téléchargement groupé.

**Et la leçon qui vaut plus que les autres : une donnée manquante ne doit
jamais ressembler à un signal de vente.** C'est ce qui a failli arriver. Si
cette propriété est cassée par une modification future, le reste n'a plus
d'importance.

## 7. Les règles de gestion

Détaillées dans le README et dans `config.py`. Les trois qui demandent une
explication :

**Pourquoi un décrochage relatif et pas un stop-loss.** Une baisse de cours
améliore le book-to-market, donc le rang de valorisation. Un stop-loss absolu
vendrait systématiquement les titres les moins chers du portefeuille,
c'est-à-dire exactement ceux que la méthode dit de garder.

**Pourquoi cinq clôtures consécutives.** Un franchissement d'un seul jour n'est
pas un signal, et il coûterait deux transactions sur les 400.

**Pourquoi la dégradation a deux niveaux.** La première version sortait un titre
dès que son GP/A ajusté passait sous la médiane de son secteur. Teleperformance
en est sortie pour 43 points de base, alors que son rang était 21 et que son
DCF lui laissait 34 points de marge. Or cette médiane bouge dès qu'un titre
entre ou sort de l'univers : on vendait sur le déplacement d'une médiane, pas
sur la société. Corrigé le 5 novembre.

## 8. Calendrier

Sept comités, fixés à l'avance : **13 novembre**, 4 décembre, 18 décembre,
8 janvier, 29 janvier, 19 février, 12 mars. Rien dans les quinze derniers jours
avant la clôture.

Le premier n'est pas un rebalancement ordinaire : c'est la révision que le
groupe n'a pas pu faire au lancement, le portefeuille ayant été construit sur
des cours du 25 septembre et acheté le 2 novembre. Plusieurs titres avaient
déjà franchi leur seuil au moment de l'achat.

Enveloppe par comité : le budget actions restant divisé par le nombre de
comités restants, soit environ 42 transactions ou 21 échanges. C'est un
maximum, pas un objectif.

## 9. Ce qui reste à faire, par ordre d'utilité

1. **Garde-fou sur les devises aberrantes** — signaler tout book-to-market
   implausible plutôt que de dépendre d'une liste d'exceptions tenue à la main
2. **Suivi de l'allocation 70/22/8** avec les bandes et les sept déclencheurs
   de la note macro
3. **Intégration de la Suisse** — voir la section suivante
4. **Historique de chiffre d'affaires** pour les titres qui entrent en liste de
   suivi sans y figurer : `historique_ca.csv` ne couvre que les 60 de septembre,
   et le repli sur la médiane sectorielle est une approximation
5. **Mesure de risque ex ante et attribution de performance**, annoncées dans la
   note synthétique et jamais écrites

## 10. Sur l'intégration de la Suisse

La place fonctionne, c'est vérifié. Mais **je recommande de ne pas l'intégrer
avant le comité du 13 novembre.**

Ajouter 14,6 points d'univers change le classement, donc potentiellement
plusieurs lignes du portefeuille. Le premier comité a déjà pour mission
d'appliquer les règles à un portefeuille construit sur des données périmées ;
lui faire absorber en même temps un univers qui n'a jamais traversé un cycle
complet, c'est mélanger deux décisions qu'on ne saura plus démêler dans le
rapport final.

Le bon moment est **après le 13**, en traitant l'élargissement comme une
décision de gestion datée et justifiée.

Ce qu'il faudra alors, dans l'ordre :

- relever dans StockTrak le symbole, la devise, la date et surtout le **volume**
  de chaque valeur suisse non financière du SMI et du SMIM, et renseigner
  `verifie_stocktrak`. Cette étape ne peut pas être automatisée : aucune API,
  et le moteur de recherche de StockTrak est capricieux. Candidats SMI :
  NESN, NOVN, ROG, ABBN, CFR, LONN, GIVN, SIKA, HOLN, ALC, GEBN, KNIN, SOON,
  SCMN, SCHP, STMN, LOGN, SDZ. Les financières — UBS, Zurich, Swiss Re,
  Partners Group — restent exclues comme partout ailleurs
- ajouter les lignes à `data/univers.csv` avec leur secteur GICS
- **corriger la collecte hebdomadaire** : elle met à jour les lignes existantes
  mais n'ajoute pas les nouveaux tickers. Sans ça les valeurs suisses resteront
  sans fondamentaux et donc sans rang

## 11. Répartition du travail

Le **dépôt** — code, page, collecte, tests — est le terrain de Claude Code.

Le **fonds** — méthode, notes, DCF, vetos qualitatifs, comités, vérifications
dans StockTrak — reste traité en conversation avec Jad, parce que ça demande
son navigateur et son jugement.

Le point de contact est ce dépôt. Toute règle décidée ailleurs doit finir
écrite dans `config.py`, datée et commentée.
