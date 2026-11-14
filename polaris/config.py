# -*- coding: utf-8 -*-
"""
Parametres de la plateforme de suivi - fonds Polaris (groupe G2, Master 222).

Tous les seuils vivent ici et nulle part ailleurs. Toute modification est datee
en commentaire : c'est ce qui empeche d'ajuster une regle apres avoir vu le
resultat qu'elle produit sur une societe que l'on aimerait garder.

Valides le 05/11/2026.
"""

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"
DOCS = RACINE / "docs"

# ------------------------------------------------------------- modele DCF ----
HORIZON = 5                  # annees de croissance explicite
G_INF = 0.02                 # croissance perpetuelle
BORNES_G1 = (-0.50, 1.00)    # intervalle de recherche de la croissance implicite

TAUX_SANS_RISQUE = 0.0360    # Bund 10 ans
PRIME_RISQUE_ACTIONS = 0.0500
SPREAD_CREDIT = 0.0140
CHOC_WACC = 0.0050           # +/- 50 pb pour le test de robustesse
SEUIL_DISPERSION = 0.40      # au-dela, le modele n'est plus discriminant

MARGE_VETO_RELATIVE = 0.50   # seuil = CAGR + max(50 % x |CAGR| ; 1,5 pt)
MARGE_VETO_ABSOLUE = 0.015
PLANCHER_SEUIL_VETO = G_INF  # un titre ne sort jamais pour une croissance
                             # implicite inferieure a la croissance perpetuelle
FENETRE_MIN_CAGR = 5         # en dessous, repli sur la mediane du secteur

# --------------------------------------------------------------- classement ---
POIDS_RENTABILITE = 0.50
POIDS_VALORISATION = 0.50
PLANCHER_RENTABILITE = 0.40  # percentile minimal, correction du professeur
PLANCHER_VALORISATION = 0.30
TAILLE_LISTE_SUIVI = 60

# Book-to-market plausible. Ajoute le 06/11/2026, apres Compass Group,
# InterContinental et Metlen : une cotation en livres (ou en euros) traitee
# comme des pence divise le cours par 100 et multiplie le B/M par 100, et le
# titre remonte en tete du classement. Une erreur d'unite deplace le B/M de deux
# ordres de grandeur, ce qui le sort de toute plage economique :
#   - au-dessus de 3, le marche valoriserait une societe non financiere a moins
#     d'un tiers de ses fonds propres. Cela n'arrive qu'en detresse, et une
#     detresse se verifie a la main avant d'entrer en liste de suivi ;
#   - en dessous de 0,01, il la valoriserait a plus de cent fois ses fonds
#     propres. Les plus chers de l'univers (Rolls-Royce, ASML, RELX) sont entre
#     0,025 et 0,045.
# Un titre hors plage n'a ni rang ni place en liste de suivi, et le journal le
# nomme. Les fonds propres negatifs (InterContinental) ne sont pas concernes :
# ils sont reels, et le classement les met deja en queue.
BM_PLAUSIBLE = (0.01, 3.0)
# Exceptions verifiees a la main : Ticker -> "date : source de la verification".
# Un titre n'y entre que si son B/M hors plage a ete confirme (cours ET fonds
# propres), jamais pour le garder dans le classement.
BM_VERIFIES: dict[str, str] = {}

# ------------------------------------------------- seuils de surveillance -----
# Deux niveaux par axe. Le premier met le titre sous surveillance, le second
# declenche la procedure de sortie. Rien n'est automatique : la plateforme
# signale, le comite decide, Jad passe les ordres.
RANG_SURVEILLANCE = 75
RANG_SORTIE = 100

MARGE_DCF_SURVEILLANCE = -0.015   # marge (g1 - seuil) entre -1,5 pt et 0
MARGE_DCF_SORTIE = 0.0
CLOTURES_CONFIRMATION = 5         # un franchissement doit tenir 5 clotures

# Degradation de la rentabilite. Deux niveaux, comme partout ailleurs.
# Corrige le 05/11/2026 : la regle d'origine sortait un titre des que le GP/A
# ajuste passait sous zero, sans surveillance ni confirmation. Teleperformance
# en est sortie pour 43 points de base sous la mediane de son secteur, alors
# que son rang etait 21 et que son DCF lui laissait 34 points de marge. Or
# cette mediane bouge des qu'un titre entre ou sort de l'univers : on vendait
# sur le deplacement d'une mediane, pas sur la societe.
DEGRADATION_SURVEILLANCE = 0.0    # GP/A ajuste sous la mediane du secteur
DEGRADATION_SORTIE = -0.10        # ... et 10 % en dessous de cette mediane

