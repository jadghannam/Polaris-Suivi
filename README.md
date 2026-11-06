# Polaris — plateforme de suivi

Suivi quotidien du fonds Polaris (groupe G2, Master 222, 2026-2027).

Le programme récupère les cours chaque soir, recalcule le classement
Novy-Marx et le DCF inversé, compare chaque ligne à son indice et à son
secteur, et affiche sur une page web ce qu'il faut surveiller, ce qui doit
sortir et par quoi le remplacer.

**La plateforme ne passe aucun ordre.** Elle signale, le comité décide, les
ordres sont passés à la main sur StockTrak.

## Installation, une seule fois

1. Créer un dépôt GitHub — public ou privé, les deux marchent — et y déposer
   ce dossier.

2. **Settings → Pages** : source « Deploy from a branch », branche `main`,
   dossier `/docs`. GitHub donne alors une adresse du type
   `https://<compte>.github.io/<depot>/`. C'est l'adresse de la plateforme,
   partageable avec le groupe.

3. **Settings → Actions → General → Workflow permissions** : cocher
   « Read and write permissions ». Sans ça, le programme ne pourra pas
   réécrire les données chaque soir.

4. **Actions → Mise a jour quotidienne → Run workflow.** Premier lancement
   manuel. Le log s'affiche dans l'onglet Actions ; s'il y a une erreur, c'est
   là qu'elle sera lisible.

Ensuite il n'y a plus rien à faire : le programme tourne tout seul du lundi au
vendredi à 18h40 UTC, après la clôture européenne.

## Après chaque passage d'ordres

1. Exporter les positions depuis StockTrak (fichier `OpenPosition_JJ_MM_AAAA.csv`).
2. Sur la page, mettre à jour les deux chiffres de la zone de dépôt —
   transactions consommées et liquidités, lus dans StockTrak —, puis y glisser
   le fichier. C'est tout :
   - la page se recalcule aussitôt avec les cours de l'export ;
   - l'export et une ligne de `data/compte.csv` partent dans un seul commit ;
   - ce commit relance le programme, qui recalcule tout avec les cours Yahoo
     du moment, et la page bascule seule sur ces données officielles quelques
     minutes plus tard. D'ici là, l'aperçu reste affiché même si on recharge.

   La première fois, coller une clé GitHub *fine-grained* limitée à ce dépôt,
   permission **Contents : Read and write** seulement. Elle reste dans le
   navigateur, jamais dans la page.

Le programme prend toujours l'export le plus récent d'après la date du nom ;
les anciens restent dans `data/` comme trace. Sans export, il se rabat sur
`data/positions.csv`. Une ligne de l'export sans correspondance dans
`data/univers.csv` (colonne `Symbole StockTrak`) est traitée comme un ETF :
elle compte dans la valeur du fonds et l'allocation, mais pas dans le
classement ni le DCF, et le journal la nomme.

## Ce qui tourne, et à quel rythme

| Donnée | Rythme | Pourquoi |
|---|---|---|
| Cours, volumes, taux de change | chaque jour | ils bougent chaque jour |
| Comptes des sociétés | chaque samedi | ils ne changent qu'aux publications, et Yahoo révise ses chiffres en silence |

Les anomalies — cours manquant, devise introuvable, états financiers absents —
sont écrites dans le journal, visible en bas de la page. Un titre qui disparaît
silencieusement du classement est le pire défaut possible pour ce genre de
chaîne.

## Les règles, en clair

**Deux seuils par axe.** Le premier met le titre sous surveillance, le second
ouvre la procédure de sortie.

| Déclencheur | Surveillance | Sortie |
|---|---|---|
| Classement | rang > 75, ou plancher franchi | rang > 100 |
| DCF inversé | marge entre −1,5 pt et 0 | marge > 0 sur 5 clôtures consécutives |
| GP/A ajusté | — | passe sous la médiane sectorielle |
| Décrochage vs indice | −20 % | −35 % |
| Dispersion WACC | > 40 % | jamais — surveillance seule |

**Pourquoi un décrochage relatif et pas un stop-loss.** Une baisse de cours
améliore le book-to-market, donc le rang de valorisation : un stop-loss absolu
vendrait systématiquement les titres les moins chers du portefeuille, c'est-à-dire
exactement ceux que la méthode dit de garder. En relatif, un écart de 20 points
contre l'indice veut dire que le marché sait sur cette société quelque chose que
nos comptes ne disent pas encore.

**Pourquoi cinq clôtures.** Un franchissement d'un seul jour n'est pas un
signal. Sans cette condition, un pic isolé déclencherait une cession et
consommerait deux transactions sur les 400.

