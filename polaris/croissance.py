# -*- coding: utf-8 -*-
"""
Croissance historique du chiffre d'affaires, prolongee automatiquement.

Ajoute le 19/11/2026. data/historique_ca.csv porte, pour 60 titres, un CA de
depart (2015 en general) et un CA d'arrivee saisis a la main en septembre :
Yahoo ne donne que quatre exercices, il ne peut pas fournir dix ans. Le
fichier n'est jamais modifie. Ce module en tire, a chaque passage, une table
prolongee :

  - le POINT DE DEPART reste celui de septembre ;
  - le POINT D'ARRIVEE avance des que Yahoo publie un exercice plus recent :
    CAGR = (CA du dernier exercice / CA de depart)^(1 / annees) - 1.

Garde-fou : Yahoo donne aussi l'exercice d'arrivee de septembre. Si les deux
chiffres different de plus de 5 % (comptes retraites, changement de
perimetre, autre ligne de CA, autre unite), on ne prolonge PAS et le titre est
signale « a verifier » sur la page. Le fichier saisi est en milliards ou en
millions selon les lignes : l'unite est deduite de cette comparaison.

Sans historique saisi, le CAGR se calcule sur les exercices Yahoo accumules
dans data/etats_annuels.csv. Il n'est retenu par le DCF qu'a partir de cinq
ans de recul (FENETRE_MIN_CAGR) : en 2027 pour la plupart des titres.
"""

from __future__ import annotations

import pandas as pd

from .journal import note

TOLERANCE = 0.05


def _annee(cloture: str) -> int:
    return int(str(cloture)[:4])


def etendre(hist: pd.DataFrame, etats: pd.DataFrame | None) -> tuple[pd.DataFrame, list[dict]]:
    """(table prolongee au format de historique_ca.csv + origine_ca, a verifier)."""
    h = hist.copy()
    h["origine_ca"] = "saisi en septembre 2026"
    a_verifier = []
    if etats is None or etats.empty:
        return h, a_verifier
    e = etats.dropna(subset=["ca"]).copy()
    e = e[e["ca"] > 0]
    e["annee"] = e["cloture"].map(_annee)
    par = {t: g.sort_values("annee") for t, g in e.groupby("Ticker")}

    for i, r in h.iterrows():
        g = par.get(r["Ticker"])
        if g is None or pd.isna(r["ca_dernier"]) or pd.isna(r["an_dernier"]):
            continue
        dernier = g.iloc[-1]
        if int(dernier["annee"]) <= int(r["an_dernier"]):
            continue                                   # rien de plus recent
        commun = g[g["annee"] == int(r["an_dernier"])]
        if commun.empty:
            a_verifier.append({"Ticker": r["Ticker"], "motif":
                               f"exercice {int(r['an_dernier'])} absent chez Yahoo : pas de point de comparaison"})
            continue
        ratio = float(commun["ca"].iloc[0]) / float(r["ca_dernier"])
        unite = next((u for u in (1.0, 1000.0) if abs(ratio / u - 1) <= TOLERANCE), None)
        if unite is None:
            a_verifier.append({"Ticker": r["Ticker"], "motif":
                               f"CA {int(r['an_dernier'])} : Yahoo {commun['ca'].iloc[0]:,.0f} contre "
                               f"{r['ca_dernier']} saisi (ecart hors tolerance de 5 %)"})
            continue
        h.at[i, "ca_dernier"] = float(dernier["ca"]) / unite
        h.at[i, "an_dernier"] = int(dernier["annee"])
        h.at[i, "origine_ca"] = f"prolonge avec Yahoo jusqu'en {int(dernier['annee'])}"

    # Titres sans historique saisi : exercices Yahoo accumules.
    connus = set(h["Ticker"])
    auto = []
    for t, g in par.items():
        if t in connus or len(g) < 2:
            continue
        auto.append({"Ticker": t, "ca_base": float(g["ca"].iloc[0]), "an_base": int(g["annee"].iloc[0]),
                     "ca_dernier": float(g["ca"].iloc[-1]), "an_dernier": int(g["annee"].iloc[-1]),
                     "devise_ca": g["devise_etats"].iloc[-1], "remarque": "",
                     "origine_ca": f"Yahoo, {len(g)} exercices"})
    if auto:
        h = pd.concat([h, pd.DataFrame(auto)], ignore_index=True)
    prolonges = int(h["origine_ca"].str.startswith("prolonge").sum())
    note(f"croissance du CA : {prolonges} historiques prolonges avec Yahoo, "
         f"{len(a_verifier)} a verifier, {len(auto)} calcules sur les seuls exercices Yahoo")
    return h, a_verifier
