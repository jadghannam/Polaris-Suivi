# -*- coding: utf-8 -*-
"""
Collecte des donnees de marche.

Deux rythmes, et c'est le point le plus important du module :

  - les COURS et les TAUX DE CHANGE changent tous les jours ;
  - les DONNEES COMPTABLES ne changent que quand une societe publie.

Retelecharger les comptes chaque jour serait du gaspillage, mais surtout
Yahoo revise ses chiffres en silence : le classement bougerait sans que
personne puisse dire pourquoi. Les fondamentaux sont donc rafraichis une fois
par semaine, et chaque modification est ecrite dans le journal.
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import yfinance as yf

from . import config as cfg
from .journal import note


# --------------------------------------------------------------- cours -------
def cours_du_jour(tickers: list[str]) -> pd.DataFrame:
    """Dernier cours, volume et amplitude du jour, en devise de cotation.

    On ramene aussi le volume et l'amplitude parce qu'ils servent au test de
    ligne fantome : une cotation sans volume et sans amplitude n'est pas
    negociable, quel que soit le prix affiche.
    """
    lignes = []
    paquet = yf.Tickers(" ".join(tickers))
    for t in tickers:
        try:
            h = paquet.tickers[t].history(period="5d", auto_adjust=False)
            if h.empty:
                note(f"cours absent pour {t}")
                lignes.append({"Ticker": t})
                continue
            d = h.iloc[-1]
            info = paquet.tickers[t].fast_info
            lignes.append({
                "Ticker": t,
                "date": h.index[-1].date().isoformat(),
                "cours": float(d["Close"]),
                "ouverture": float(d["Open"]),
                "haut": float(d["High"]),
                "bas": float(d["Low"]),
                "volume": float(d["Volume"]),
                "devise": getattr(info, "currency", None),
                "actions_m": (getattr(info, "shares", None) or 0) / 1e6 or None,
            })
        except Exception as e:                      # noqa: BLE001
            note(f"echec cours {t} : {e}")
            lignes.append({"Ticker": t})
    df = pd.DataFrame(lignes)
    df["negociable"] = (df.get("volume", 0).fillna(0) >= cfg.VOLUME_MIN_JOUR) & \
                       (df.get("haut", 0).fillna(0) > df.get("bas", 0).fillna(0))
    return df


def taux_de_change() -> dict[str, float]:
    """Unites de devise par euro, comme dans la base (1 EUR = 0,86 GBP)."""
    taux = {"EUR": 1.0}
    for d in cfg.DEVISES:
        try:
            h = yf.Ticker(f"EUR{d}=X").history(period="5d")
            taux[d] = float(h["Close"].iloc[-1])
        except Exception as e:                      # noqa: BLE001
            note(f"taux EUR/{d} indisponible : {e}")
    return taux


def indice(symbole: str = cfg.BENCHMARK, depuis: str = cfg.DATE_LANCEMENT) -> pd.Series:
    """Serie de cloture de l'indice de reference depuis le lancement."""
    h = yf.Ticker(symbole).history(start=depuis)
    if h.empty:
        note(f"indice {symbole} indisponible")
        return pd.Series(dtype=float)
    s = h["Close"]
    s.index = [d.date().isoformat() for d in s.index]
    return s


# --------------------------------------------------- donnees comptables ------
def _val(df: pd.DataFrame, cles: list[str], col) -> float | None:
    for k in cles:
        if k in df.index:
            v = df.loc[k, col]
            if pd.notna(v):
                return float(v) / 1e6          # en millions
    return None


def fondamentaux(tickers: list[str]) -> pd.DataFrame:
    """Comptes du dernier exercice publie, en millions de devise de publication.

    Les conventions de signe de Yahoo sont redressees ici, une fois pour
    toutes : les capex sortent en negatif, la variation du BFR est inversee.
    """
    lignes = []
    for t in tickers:
        try:
            y = yf.Ticker(t)
            inc, bil, cf = y.income_stmt, y.balance_sheet, y.cashflow
            if inc.empty or bil.empty:
                note(f"etats financiers absents pour {t}")
                continue
            c = inc.columns[0]
            cb = bil.columns[0]
            l = {
                "Ticker": t,
                "ca": _val(inc, ["Total Revenue", "Operating Revenue"], c),
                "cogs": _val(inc, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], c),
                "actif": _val(bil, ["Total Assets"], cb),
                "fonds_propres": _val(bil, ["Stockholders Equity",
                                            "Common Stock Equity"], cb),
                "dette_nette": None,
                "minoritaires": _val(bil, ["Minority Interest"], cb) or 0.0,
                "mises_en_equivalence": _val(
                    bil, ["Investmentin Financial Assets",
                          "Investments In Other Ventures Under Equity Method"], cb) or 0.0,
                "devise_etats": y.info.get("financialCurrency"),
            }
            dette = _val(bil, ["Total Debt"], cb)
            tresorerie = _val(bil, ["Cash And Cash Equivalents",
                                    "Cash Cash Equivalents And Short Term Investments"], cb)
            if dette is not None:
                l["dette_nette"] = dette - (tresorerie or 0.0)
            if l["ca"] is not None and l["cogs"] is not None:
                l["profit_brut"] = l["ca"] - l["cogs"]
            # trois exercices de flux
            for i, suf in enumerate(["n", "n1", "n2"]):
                if i < len(inc.columns):
                    cc = inc.columns[i]
                    l[f"ebit_{suf}"] = _val(inc, ["EBIT", "Operating Income"], cc)
                if cf is not None and not cf.empty and i < len(cf.columns):
                    cc = cf.columns[i]
                    l[f"da_{suf}"] = _val(
                        cf, ["Depreciation And Amortization",
                             "Depreciation Amortization Depletion"], cc)
                    capex = _val(cf, ["Capital Expenditure"], cc)
                    l[f"capex_{suf}"] = abs(capex) if capex is not None else None
                    bfr = _val(cf, ["Change In Working Capital"], cc)
                    # Yahoo publie la variation du BFR avec le signe de son
                    # effet sur la tresorerie : on retablit la convention
                    # comptable (une hausse du BFR consomme du cash).
                    l[f"dbfr_{suf}"] = -bfr if bfr is not None else None
            lignes.append(l)
        except Exception as e:                      # noqa: BLE001
            note(f"echec fondamentaux {t} : {e}")
    return pd.DataFrame(lignes)


# ----------------------------------------------------------- orchestration ---
def doit_rafraichir_fondamentaux(aujourdhui: dt.date | None = None) -> bool:
    j = aujourdhui or dt.date.today()
    return j.weekday() == cfg.JOUR_FONDAMENTAUX
