# -*- coding: utf-8 -*-
"""
Scoring des obligations IG a l'horizon de liquidation du fonds.

Reprise du script scoring_ig_horizon.py, qui reproduit le classeur valide le
05/11/2026 a la decimale pres. Score /100 :

  credit 25 + risque 25           notes du classeur
  valorisation 25                 rang de l'alpha central (1 a 10)
                                  + rang de l'alpha en stress (1 a 10)
                                  + ecart de spread aux pairs / 3 (0 a 5)
  diversification 15              note du classeur
  horizon et structure 10         note de duration (3 a 5) + structure (0 a 5)

L'alpha est le rendement total approche a l'horizon moins celui de l'indice :
    TR = YTM x H - duration x (choc Bund + choc spread)
Approximation au premier ordre : ni convexite ni effet de roulement.

Ajouts par rapport au script :
  - une ligne incomplete est ecartee et nommee dans le journal, sans plantage ;
  - les obligations detenues (export StockTrak) sont rapprochees du classement
    par coupon et echeance, et celles absentes du classeur sont signalees.
"""

from __future__ import annotations

import datetime as dt
import re

import numpy as np
import pandas as pd

from . import config as cfg
from .journal import note

CHAMPS = ["ytm", "duration", "credit_25", "risk_25", "diversification_15",
          "structure_5", "peer_spread_15"]
MOIS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def horizon_annees() -> float:
    debut = dt.date.fromisoformat(cfg.OBLIG_DATE_DONNEES)
    fin = dt.date.fromisoformat(cfg.OBLIG_LIQUIDATION)
    return (fin - debut).days / 365.25


def score_rang_relatif(valeur: float, toutes: list[float], bas: float, haut: float) -> float:
    """Reproduit NB.SI.ENS(<=) du classeur : des ex-aequo ont le meme score."""
    if len(toutes) < 2:
        raise ValueError("au moins deux obligations eligibles sont necessaires")
    n_inf = sum(v <= valeur + 1e-12 for v in toutes)
    return bas + (haut - bas) * (n_inf - 1) / (len(toutes) - 1)


def score_duration(duration: float) -> float:
    if 1.5 <= duration <= 3.5:
        return 5
    if 1 <= duration < 1.5 or 3.5 < duration <= 4.5:
        return 4
    return 3


def rendement_total(ytm: float, duration: float, choc_bund_pb: float,
                    choc_spread_pb: float, h: float) -> float:
    return ytm * h - duration * (choc_bund_pb + choc_spread_pb) / 10000


def cle_obligation(coupon: float, mois: int, annee: int) -> tuple:
    return (round(float(coupon), 3), int(mois), int(annee))


def cle_depuis_libelle(libelle: str):
    """'Snam S.p.A. 4.000% Nov 2029' -> (4.0, 11, 2029)."""
    m = re.search(r"(\d+(?:\.\d+)?)%\s+([A-Za-z]{3})\w*\s+(\d{4})", str(libelle))
    if not m or m.group(2).lower() not in MOIS:
        return None
    return cle_obligation(m.group(1), MOIS[m.group(2).lower()], m.group(3))


def cle_depuis_symbole(symbole: str):
    """'IT-SGR-4.000-27112029' -> (4.0, 11, 2029)."""
    m = re.match(r"^[A-Z]{2}-[A-Z0-9.]+-(\d+(?:\.\d+)?)-(\d{2})(\d{2})(\d{4})$",
                 str(symbole).strip().upper())
    return cle_obligation(m.group(1), m.group(3), m.group(4)) if m else None


