# -*- coding: utf-8 -*-
"""
Classement Novy-Marx.

Deux jambes, moitie-moitie. La rentabilite brute rapportee a l'actif, ajustee
de la mediane de son secteur GICS, et le book-to-market. Novy-Marx (2013)
montre que les deux sont negativement correlees : leur combinaison a une
volatilite plus faible que chacune des jambes prise isolement.

Un filtre classe, il n'exclut pas. Les planchers, eux, excluent : un titre
doit etre au moins au 40e percentile de rentabilite et au 30e de valorisation.
C'est la correction demandee par le professeur, et c'est ce qui empeche un
excellent rang sur une jambe de racheter un rang catastrophique sur l'autre.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg
from .journal import note


def percentile(serie: pd.Series) -> pd.Series:
    """Rang de centile, 1 = le meilleur."""
    valides = serie.notna().sum()
    if valides < 2:
        return pd.Series(np.nan, index=serie.index)
    return serie.rank(pct=True, na_option="keep")


def classer(univers: pd.DataFrame, fonda: pd.DataFrame,
            cours: pd.DataFrame, taux: dict[str, float],
            bloques: set[str] | None = None) -> pd.DataFrame:
    """Construit le classement du jour.

    `fonda` porte les comptes en devise de publication, `cours` le prix du jour
    en devise de cotation. Les deux sont ramenes en euros avant tout calcul :
    c'est l'erreur qui nous avait fait sortir toutes les britanniques en
    septembre, parce que Londres cote en pence.
    """
    df = univers.merge(fonda, on="Ticker", how="left") \
                .merge(cours, on="Ticker", how="left", suffixes=("", "_c"))

    def en_euros(colonne, devise_col):
        d = df[devise_col].fillna("EUR").map(lambda x: taux.get(x, np.nan))
        return df[colonne] / d

    df["capitalisation"] = en_euros("cours", "devise") * df["actions_m"]
    for c in ["ca", "cogs", "profit_brut", "actif", "fonds_propres"]:
        if c in df.columns:
            df[c + "_eur"] = en_euros(c, "devise_etats") if "devise_etats" in df.columns else df[c]

    pb = df.get("profit_brut_eur", df.get("profit_brut"))
    df["profit_brut_retenu"] = pb.fillna(df.get("ca_eur", df.get("ca")) -
                                         df.get("cogs_eur", df.get("cogs")))
    df["GP/A"] = df["profit_brut_retenu"] / df.get("actif_eur", df.get("actif"))
    df["B/M"] = df.get("fonds_propres_eur", df.get("fonds_propres")) / df["capitalisation"]

    mediane = df.groupby("Secteur")["GP/A"].transform("median")
    df["mediane_secteur"] = mediane
    df["GP/A ajuste"] = df["GP/A"] - mediane

    # Garde-fou sur les unites. Un B/M hors de toute plage economique est le
    # symptome d'un cours dans la mauvaise unite (Compass Group, InterContinental,
    # Metlen) ou de comptes mal collectes. Le titre est retire du calcul des
    # centiles et du rang AVANT le classement : sinon il prend la premiere place
    # et decale tous les autres. Le B/M brut reste visible pour le diagnostic.
    bas, haut = cfg.BM_PLAUSIBLE
    bm = df["B/M"]
    df["bm_implausible"] = (bm.notna() & (bm > 0) & ((bm < bas) | (bm > haut))
                            & ~df["Ticker"].isin(cfg.BM_VERIFIES))
    for t, s, v in df.loc[df["bm_implausible"], ["Ticker", "Societe", "B/M"]].itertuples(index=False):
        note(f"ATTENTION book-to-market implausible {v:.3g} pour {t} ({s}) : "
             f"cours ou fonds propres dans la mauvaise unite ? "
             f"Retire du classement et de la liste de suivi")

    df["rang_rentabilite"] = percentile(df["GP/A ajuste"])
    df["rang_valorisation"] = percentile(bm.where(~df["bm_implausible"]))
    df["rang_combine"] = (df["rang_rentabilite"] * cfg.POIDS_RENTABILITE
                          + df["rang_valorisation"] * cfg.POIDS_VALORISATION)

    df["plancher_ok"] = ((df["rang_rentabilite"] >= cfg.PLANCHER_RENTABILITE)
                         & (df["rang_valorisation"] >= cfg.PLANCHER_VALORISATION))

    # Negociabilite : deux tests qui ne detectent pas la meme chose.
    #
    # 1. Le test de LIQUIDITE, automatique. Une cotation sans volume et sans
    #    amplitude du jour n'est pas traitee sur le marche reel : c'est le cas
    #    des lignes secondaires fantomes (Adidas en francs suisses) et des
    #    cotations gelees. Yahoo le dit, donc la machine peut le verifier
    #    chaque soir.
    #
    # 2. Le test de DISPONIBILITE sur StockTrak, manuel. Yahoo ne sait pas si
    #    StockTrak porte le titre, ni a quel prix il l'affiche : l'ETF HIGH se
    #    negocie normalement a Londres et serait passe au test 1, alors que
    #    StockTrak le cotait a un centieme de sa valeur. Aucune API ne permet
    #    de le verifier : la colonne verifie_stocktrak porte la date du dernier
    #    controle fait a la main dans le navigateur, et un titre jamais
    #    verifie n'est pas proposable.
    df["liquide"] = df.get("negociable", True).fillna(False)
    df["verifie"] = df.get("verifie_stocktrak", pd.Series(dtype=object)).notna()
    # 3. Les blocages manuels (data/blocages.csv) : StockTrak ne permet pas de
    #    traiter le titre au prix affiche. Appliques ici, avant le rang, depuis
    #    le 06/11/2026 : appliques apres, Compass Group bloque gardait le rang 1
    #    et decalait d'une place tout le reste du classement.
    df["bloque"] = df["Ticker"].isin(bloques or set())
    df["negociable"] = df["liquide"] & df["verifie"] & ~df["bloque"]

    df = df.sort_values("rang_combine", ascending=False).reset_index(drop=True)
    eligibles = df["plancher_ok"] & df["negociable"] & ~df["bm_implausible"]
    df["rang"] = np.nan
    df.loc[eligibles, "rang"] = range(1, int(eligibles.sum()) + 1)
    df["liste_suivi"] = df["rang"] <= cfg.TAILLE_LISTE_SUIVI
    return df
