# -*- coding: utf-8 -*-
"""
Positions reelles du fonds et etat du compte.

Source des positions, par ordre de preference :

  1. le dernier export StockTrak depose dans data/, nomme
     OpenPosition_JJ_MM_AAAA.csv. On prend toujours le plus recent d'apres la
     date du nom ; les anciens restent dans le depot et servent de trace ;
  2. a defaut, data/positions.csv, la photo saisie a la main au lancement.

Chaque ligne porte un type explicite :

  - "action" : le symbole StockTrak correspond a un titre de data/univers.csv.
    Elle passe par le classement, le DCF et les signaux ;
  - "etf"    : aucun titre de l'univers ne correspond. Elle compte dans la
    valeur du fonds et dans l'allocation, mais ni le classement Novy-Marx ni
    le DCF n'ont de sens pour un ETF obligataire. Chaque ligne classee ainsi
    est ecrite dans le journal : une action mal saisie dans l'univers ne doit
    pas devenir un ETF sans que personne le voie.

L'etat du compte (transactions consommees, liquidites) vit dans
data/compte.csv, une ligne par mise a jour ; la plus recente fait foi.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as cfg
from .journal import note

MOTIF_EXPORT = re.compile(r"^OpenPosition_(\d{1,2})_(\d{1,2})_(\d{4})(.*)\.csv$",
                          re.IGNORECASE)
COLONNES_EXPORT = ["Symbol", "Description", "Quantity", "Currency", "LastPrice",
                   "PricePaid", "DayChange", "ProfitLoss", "MarketValue",
                   "ProfitLossPercentage"]
# Mots qui disent qu'une ligne hors univers est bien un fonds indiciel. Une
# ligne hors univers qui n'en contient aucun reste traitee comme un ETF, mais
# le journal le signale : c'est peut-etre une action absente de l'univers.
# Obligations : StockTrak les nomme PAYS-EMETTEUR-COUPON-ECHEANCE
# (FR-HO-4.250-18102031 = Thales 4,25 % octobre 2031), prix pour 1 000 de nominal.
MOTIF_OBLIGATION = re.compile(r"^[A-Z]{2}-[A-Z0-9.]+-\d+(?:\.\d+)?-\d{8}$")
# Contrats a terme : SOUS-JACENT/MOIS-ANNEE (ZN/H7 = T-Note 10 ans mars 2027).
# Leur MarketValue est le NOMINAL ; StockTrak ne debite que le depot de
# garantie. Compte comme un ETF, le ZN/H7 faisait croire le 14/11/2026 a
# 95 000 EUR de positions de plus, et le controle des liquidites criait faux.
MOTIF_FUTURE = re.compile(r"^[A-Z0-9]{1,6}/[FGHJKMNQUVXZ]\d{1,2}$")
MOTS_ETF = ("ETF", "UCITS", "ISHARES", "BLACKROCK", "XTRACKERS", "AMUNDI", "LYXOR", "SPDR",
            "VANGUARD", "INVESCO", "WISDOMTREE", "INDEX", "FUND", "BOND", "TRACKER")


# ------------------------------------------------------------ formats ------
def nombre_fr(v) -> float:
    """'2 431,26' -> 2431.26. Accepte espaces inseables, %, signe moins
    typographique et nombres deja convertis. Vide -> NaN."""
    if v is None:
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    s = str(v).strip()
    for c in (" ", " ", " ", " ", "%", "€", "﻿"):
        s = s.replace(c, "")
    s = s.replace("−", "-").replace("–", "-")
    if s.startswith("(") and s.endswith(")"):       # (12,5) = -12,5
        s = "-" + s[1:-1]
    if not s or s in ("-", "--", "N/A", "n/a"):
        return np.nan
    if "," in s:
        # Virgule decimale : les points eventuels sont des milliers.
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def normaliser_symbole(s) -> str:
    """Forme commune aux deux ecritures du meme titre.

    L'export ecrit 'JD.' et 'ESSITY B', l'univers 'JD.:LN' et 'ESSITYB:ST'.
    On retire la place (':LN'), puis espaces et points, en majuscules :
    les deux donnent 'JD' et 'ESSITYB'.
    """
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = str(s).strip().upper()
    s = re.sub(r":[A-Z]{1,3}$", "", s)
    return re.sub(r"[\s. ]", "", s)


# ---------------------------------------------------------- choix fichier --
def _cle_export(p: Path):
    m = MOTIF_EXPORT.match(p.name)
    j, mo, a, reste = m.groups()
    try:
        d = dt.date(int(a), int(mo), int(j))
    except ValueError:
        return None
    # 'OpenPosition_13_11_2026 (2).csv' ou '_2' : le numero departage deux
    # exports du meme jour. Pas la date de modification : apres un clone, tous
    # les fichiers ont la meme.
    n = re.findall(r"\d+", reste)
    return (d, int(n[-1]) if n else 0, p.name)


def exports_disponibles(dossier: Path | None = None) -> list[tuple[dt.date, Path]]:
    """Tous les exports reconnus, du plus ancien au plus recent."""
    dossier = dossier or cfg.DATA
    trouves = []
    for p in dossier.glob("*.csv"):
        if not MOTIF_EXPORT.match(p.name):
            continue
        k = _cle_export(p)
        if k is None:
            note(f"ATTENTION export ignore, date invalide dans le nom : {p.name}")
            continue
        trouves.append((k, p))
    trouves.sort(key=lambda x: x[0])
    return [(k[0], p) for k, p in trouves]


def _lire_texte(chemin: Path) -> str:
    brut = chemin.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return brut.decode(enc)
        except UnicodeDecodeError:
            continue
    return brut.decode("latin-1")


def lire_export(chemin: Path) -> pd.DataFrame:
    """L'export brut, nombres convertis. Separateur ';', ',' ou tabulation."""
    import csv
    import io

    texte = _lire_texte(chemin)
    premiere = texte.splitlines()[0] if texte else ""
    sep = max((";", "\t", ","), key=premiere.count)
    df = pd.read_csv(io.StringIO(texte), sep=sep, dtype=str, quoting=csv.QUOTE_MINIMAL,
                     skipinitialspace=True)
    df.columns = [str(c).strip().strip('"').replace("﻿", "") for c in df.columns]
    manquantes = [c for c in ("Symbol", "Quantity", "Currency", "LastPrice", "PricePaid")
                  if c not in df.columns]
    if manquantes:
        raise ValueError(f"{chemin.name} : colonnes absentes {manquantes} "
                         f"(lues : {list(df.columns)})")
    df = df[df["Symbol"].notna() & (df["Symbol"].str.strip() != "")].copy()
    for c in ("Quantity", "LastPrice", "PricePaid", "DayChange", "ProfitLoss",
              "MarketValue", "ProfitLossPercentage"):
        if c in df.columns:
            df[c] = df[c].map(nombre_fr)
    df["Symbol"] = df["Symbol"].str.strip()
    df["Currency"] = df["Currency"].fillna("").str.strip().str.upper()
    if "Description" not in df.columns:
        df["Description"] = ""
    return df


