# -*- coding: utf-8 -*-
"""
Zones de surveillance, procedure de sortie, remplacants, budget.

Trois principes, poses une fois pour toutes :

1. Deux seuils par axe. Le premier met le titre sous surveillance, le second
   ouvre la procedure de sortie. Rien n'est automatique : la plateforme
   signale, le comite decide, les ordres sont passes a la main.

2. Un franchissement doit TENIR. Cinq clotures consecutives au-dela du seuil,
   sinon on ne bouge pas. Sans cette condition, un pic d'une seule journee
   declencherait une cession - Dassault aurait fait sortir un titre le
   2 novembre sur un mouvement qui s'est poursuivi, mais la regle doit tenir
   aussi les jours ou le mouvement se retourne.

3. On ne sort jamais un titre sans remplacant eligible identifie. Vendre sans
   savoir quoi acheter, c'est prendre une decision d'allocation en croyant
   prendre une decision de selection.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import config as cfg

SURVEILLANCE, SORTIE, OK = "surveillance", "sortie", "ok"


# ------------------------------------------------------------- zones ---------
def zone_rang(rang) -> str:
    if rang is None or not np.isfinite(rang):
        return SORTIE                       # sorti de l'univers eligible
    if rang > cfg.RANG_SORTIE:
        return SORTIE
    if rang > cfg.RANG_SURVEILLANCE:
        return SURVEILLANCE
    return OK


def zone_dcf(marge) -> str:
    if not np.isfinite(marge):
        return OK
    if marge > cfg.MARGE_DCF_SORTIE:
        return SORTIE
    if marge >= cfg.MARGE_DCF_SURVEILLANCE:
        return SURVEILLANCE
    return OK


def zone_decrochage(perf_relative) -> str:
    """Decrochage mesure CONTRE l'indice, jamais en absolu.

    Un stop-loss absolu vendrait systematiquement les titres dont le cours a
    baisse - donc ceux dont le book-to-market vient de s'ameliorer, donc ceux
    que la methode dit de garder. En relatif, un ecart de 20 points contre
    l'indice veut dire que le marche sait sur cette societe quelque chose que
    nos comptes ne disent pas encore.
    """
    if not np.isfinite(perf_relative):
        return OK
    if perf_relative <= cfg.DECROCHAGE_SORTIE:
        return SORTIE
    if perf_relative <= cfg.DECROCHAGE_REEXAMEN:
        return SURVEILLANCE
    return OK


def zone_degradation(gpa_ajuste, mediane_secteur) -> str:
    """La jambe Novy-Marx s'affaisse : c'est la raison meme de detenir le titre.

    Deux niveaux, comme sur les autres axes. Passer legerement sous la mediane
    de son secteur met le titre sous surveillance ; il ne sort que s'il
    s'enfonce nettement en dessous, et seulement apres confirmation. Un ecart
    de quelques points de base n'est pas un signal : la mediane elle-meme se
    deplace des qu'un titre entre ou sort de l'univers.
    """
    if gpa_ajuste is None or not np.isfinite(gpa_ajuste):
        return OK
    if gpa_ajuste >= cfg.DEGRADATION_SURVEILLANCE:
        return OK
    if mediane_secteur is None or not np.isfinite(mediane_secteur) or mediane_secteur <= 0:
        return SURVEILLANCE
    if gpa_ajuste <= cfg.DEGRADATION_SORTIE * mediane_secteur:
        return SORTIE
    return SURVEILLANCE


ORDRE = {OK: 0, SURVEILLANCE: 1, SORTIE: 2}


def zone_globale(zones: dict[str, str]) -> str:
    return max(zones.values(), key=lambda z: ORDRE[z])


# ------------------------------------------------------- persistance ---------
def compter_clotures(historique: pd.DataFrame, ticker: str, colonne: str,
                     valeur: str = SORTIE) -> int:
    """Nombre de clotures CONSECUTIVES, la plus recente en premier, pour
    lesquelles le titre etait dans l'etat demande."""
    h = historique[historique["Ticker"] == ticker].sort_values("date", ascending=False)
    n = 0
    for v in h[colonne]:
        if v == valeur:
            n += 1
        else:
            break
    return n


