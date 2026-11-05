# -*- coding: utf-8 -*-
"""
DCF inverse.

On ne cherche pas la valeur d'une action : on cherche ce que le cours suppose.
Le modele part de la valeur d'entreprise observee et resout la seule inconnue
laissee libre, la croissance du flux de tresorerie disponible pendant la phase
explicite. Cette croissance implicite g1 est ensuite comparee a celle que la
societe a reellement realisee. Si le marche demande nettement plus que ce que
l'entreprise a su faire, le titre sort.

Ici, g1 est resolue par brentq a chaque mise a jour : c'est ce qui remplace la
Valeur cible d'Excel, qu'il fallait relancer onglet par onglet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from . import config as cfg


def _z(x) -> float:
    """Une rubrique de bilan absente vaut zero, pas 'inconnu'.

    Sans ce passage par zero, un champ vide d'interets minoritaires
    contaminerait toute la chaine et le titre ressortirait non calculable pour
    une ligne sans enjeu.
    """
    if x is None:
        return 0.0
    try:
        return 0.0 if np.isnan(float(x)) else float(x)
    except (TypeError, ValueError):
        return 0.0


def fcff_normatif(l: pd.Series) -> float:
    """Moyenne des FCFF des trois derniers exercices.

    Une seule annee suffit a faire mentir le modele : un exercice ou le capex
    tombe, ou le besoin en fonds de roulement se denoue, produit un flux qui ne
    se repetera pas.
    """
    t = _z(l.get("taux_impot"))
    flux = []
    for s in ("n2", "n1", "n"):
        ebit = l.get(f"ebit_{s}")
        if ebit is None or (isinstance(ebit, float) and np.isnan(ebit)):
            return np.nan
        flux.append(ebit * (1 - t) + _z(l.get(f"da_{s}"))
                    - abs(_z(l.get(f"capex_{s}"))) - _z(l.get(f"dbfr_{s}")))
    return float(np.mean(flux))


def valeur_entreprise(fcff0, g1, wacc, horizon=cfg.HORIZON, g_inf=cfg.G_INF):
    """Modele a deux phases : horizon annees a g1, puis g_inf a l'infini."""
    if wacc <= g_inf:
        return np.nan
    ve, flux = 0.0, fcff0
    for annee in range(1, horizon + 1):
        flux *= (1 + g1)
        ve += flux / (1 + wacc) ** annee
    ve += flux * (1 + g_inf) / (wacc - g_inf) / (1 + wacc) ** horizon
    return ve


def ve_marche(capitalisation, dette_nette, minoritaires, mises_en_equivalence):
    """VE = capitalisation + dette nette + minoritaires - mises en equivalence.

    Les minoritaires s'ajoutent parce que le FCFF est genere par la totalite du
    perimetre consolide. Les mises en equivalence se retranchent parce que leur
    resultat ne passe pas par l'EBIT : les laisser dedans serait payer deux fois.
    """
    return (_z(capitalisation) + _z(dette_nette) + _z(minoritaires)
            - _z(mises_en_equivalence))


def croissance_implicite(ve_cible, fcff0, wacc, bornes=cfg.BORNES_G1):
    """Resout g1 tel que VE(modele) = VE(marche).

    La VE est strictement croissante en g1, donc la racine est unique et brentq
    la trouve sans point de depart. Un flux normatif negatif rend l'equation
    sans solution economique : on renvoie NaN plutot qu'un chiffre illisible.
    """
    if not np.isfinite(fcff0) or fcff0 <= 0 or not np.isfinite(ve_cible):
        return np.nan

    def ecart(g):
        return valeur_entreprise(fcff0, g, wacc) - ve_cible

    bas, haut = bornes
    try:
        if ecart(bas) > 0 or ecart(haut) < 0:
            return np.nan
        return float(brentq(ecart, bas, haut, xtol=1e-6))
    except (ValueError, ZeroDivisionError):
        return np.nan


def cagr(v0, v1, annees):
    if annees <= 0 or v0 is None or v0 <= 0:
        return np.nan
    return (v1 / v0) ** (1 / annees) - 1


def seuil_veto(cagr_retenu):
    """seuil = max(CAGR + max(50 % x |CAGR| ; 1,5 pt) ; croissance perpetuelle).

    La part relative laisse de la place aux societes volatiles, la part absolue
    evite qu'une societe a croissance nulle soit vetee pour dix points de base.
    Le plancher protege celles dont le CAGR est negatif pour cause de cessions :
    sans lui, SSE, Solvay ou Telefonica seraient vetees quel que soit leur prix.
    """
    if not np.isfinite(cagr_retenu):
        return np.nan
    marge = max(cfg.MARGE_VETO_RELATIVE * abs(cagr_retenu), cfg.MARGE_VETO_ABSOLUE)
    return max(cagr_retenu + marge, cfg.PLANCHER_SEUIL_VETO)