def scorer(brut: pd.DataFrame) -> pd.DataFrame:
    """Classement des obligations eligibles, du meilleur score au moins bon."""
    h = horizon_annees()
    df = brut[brut["eligible"].astype(str).str.strip().str.upper() == "OUI"].copy()
    for c in CHAMPS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    incompletes = df[df[CHAMPS].isna().any(axis=1)]
    for r in incompletes.itertuples():
        note(f"ATTENTION obligation ecartee, donnees incompletes : {r.obligation}")
    df = df.drop(incompletes.index)
    if len(df) < 2:
        note("ATTENTION moins de deux obligations eligibles : pas de classement")
        return pd.DataFrame()

    for nom, (bund, spread) in cfg.OBLIG_SCENARIOS.items():
        tr_bench = rendement_total(cfg.OBLIG_BENCH_YTM, cfg.OBLIG_BENCH_DURATION,
                                   bund, spread, h)
        df["tr_" + nom] = [rendement_total(y, d, bund, spread, h)
                           for y, d in zip(df["ytm"], df["duration"])]
        df["alpha_" + nom] = df["tr_" + nom] - tr_bench

    centr, stress = df["alpha_central"].tolist(), df["alpha_stress"].tolist()
    df["valuation_25"] = [score_rang_relatif(a, centr, 1, 10)
                          + score_rang_relatif(s, stress, 1, 10) + p / 3
                          for a, s, p in zip(df["alpha_central"], df["alpha_stress"],
                                             df["peer_spread_15"])]
    df["horizon_structure_10"] = df["duration"].map(score_duration) + df["structure_5"]
    df["score_100"] = (df["credit_25"] + df["risk_25"] + df["valuation_25"]
                       + df["diversification_15"] + df["horizon_structure_10"])
    df["rang"] = [1 + int((df["score_100"] > s + 1e-10).sum()) for s in df["score_100"]]

    # Controle : le classement doit reproduire le classeur valide.
    if "score_excel" in df.columns:
        ref = pd.to_numeric(df["score_excel"], errors="coerce")
        ecart = (df["score_100"] - ref).abs()
        if (ecart > 1e-6).any():
            note(f"ATTENTION scores obligataires differents du classeur : "
                 f"{', '.join(df.loc[ecart > 1e-6, 'obligation'])}")
    df["cle"] = df["obligation"].map(cle_depuis_libelle)
    return df.sort_values(["score_100", "obligation"], ascending=[False, True]) \
             .reset_index(drop=True)


def rapprocher(classement: pd.DataFrame, detenues: pd.DataFrame) -> tuple[list, list]:
    """Marque les obligations detenues dans le classement, et renvoie celles
    que le fonds detient sans qu'elles figurent dans le classeur."""
    if classement.empty:
        return [], []
    det = {}
    for r in detenues.itertuples():
        k = cle_depuis_symbole(r.symbole_stocktrak)
        if k:
            det[k] = r
    lignes, vus = [], set()
    for r in classement.itertuples():
        d = det.get(r.cle)
        if d is not None:
            vus.add(r.cle)
        lignes.append({
            "rang": int(r.rang), "emetteur": r.issuer, "obligation": r.obligation,
            "score": float(r.score_100), "credit": float(r.credit_25),
            "risque": float(r.risk_25), "valorisation": float(r.valuation_25),
            "diversification": float(r.diversification_15),
            "horizon": float(r.horizon_structure_10),
            "ytm": float(r.ytm), "duration": float(r.duration),
            "alpha_central": float(r.alpha_central), "alpha_stress": float(r.alpha_stress),
            "tr_central": float(r.tr_central), "tr_stress": float(r.tr_stress),
            "detenue": d is not None,
            "symbole": d.symbole_stocktrak if d is not None else None,
            "quantite": float(d.quantite) if d is not None else None,
        })
    hors = [{"symbole": r.symbole_stocktrak, "description": r.description,
             "quantite": float(r.quantite)}
            for k, r in det.items() if k not in vus]
    if hors:
        note(f"obligations detenues absentes du classeur IG : "
             f"{', '.join(h['symbole'] for h in hors)}")
    return lignes, hors


def charger() -> pd.DataFrame:
    chemin = cfg.DATA / "obligations_ig.csv"
    if not chemin.exists():
        note("pas de data/obligations_ig.csv : pas de scoring obligataire")
        return pd.DataFrame()
    return pd.read_csv(chemin, encoding="utf-8-sig", dtype=str)