def sortie_confirmee(historique: pd.DataFrame, ticker: str, colonne: str) -> bool:
    return compter_clotures(historique, ticker, colonne) >= cfg.CLOTURES_CONFIRMATION


# ------------------------------------------------------- remplacants ---------
def remplacants_eligibles(suivi: pd.DataFrame, detenus: set[str]) -> pd.DataFrame:
    """Titres prets a entrer, classes du meilleur au moins bon.

    Verdict A ou B exige, pas C : on ne remplace pas un titre marginal par un
    autre titre marginal. Et la ligne doit rester sous 5 % du volume quotidien,
    sinon on ne saura pas la construire ni la defaire.
    """
    r = suivi[
        (~suivi["Ticker"].isin(detenus))
        & (suivi["rang"] <= cfg.REMPLACANT_RANG_MAX)
        & (suivi["plancher_ok"])
        & (suivi["negociable"])
        & (suivi["verdict"].str[0].isin(cfg.REMPLACANT_VERDICTS))
    ].copy()
    return r.sort_values("rang")


def meilleur_remplacant(candidats: pd.DataFrame, secteur_sortant: str,
                        ecarts_secteur: dict[str, float]) -> pd.Series | None:
    """A eligibilite egale, on prend celui qui REDUIT l'ecart sectoriel.

    Le portefeuille est deja tres au-dessus de l'indice sur l'industrie : tout
    echange qui en rajoute aggrave une contrainte deja franchie.
    """
    if candidats.empty:
        return None
    c = candidats.copy()
    # effet de l'echange sur l'ecart sectoriel : negatif = ameliore
    c["effet"] = c["Secteur"].map(lambda s: ecarts_secteur.get(s, 0.0)) \
        - ecarts_secteur.get(secteur_sortant, 0.0)
    c = c.sort_values(["effet", "rang"])
    return c.iloc[0]


# ---------------------------------------------------------- budget -----------
def budget(transactions_faites: int, transactions_initiales: int = 0,
           aujourdhui: dt.date | None = None) -> dict:
    """Suivi du rythme de consommation des 400 transactions.

    Ce n'est pas un plafond, c'est un indicateur : on veut savoir si on
    consomme plus vite que le temps ne passe, pas s'interdire d'agir.

    La construction initiale du portefeuille est exclue du calcul de rythme.
    C'est un cout d'entree paye une fois, pas de la rotation : l'y inclure
    afficherait un depassement permanent des le premier jour et l'indicateur
    ne voudrait plus rien dire.
    """
    j = aujourdhui or dt.date.today()
    debut = dt.date.fromisoformat(cfg.DATE_LANCEMENT)
    fin = dt.date.fromisoformat(cfg.DATE_CLOTURE)
    duree = (fin - debut).days
    ecoule = max((j - debut).days, 0)
    courantes = max(transactions_faites - transactions_initiales, 0)
    attendu = cfg.BUDGET_ACTIONS * ecoule / duree if duree else 0
    rythme = courantes / attendu if attendu > 0 else 0.0

    # Enveloppe par comite : ce qui reste du budget actions, reparti sur les
    # comites a venir. Elle se recalcule toute seule : si un comite consomme
    # peu, les suivants heritent de la difference.
    restants = [d for d in cfg.COMITES if dt.date.fromisoformat(d) >= j]
    budget_actions_restant = max(cfg.BUDGET_ACTIONS - courantes, 0)
    nb = len(restants)
    enveloppe = budget_actions_restant / nb if nb else 0
    return {
        "comites_restants": nb,
        "prochain_comite": restants[0] if restants else None,
        "budget_actions_restant": budget_actions_restant,
        "enveloppe_par_comite": round(enveloppe, 1),
        "echanges_max_par_comite": int(enveloppe // 2),
        "faites": transactions_faites,
        "initiales": transactions_initiales,
        "rotation": courantes,
        "restantes": cfg.BUDGET_TOTAL - transactions_faites,
        "attendu_a_ce_jour": round(attendu, 1),
        "rythme": round(rythme, 2),
        "etat": "vert" if rythme < 1.0 else ("orange" if rythme <= 1.2 else "rouge"),
        "echanges_possibles": (cfg.BUDGET_TOTAL - transactions_faites) // 2,
        "jours_restants": max((fin - j).days, 0),
    }
