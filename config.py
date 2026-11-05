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
BUDGET_TOTAL = 400
BUDGET_ACTIONS = 300              # 150 echanges possibles
BUDGET_ALLOCATION = 50            # mouvements de bandes macro sur les ETF
BUDGET_RESERVE = 20               # erreurs et corrections
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
DEVISES = ("GBP", "SEK", "DKK", "CHF", "NOK", "USD", "PLN")

# ---------------------------- lignes fantomes --------------------------------
# Decouvert le 05/11/2026 : StockTrak expose des lignes cotees mais jamais
# traitees (HIGH a Londres, Adidas en francs). Une cotation sans volume et sans
# amplitude n'est pas negociable, quel que soit le prix affiche.
VOLUME_MIN_JOUR = 1               # volume du jour strictement positif
