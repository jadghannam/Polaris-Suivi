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
def remplacants_eligibles(suivi: pd.DataFrame, detenus: set[str],
                          vetos: set[str] = frozenset()) -> pd.DataFrame:
    """Titres prets a entrer, classes du meilleur au moins bon.

    Verdict A ou B exige, pas C : on ne remplace pas un titre marginal par un
    autre titre marginal. Et la ligne doit rester sous 5 % du volume quotidien,
    sinon on ne saura pas la construire ni la defaire.

    Aucun veto qualitatif (data/vetos.csv). Ajoute le 14/11/2026 : la regle
    etait ecrite dans le README mais pas dans le code, et la page proposait
    AkzoNobel, ecartee le 23/10 pour sa fusion avec Axalta, en remplacement de
    chaque sortie.
    """
    r = suivi[
        (~suivi["Ticker"].isin(detenus))
        & (~suivi["Ticker"].isin(vetos))
        & (suivi["rang"] <= cfg.REMPLACANT_RANG_MAX)
        & (suivi["plancher_ok"])
        & (suivi["negociable"])
        # Le code du verdict est ce qui precede " - ", compare en entier.
        # Corrige le 06/11/2026 : le test portait sur la premiere lettre, et
        # "ABSTENTION - modele non discriminant" passait pour un verdict A.
        & (suivi["verdict"].fillna("").str.split(" - ").str[0].str.strip()
           .isin(cfg.REMPLACANT_VERDICTS))
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


# ------------------------------------------------------- ordre d'achat ----
def ordre_achat(cours, devise: str, montant_eur: float, taux: dict) -> dict:
    """Quantite entiere a acheter pour atteindre un montant cible en euros.

    Ajoute le 19/11/2026. La cible d'une ligne est la valeur ACTUELLE de la
    poche actions divisee par le nombre de lignes (1/N) : elle suit la poche,
    pas les 27 000 EUR du lancement. On arrondit a l'action inferieure, parce
    que StockTrak ne traite pas de fractions et qu'un arrondi superieur
    depasserait la cible.
    """
    fx = taux.get(devise or "EUR", np.nan)
    if cours is None or not np.isfinite(cours) or cours <= 0 or not np.isfinite(fx) \
            or not np.isfinite(montant_eur):
        return {"quantite": None, "montant_eur": None, "cible_eur": montant_eur}
    q = int(np.floor(montant_eur * fx / cours))
    return {"quantite": q, "montant_eur": q * cours / fx, "cible_eur": montant_eur,
            "cours": float(cours), "devise": devise}


def plan_echanges(sorties: list[dict], candidats: pd.DataFrame, poche_eur: float,
                 nb_lignes: int, liquidites_eur: float, taux: dict,
                 ecarts_secteur: dict[str, float], meme_region: bool = False) -> list[dict]:
    """Montants des echanges du jour, sortie par sortie (19/11/2026).

    `sorties` : lignes en zone de sortie, deja dans l'ordre de priorite, avec
    Ticker, Secteur, Region, quantite, valeur_eur. Chaque sortie recoit le
    meilleur remplacant encore libre (deux sorties ne prennent jamais le meme),
    puis le montant :
        cible  = (poche - ligne vendue) / (N - 1), moyenne des lignes restantes ;
        budget = produit de la vente + liquidites disponibles (hors reserve) ;
        achat  = cible si budget >= cible, sinon budget ;
        pas de remplacement si achat < SEUIL_REMPLACEMENT x cible.
    Les sorties sont traitees l'une apres l'autre : la poche et les
    liquidites evoluent avec chaque echange.
    """
    poche, dispo, pris, plan = float(poche_eur), max(float(liquidites_eur), 0.0), set(), []
    for s in sorties:
        libres = candidats[~candidats["Ticker"].isin(pris)]
        if meme_region and "Region" in libres.columns:
            libres = libres[libres["Region"] == s.get("Region")]
        m = meilleur_remplacant(libres, s.get("Secteur"), ecarts_secteur)
        vente = float(s.get("valeur_eur") or 0.0)
        # Poids cible de la ligne : 1/N par defaut, ou celui de sa construction
        # (repartition ACWI). L'achat A doit peser w dans la poche d'apres :
        # A = w x (poche - vente + A), soit A = w x (poche - vente) / (1 - w).
        # Pour w = 1/N, c'est la moyenne des N - 1 lignes restantes.
        w = s.get("poids_cible")
        w = w if w is not None and 0 < w < 1 else (1 / nb_lignes if nb_lignes > 1 else 1.0)
        cible = w * (poche - vente) / (1 - w) if w < 1 else vente
        e = {"Ticker": s["Ticker"], "vente": {"quantite": s.get("quantite"), "valeur_eur": vente},
             "cible_eur": cible, "liquidites_avant_eur": dispo, "remplacant": None}
        if m is None:
            e["decision"] = "aucun remplacant eligible : la ligne n'est pas vendue (pas de sortie sans remplacant)"
            e["liquidites_apres_eur"] = dispo
            plan.append(e)
            continue
        budget = vente + dispo
        montant = min(cible, budget)
        a = ordre_achat(m["cours"], m["devise"], montant, taux)
        reel = a.get("montant_eur") or 0.0
        if reel < cfg.SEUIL_REMPLACEMENT * cible:
            e["decision"] = (f"pas de remplacement : {reel:,.0f} EUR achetables, sous "
                             f"{cfg.SEUIL_REMPLACEMENT:.0%} de la cible ; la vente reste en liquidites")
            e["remplacant_envisage"] = m["Ticker"]
            dispo += vente
            poche -= vente
        else:
            pris.add(m["Ticker"])
            dispo = budget - reel
            poche = poche - vente + reel
            e["remplacant"] = {"Ticker": m["Ticker"], "Societe": m["Societe"],
                               "Secteur": m["Secteur"], "rang": m["rang"], "verdict": m["verdict"],
                               "marge": m["marge"], "achat": a}
            e["decision"] = ("achat a la cible" if montant >= cible
                             else "achat au maximum des liquidites disponibles")
            e["solde_liquidites_eur"] = vente - reel
        e["liquidites_apres_eur"] = dispo
        plan.append(e)
    return plan


def periode(compte: pd.DataFrame, transactions_initiales: int,
            aujourdhui: dt.date | None = None) -> dict:
    """Periode entre deux comites et son enveloppe de transactions.

    `compte` : data/compte.csv (date, transactions_consommees). L'enveloppe est
    figee a l'ouverture de la periode, avec les transactions faites AVANT le
    jour du comite : celles du comite comptent dans la periode qu'il ouvre.
    """
    j = aujourdhui or dt.date.today()
    dates = [dt.date.fromisoformat(d) for d in cfg.COMITES]
    passes = [d for d in dates if d <= j]
    suivant = next((d for d in dates if d > j), None)
    debut = passes[-1] if passes else dt.date.fromisoformat(cfg.DATE_LANCEMENT)
    c = compte.copy()
    c["date"] = pd.to_datetime(c["date"]).dt.date
    c["t"] = pd.to_numeric(c["transactions_consommees"], errors="coerce")
    c = c.dropna(subset=["t"])
    avant = c[c["date"] < debut]["t"]
    faites_avant = int(avant.iloc[-1]) if len(avant) else transactions_initiales
    jusqu = c[c["date"] <= j]["t"]
    faites = int(jusqu.iloc[-1]) if len(jusqu) else transactions_initiales
    restants = len([d for d in dates if d >= debut]) if passes else len(dates)
    rotation_avant = max(faites_avant - transactions_initiales, 0)
    enveloppe = int((cfg.BUDGET_ACTIONS - rotation_avant) / restants) if restants else 0
    utilisees = max(faites - max(faites_avant, transactions_initiales), 0)
    return {"debut": debut.isoformat(), "comite_ouvrant": bool(passes),
            "prochain_comite": suivant.isoformat() if suivant else None,
            "enveloppe": enveloppe, "utilisees": utilisees,
            "restantes": max(enveloppe - utilisees, 0)}


def statut_execution(plan: list[dict], confirmees: set[str], per: dict) -> None:
    """Ajoute a chaque echange du plan : maintenant, ou au prochain comite.

    Dans l'ordre du plan (priorite), chaque echange executable consomme deux
    transactions de l'enveloppe restante de la periode."""
    reste = per["restantes"]
    comite = per["prochain_comite"]
    for e in plan:
        if not e.get("remplacant"):
            e["execution"] = {"statut": "aucun", "motif": e.get("decision", ""), "comite": comite}
        elif e["Ticker"] not in confirmees:
            e["execution"] = {"statut": "comite", "comite": comite,
                              "motif": "sortie non confirmee : attendre les 5 clotures ou le comite"}
        elif not cfg.ECHANGES_ENTRE_COMITES:
            e["execution"] = {"statut": "comite", "comite": comite,
                              "motif": "echanges reserves aux comites (config.py)"}
        elif reste < 2:
            e["execution"] = {"statut": "comite", "comite": comite,
                              "motif": f"enveloppe de la periode epuisee ({per['utilisees']} / {per['enveloppe']})"}
        else:
            reste -= 2
            e["execution"] = {"statut": "maintenant", "comite": comite,
                              "motif": f"sortie confirmee, remplacant disponible, {reste} transactions "
                                       f"restantes dans l'enveloppe apres l'echange"}


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