# ----------------------------------------------------------- positions -----
def _depuis_export(chemin: Path, univers: pd.DataFrame) -> pd.DataFrame:
    from .collecte import place

    brut = lire_export(chemin)
    table = {normaliser_symbole(s): t for s, t in
             zip(univers["Symbole StockTrak"], univers["Ticker"])}
    lignes = []
    for r in brut.itertuples(index=False):
        q = r.Quantity
        if not np.isfinite(q) or q == 0:
            continue
        devise, cours, paye = r.Currency or "EUR", r.LastPrice, r.PricePaid
        # Londres peut sortir en pence (GBX / GBp) : on ramene en livres,
        # comme le fait collecte.py pour Yahoo.
        if devise == "GBX":
            devise, cours, paye = "GBP", cours / 100, paye / 100
        ticker = table.get(normaliser_symbole(r.Symbol))
        ligne = {
            "symbole_stocktrak": r.Symbol, "description": r.Description,
            "quantite": float(q), "devise": devise,
            "prix_paye_local": paye, "cours_stocktrak": cours,
            "valeur_marche_stocktrak": getattr(r, "MarketValue", np.nan),
            "pl_stocktrak": getattr(r, "ProfitLoss", np.nan),
        }
        if ticker:
            attendue = place(ticker)[0]
            if devise != attendue:
                note(f"ATTENTION {r.Symbol} -> {ticker} : devise {devise} dans "
                     f"l'export, {attendue} attendue sur sa place")
            ligne.update(Ticker=ticker, type="action")
        elif (MOTIF_FUTURE.match(str(r.Symbol).strip().upper())
              or "FUTURE" in str(r.Description or "").upper()):
            ligne.update(Ticker=r.Symbol, type="future")
        elif MOTIF_OBLIGATION.match(str(r.Symbol).strip().upper()):
            ligne.update(Ticker=r.Symbol, type="obligation")
        else:
            ligne.update(Ticker=r.Symbol, type="etf")
        lignes.append(ligne)
    pos = pd.DataFrame(lignes)
    if pos.empty:
        raise ValueError(f"{chemin.name} : aucune position lisible")
    doublons = pos.loc[pos["Ticker"].duplicated(), "Ticker"].tolist()
    if doublons:
        note(f"ATTENTION symboles en double dans l'export, quantites additionnees : "
             f"{', '.join(doublons)}")
        pos["cout"] = pos["quantite"] * pos["prix_paye_local"]
        pos = pos.groupby("Ticker", as_index=False).agg(
            {"symbole_stocktrak": "first", "description": "first", "quantite": "sum",
             "devise": "first", "cout": "sum", "cours_stocktrak": "first",
             "valeur_marche_stocktrak": "sum", "pl_stocktrak": "sum", "type": "first"})
        pos["prix_paye_local"] = pos["cout"] / pos["quantite"]
        pos = pos.drop(columns="cout")

    etf = pos[pos["type"] == "etf"]
    for r in etf.itertuples():
        desc = str(r.description or "")
        ressemble = any(m in desc.upper() for m in MOTS_ETF)
        note(f"hors univers, traite comme ETF (ni classement ni DCF) : "
             f"{r.symbole_stocktrak} - {desc}"
             + ("" if ressemble else
                "  ATTENTION la description ne ressemble pas a un ETF : "
                "action absente de data/univers.csv ?"))
    oblig = pos[pos["type"] == "obligation"]
    if len(oblig):
        note(f"obligations (ni classement ni DCF) : {len(oblig)} -> "
             f"{', '.join(oblig['symbole_stocktrak'])}")
    fut = pos[pos["type"] == "future"]
    for r in fut.itertuples():
        note(f"contrat a terme (valeur = P/L, nominal hors valeur du fonds) : "
             f"{r.symbole_stocktrak} - {r.description} - nominal "
             f"{r.valeur_marche_stocktrak:,.0f} EUR")
    note(f"positions lues dans {chemin.name} : "
         f"{int((pos['type'] == 'action').sum())} actions, {len(oblig)} obligations, "
         f"{len(etf)} ETF, {len(fut)} futures")
    return pos