**Pas de sortie sans remplaçant.** Un remplaçant est éligible s'il est dans la
liste de suivi, passe les deux planchers, porte un verdict DCF A ou B — pas C,
on ne remplace pas un titre marginal par un autre titre marginal —, n'a aucun
veto qualitatif et reste sous 5 % du volume quotidien. À éligibilité égale,
celui qui réduit l'écart sectoriel l'emporte.

## Pièges de données déjà rencontrés

Ils sont dans le code parce qu'ils nous ont déjà coûté cher.

**Les pence.** Londres cote en pence. Sans conversion, les soixante-quatre
valeurs britanniques affichaient un book-to-market cent fois trop faible et
auraient toutes été éliminées sans que rien ne le signale.

**Les cotations dans une autre unité que celle de leur place.** Compass Group,
InterContinental et Metlen sortent de Yahoo en livres ou en euros, traités
comme des pence. Garde-fou générique depuis le 6 novembre : tout book-to-market
hors de [0,01 ; 3] (`BM_PLAUSIBLE` dans `config.py`) est nommé dans le journal
et retiré du classement avant le calcul des rangs. Si c'est une ligne détenue,
elle passe en surveillance, jamais en sortie : une donnée suspecte ne doit pas
ressembler à un signal de vente.

**Les lignes fantômes.** Deux tests, qui ne détectent pas la même chose.

*Liquidité, automatique.* Une cotation sans volume et sans amplitude du jour
n'est pas traitée sur le marché réel. Yahoo le dit, donc la machine le vérifie
chaque soir et la ligne sort de la liste de suivi.

*Disponibilité sur StockTrak, manuelle.* Yahoo ne sait pas si StockTrak porte
le titre ni à quel prix il l'affiche. L'ETF HIGH se négocie normalement à
Londres — il aurait passé le test de liquidité sans problème — alors que
StockTrak le cotait à un centième de sa valeur. Aucune API ne permet de le
vérifier. La colonne `verifie_stocktrak` de `data/univers.csv` porte donc la
date du dernier contrôle fait à la main dans le navigateur, et **un titre
jamais vérifié n'est jamais proposé comme remplaçant**. Au moment de passer
l'ordre, le contrôle reste arithmétique : quantité × prix réel doit donner le
montant visé.

**Les conventions de signe de Yahoo.** Les capex sortent en négatif, la
variation du besoin en fonds de roulement est inversée. Les deux sont
redressées une fois pour toutes dans `collecte.py`.

## Organisation du code

```
polaris/
  config.py       tous les seuils, et rien d'autre
  journal.py      trace d'exécution
  collecte.py     Yahoo : cours quotidiens, fondamentaux hebdomadaires
  classement.py   GP/A ajusté du secteur, book-to-market, planchers
  dcf.py          FCFF, valeur d'entreprise, résolution de g₁, verdicts
  signaux.py      zones, persistance, remplaçants, budget de transactions
  positions.py    export StockTrak, actions / ETF, data/compte.csv
  maj.py          point d'entrée, écrit docs/data.json
docs/
  index.html      la page de suivi, lit data.json
data/
  *.csv           univers, positions, fondamentaux, historique des signaux
```

Tous les seuils vivent dans `config.py` et nulle part ailleurs. Toute
modification est datée en commentaire : c'est ce qui empêche d'ajuster une
règle après avoir vu le résultat qu'elle produit sur une société que l'on
aimerait garder.

## Lancer en local

```bash
pip install -r requirements.txt
python -m polaris.maj
python -m http.server -d docs 8000   # puis http://localhost:8000
```

## Calendrier des comités

Fixé à l'avance, et c'est le point : une date de comité choisie après avoir vu
les cours n'est plus une règle, c'est un arbitrage.

| Comité | Date |
|---|---|
| 1 — révision complète sur données fraîches | vendredi 13 novembre 2026 |
| 2 | vendredi 4 décembre |
| 3 | vendredi 18 décembre |
| 4 | vendredi 8 janvier 2027 |
| 5 | vendredi 29 janvier |
| 6 | vendredi 19 février |
| 7 — dernier | vendredi 12 mars |

Trois semaines d'écart, sauf le troisième avancé pour éviter Noël, et rien
dans les quinze derniers jours avant la clôture du 31 mars. Au plus trois
échanges par comité, soit 42 transactions au total sur les 300 réservées aux
actions.

Le premier comité ne peut pas se tenir avant que la plateforme ait produit
cinq clôtures : la règle de confirmation a besoin d'un historique, et cet
historique démarre au premier lancement.