# Pas de stop-loss en absolu : une baisse ameliore le
# book-to-market, donc un stop absolu vendrait systematiquement les titres les
# moins chers du portefeuille, exactement l'inverse de la philosophie.
# On mesure donc le decrochage RELATIF a l'indice.
DECROCHAGE_REEXAMEN = -0.20       # -20 % vs STOXX 600 : reexamen obligatoire
DECROCHAGE_SORTIE = -0.35         # -35 % vs STOXX 600 : sortie sans discussion

# ------------------------------------------------------------ remplacants ----
# On ne sort jamais un titre sans remplacant eligible identifie.
REMPLACANT_RANG_MAX = TAILLE_LISTE_SUIVI
REMPLACANT_VERDICTS = ("A", "B")  # pas de C : on ne remplace pas un titre
                                  # marginal par un autre titre marginal
PART_MAX_VOLUME = 0.05            # notre ligne sous 5 % du volume quotidien

# ---------------------------------------------------- budget de transactions --
CAPITAL_INITIAL = 1_000_000       # euros, au 02/11/2026
BUDGET_TOTAL = 400
BUDGET_ACTIONS = 300              # 150 echanges possibles
BUDGET_ALLOCATION = 50            # mouvements de bandes macro sur les ETF
BUDGET_RESERVE = 20               # erreurs et corrections
# Cout de construction : 26 lignes actions + 1 part test de CBE3, exclu du
# calcul de rythme (voir signaux.budget). Fige le 06/11/2026 : il etait deduit
# du nombre de lignes de positions.csv, ce qui ne tient plus des que les
# positions viennent de l'export StockTrak (ETF compris, lignes qui changent).
# Les transactions consommees vivent dans data/compte.csv.
TRANSACTIONS_CONSTRUCTION = 27
DATE_LANCEMENT = "2026-11-02"
DATE_CLOTURE = "2027-03-31"

# Dates de comite, fixees a l'avance le 05/11/2026. Une date choisie apres
# avoir vu les cours n'est plus une regle, c'est un arbitrage.
# Trois semaines d'ecart, le troisieme avance pour eviter Noel, et rien dans
# les quinze derniers jours avant la cloture.
COMITES = [
    "2026-11-13",   # revision complete sur donnees fraiches
    "2026-12-04",
    "2026-12-18",
    "2027-01-08",
    "2027-01-29",
    "2027-02-19",
    "2027-03-12",
]
# Pas de plafond fixe par comite : l'enveloppe est le budget actions restant
# divise par le nombre de comites restants. Au lancement cela donne environ
# 42 transactions, soit 21 echanges. Ce n'est pas un objectif, c'est un
# maximum : on ne change pas vingt titres pour le plaisir de les changer.

# ------------------------------------------------------------- portefeuille --
LIGNE_MIN = 0.015
LIGNE_CIBLE = 0.04
LIGNE_PLAFOND = 0.06
ECART_SECTEUR_MAX = 0.10          # +/- 10 points vs indice
ECART_PAYS_MAX = 0.15

# ---------------------------------------------------------------- benchmark --
BENCHMARK = "^STOXX"              # STOXX Europe 600 (indice de prix)
BENCHMARK_NOM = "STOXX Europe 600"
# L'indice officiel de la note est le SXXR (net return, en euros). Yahoo ne
# sert que l'indice de prix ^STOXX : on l'utilise pour la comparaison
# quotidienne et la performance officielle sera recalee sur le SXXR au
# reporting. L'ecart est le rendement des dividendes, identique des deux cotes
# sur un ecart relatif.

# ------------------------------------------------------------- collecte ------
# Les cours bougent tous les jours. Les donnees comptables ne bougent que quand
# une societe publie : les retelecharger quotidiennement est du gaspillage, et
# surtout Yahoo revise ses chiffres en silence, ce qui ferait bouger le
# classement sans que personne sache pourquoi.
JOUR_FONDAMENTAUX = 5             # 0 = lundi ... 5 = samedi
# JPY, HKD, KRW, CNY ajoutees le 14/11/2026 avec l'univers mondial (les
# H-shares de Hong Kong publient le plus souvent en renminbi).
DEVISES = ("GBP", "SEK", "DKK", "CHF", "NOK", "USD", "PLN",
           "JPY", "HKD", "KRW", "CNY")