def dispersion(fcff0, g1, wacc, dette, minos, mee):
    """Ecart relatif de la valeur des fonds propres pour un WACC +/- 50 pb.

    Au-dela de 40 %, la valeur depend plus du taux d'actualisation que de
    l'entreprise : on s'abstient plutot que de prononcer un verdict
    indefendable.
    """
    if not np.isfinite(g1):
        return np.nan
    v = []
    for w in (wacc - cfg.CHOC_WACC, wacc, wacc + cfg.CHOC_WACC):
        ve = valeur_entreprise(fcff0, g1, w)
        v.append(ve - _z(dette) - _z(minos) + _z(mee))
    v = np.array(v, dtype=float)
    if not np.all(np.isfinite(v)) or abs(v[1]) < 1e-9:
        return np.nan
    return float((v.max() - v.min()) / abs(v[1]))


VERDICTS = {
    "A": "A - Le marche n'attend aucune croissance",
    "B": "B - Attente inferieure a l'historique realise",
    "C": "C - Attente superieure a l'historique, dans la marge",
    "D": "D - VETO QUANTITATIF",
    "ABS": "ABSTENTION - modele non discriminant",
    "FN": "FLUX NEGATIF - modele inapplicable",
    "NC": "DONNEES INCOMPLETES",
}


def verdict(g1, cagr_retenu, seuil, disp, fcff0=None):
    """L'ordre des tests compte : on verifie d'abord que le modele tient,
    ensuite seulement ce qu'il dit."""
    if fcff0 is not None and np.isfinite(fcff0) and fcff0 <= 0:
        return VERDICTS["FN"]
    if not np.isfinite(g1):
        return VERDICTS["NC"]
    if np.isfinite(disp) and disp > cfg.SEUIL_DISPERSION:
        return VERDICTS["ABS"]
    if g1 <= cfg.G_INF:
        return VERDICTS["A"]
    if np.isfinite(cagr_retenu) and g1 <= cagr_retenu:
        return VERDICTS["B"]
    if np.isfinite(seuil) and g1 <= seuil:
        return VERDICTS["C"]
    return VERDICTS["D"]


def evaluer(classement: pd.DataFrame, dcf_in: pd.DataFrame, hist_ca: pd.DataFrame,
            wacc: pd.DataFrame) -> pd.DataFrame:
    """Applique le DCF inverse a toute la liste de suivi."""
    w = dict(zip(wacc["Secteur"], wacc["WACC"]))
    df = classement.merge(dcf_in, on="Ticker", how="left") \
                   .merge(hist_ca, on="Ticker", how="left")
    df["wacc"] = df["Secteur"].map(w)
    df["fcff"] = df.apply(fcff_normatif, axis=1)
    df["ve_marche"] = [ve_marche(r.capitalisation, r.dette_nette,
                                 r.minoritaires, r.mises_en_equivalence)
                       for r in df.itertuples()]
    df["g1"] = [croissance_implicite(r.ve_marche, r.fcff, r.wacc)
                for r in df.itertuples()]

    df["fenetre"] = (df["an_dernier"] - df["an_base"]).fillna(0)
    df["cagr_brut"] = [cagr(r.ca_base, r.ca_dernier, r.fenetre) for r in df.itertuples()]
    fiable = df["fenetre"] >= cfg.FENETRE_MIN_CAGR
    med = df[fiable].groupby("Secteur")["cagr_brut"].median()
    med_globale = df.loc[fiable, "cagr_brut"].median()
    df["cagr_retenu"] = [
        r.cagr_brut if (r.fenetre >= cfg.FENETRE_MIN_CAGR and np.isfinite(r.cagr_brut))
        else med.get(r.Secteur, med_globale) for r in df.itertuples()]
    df["origine_cagr"] = np.where(
        (df["fenetre"] >= cfg.FENETRE_MIN_CAGR) & df["cagr_brut"].notna(),
        "historique " + df["fenetre"].astype("Int64").astype(str) + " ans",
        "repli : mediane du secteur")

    df["seuil"] = df["cagr_retenu"].apply(seuil_veto)
    df["dispersion"] = [dispersion(r.fcff, r.g1, r.wacc, r.dette_nette,
                                   r.minoritaires, r.mises_en_equivalence)
                        for r in df.itertuples()]
    df["verdict"] = [verdict(r.g1, r.cagr_retenu, r.seuil, r.dispersion, r.fcff)
                     for r in df.itertuples()]
    df["marge"] = df["g1"] - df["seuil"]
    return df