def _depuis_photo() -> pd.DataFrame:
    pos = pd.read_csv(cfg.DATA / "positions.csv")
    pos["type"] = "action"
    pos["description"] = ""
    pos["cours_stocktrak"] = np.nan
    pos["valeur_marche_stocktrak"] = np.nan
    pos["pl_stocktrak"] = np.nan
    return pos


def charger(univers: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Positions du fonds et description de leur source."""
    exports = exports_disponibles()
    # Du plus recent au plus ancien : un export illisible est signale et l'on
    # se rabat sur le precedent plutot que de laisser la mise a jour tomber.
    for d, chemin in reversed(exports):
        try:
            pos = _depuis_export(chemin, univers)
        except Exception as e:                          # noqa: BLE001
            note(f"ATTENTION export illisible, ignore : {chemin.name} ({e})")
            continue
        if chemin != exports[-1][1]:
            note(f"ATTENTION positions lues dans un export ancien : {chemin.name}")
        return pos, {"type": "export", "fichier": chemin.name,
                     "date": d.isoformat(), "exports_conserves": len(exports)}
    note("aucun export StockTrak lisible dans data/ : repli sur data/positions.csv")
    return _depuis_photo(), {"type": "photo", "fichier": "positions.csv",
                             "date": None, "exports_conserves": len(exports)}


# --------------------------------------------------------------- compte ----
def compte() -> dict:
    """Derniere ligne de data/compte.csv : transactions consommees et
    liquidites en euros. Une liquidite vide reste vide, elle ne vaut pas 0."""
    chemin = cfg.DATA / "compte.csv"
    if not chemin.exists():
        note("ATTENTION data/compte.csv absent : transactions inconnues")
        return {"date": None, "transactions": cfg.TRANSACTIONS_CONSTRUCTION,
                "liquidites_eur": np.nan}
    c = pd.read_csv(chemin, dtype=str).dropna(subset=["date"])
    c["date"] = pd.to_datetime(c["date"].str.strip(), errors="coerce")
    c = c.dropna(subset=["date"]).sort_values("date", kind="stable")
    if c.empty:
        raise ValueError("data/compte.csv ne contient aucune ligne datee")
    d = c.iloc[-1]
    t = nombre_fr(d.get("transactions_consommees"))
    if not np.isfinite(t):
        raise ValueError(f"data/compte.csv : transactions_consommees vide au "
                         f"{d['date'].date()}")
    liq = nombre_fr(d.get("liquidites_eur"))
    if not np.isfinite(liq):
        note("solde de liquidites non renseigne dans data/compte.csv : "
             "la valeur du fonds ne compte que les titres")
    return {"date": d["date"].date().isoformat(), "transactions": int(t),
            "liquidites_eur": liq}