# Hors univers du fonds, les ~1 300 titres mondiaux ont leurs comptes
# rafraichis par tranche, un cinquieme chaque jour ouvre : 1 300 appels le
# meme jour depuis un serveur GitHub, c'est la coupure du 5 novembre en pire.
# L'univers du fonds garde son rafraichissement du samedi, inchange.
TRANCHES_FONDAMENTAUX = 5
# Titres nouveaux dans l'univers, sans aucun compte : lus au plus 300 par
# passage, pour que l'amorcage d'un indice entier ne fasse pas couper Yahoo.
AMORCAGE_MAX = 300

# ------------------------------------------------- univers et contraintes ----
# Ajoute le 14/11/2026. L'univers couvre cinq indices ; le fonds n'en voit
# qu'un sous-ensemble, defini par deux contraintes que chaque portefeuille
# active ou non. Percentiles, medianes sectorielles et rangs sont calcules A
# L'INTERIEUR de l'univers filtre : avec les deux contraintes, le fonds
# retrouve exactement son classement d'avant l'extension.
CONTRAINTES = {
    "europe": "Region Europe uniquement",
    "stocktrak": "Disponible et verifie dans StockTrak",
}
CONTRAINTES_POLARIS = ("europe", "stocktrak")
# Indices de comparaison proposes pour un portefeuille personnel :
# symbole Yahoo -> (nom, devise). La performance est toujours mesuree en euros.
INDICES = {
    "URTH": ("MSCI World (ETF iShares URTH)", "USD"),
    "^STOXX": ("STOXX Europe 600", "EUR"),
    "^GSPC": ("S&P 500", "USD"),
    "^N225": ("Nikkei 225", "JPY"),
    "^HSCE": ("Hang Seng China Enterprises", "HKD"),
    "^KS200": ("KOSPI 200", "KRW"),
}

# Taux sans risque 10 ans par devise de cotation, pour le DCF hors Europe.
# Le WACC sectoriel est construit sur le Bund ; pour une societe cotee dans
# une autre zone monetaire, on le decale de l'ecart de taux sans risque
# (WACC local = WACC secteur + rf local - rf Bund), pour que flux et taux
# d'actualisation soient dans la meme monnaie. Les devises europeennes ne sont
# PAS decalees : c'est la convention du fonds depuis septembre, la changer
# changerait ses verdicts.
# USD et HKD sont relus chaque jour sur Yahoo (^TNX, le HKD etant arrime au
# dollar) : les valeurs ci-dessous ne servent alors que de repli.
# JPY et KRW : Yahoo ne les sert pas. A VALIDER PAR JAD, niveaux approximatifs
# au 14/11/2026, a recaler sur les rendements du jour avant toute decision.
TAUX_SANS_RISQUE_DEVISE = {
    "USD": 0.0430,   # Treasury 10 ans (repli si ^TNX indisponible)
    "JPY": 0.0150,   # JGB 10 ans
    "HKD": 0.0430,   # arrime au dollar (repli)
    "KRW": 0.0290,   # KTB 10 ans
}

# ---------------------------- lignes fantomes --------------------------------
# Decouvert le 05/11/2026 : StockTrak expose des lignes cotees mais jamais
# traitees (HIGH a Londres, Adidas en francs). Une cotation sans volume et sans
# amplitude n'est pas negociable, quel que soit le prix affiche.
VOLUME_MIN_JOUR = 1               # volume du jour strictement positif

# --------------------------------------------- obligations IG, horizon -------
# Score FINAL HORIZON du classeur obligataire valide le 05/11/2026, reproduit
# a l'identique (data/obligations_ig.csv porte les notes du classeur).
# Score /100 = credit 25 + risque 25 + valorisation 25 + diversification 15
#              + horizon et structure 10.
OBLIG_DATE_DONNEES = "2026-11-05"  # date des rendements du classeur
# Date de liquidation retenue par le classeur. A noter : la negociation se
# clot le 31/03/2027 (DATE_CLOTURE) ; le classeur porte l'horizon au 15/04.
# Garde tel quel pour reproduire le classeur valide.
OBLIG_LIQUIDATION = "2027-04-15"
OBLIG_BENCH_YTM = 0.0393          # indice IG de reference
OBLIG_BENCH_DURATION = 4.4
# Chocs en points de base : (Bund, spread de credit).
OBLIG_SCENARIOS = {"central": (0, 0), "favorable": (-25, -15), "stress": (50, 50)}
