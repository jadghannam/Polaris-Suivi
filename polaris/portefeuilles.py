# -*- coding: utf-8 -*-
"""
Univers filtres et portefeuilles multiples.

Ajoute le 14/11/2026. Trois idees :

1. Un univers filtre par CONTRAINTES. Le fonds Polaris en a deux, verrouillees
   (Europe, StockTrak). Un portefeuille personnel peut les decocher.

2. Le classement est refait A L'INTERIEUR de chaque univers filtre :
   percentiles, medianes sectorielles, planchers, rangs. Un titre n'a donc pas
   le meme rang dans le fonds et dans l'univers mondial, et c'est voulu :
   Novy-Marx classe une societe contre ses concurrentes du meme univers. Avec
   les deux contraintes, on retrouve exactement le classement du fonds.

3. Un portefeuille cree sur la page est CONSTRUIT PAR LA METHODE le jour de sa
   premiere mise a jour : les N premiers rangs de la liste de suivi au verdict
   DCF A ou B, sans veto qualitatif, equipondere. Ensuite il est suivi avec les
   memes zones que le fonds. Rien n'est automatique : la plateforme signale les
   sorties et les remplacants, on decide.

Fichiers :
  data/portefeuilles.json              definitions, ecrites par la page
  data/portefeuilles/<id>.csv          lignes construites (figees a la creation)
  data/portefeuilles/<id>_historique.csv  zones par jour, pour la persistance
  docs/classements/<cle>.json          classement complet d'un univers filtre
  docs/portefeuilles.json              etat de chaque portefeuille, pour la page
"""

from __future__ import annotations

import datetime as dt
import json
import re

import numpy as np
import pandas as pd

from . import classement as cl
from . import config as cfg
from . import dcf
from . import signaux as sg
from .journal import note

DOSSIER = cfg.DATA / "portefeuilles"


# ------------------------------------------------------------ univers -------
def filtrer(univers: pd.DataFrame, contraintes) -> pd.DataFrame:
    """Filtre par les colonnes contrainte_europe et contrainte_stocktrak de
    data/univers.csv, posees A LA MAIN (OUI / NON), jamais deduites.

    Decide le 14/11/2026 avec Jad : l'univers du fonds ne doit dependre d'aucune
    regle qui pourrait bouger (region recalculee, date de verification effacee).
    Les 192 lignes du fonds portent OUI / OUI ; un titre n'y entre que si
    quelqu'un ecrit OUI dans le fichier.
    """
    c = set(contraintes or ())
    m = pd.Series(True, index=univers.index)
    for k in ("europe", "stocktrak"):
        if k in c:
            col = f"contrainte_{k}"
            if col not in univers.columns:
                raise ValueError(f"data/univers.csv sans colonne {col} : univers non filtrable")
            m &= univers[col].astype(str).str.strip().str.upper() == "OUI"
    return univers[m].copy()


def cle(contraintes) -> str:
    c = sorted(set(contraintes or ()))
    return "-".join(c) if c else "monde"


def classer_univers(univers_complet, contraintes, rang_in, dcf_in, hist_ca, wacc,
                    cours, taux, bloques, vetos) -> pd.DataFrame:
    """Classement et DCF d'un univers filtre. Les blocages StockTrak ne valent
    que sous la contrainte StockTrak : ils disent ce que StockTrak cote mal."""
    stocktrak = "stocktrak" in set(contraintes or ())
    u = filtrer(univers_complet, contraintes)
    clt = cl.classer(u, rang_in, cours, taux, bloques if stocktrak else set(),
                     exiger_stocktrak=stocktrak)
    ev = dcf.evaluer(clt, dcf_in, hist_ca, wacc)
    ev["veto_qualitatif"] = ev["Ticker"].isin(vetos)
    return ev


COLONNES_FICHE = [
    "Ticker", "Societe", "Pays", "Region", "Indice", "Secteur", "devise", "cours",
    "capitalisation", "GP/A", "mediane_secteur", "GP/A ajuste", "B/M",
    "rang_rentabilite", "rang_valorisation", "rang_combine", "plancher_ok",
    "liquide", "negociable", "bloque", "bm_implausible", "rang", "liste_suivi",
    "wacc", "fcff", "ve_marche", "dette_nette", "g1", "cagr_brut", "cagr_retenu",
    "origine_cagr", "seuil", "dispersion", "verdict", "marge", "veto_qualitatif",
]


def _propre(v):
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def ecrire_classement(ev: pd.DataFrame, nom: str, contraintes) -> None:
    dossier = cfg.DOCS / "classements"
    dossier.mkdir(parents=True, exist_ok=True)
    lignes = [{k: _propre(v) for k, v in r.items()}
              for r in ev.reindex(columns=COLONNES_FICHE).to_dict("records")]
    (dossier / f"{nom}.json").write_text(json.dumps({
        "contraintes": sorted(set(contraintes or ())),
        "nb_titres": len(lignes),
        "nb_classes": int(ev["rang"].notna().sum()),
        "lignes": lignes}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------- definitions -----
def definitions() -> list[dict]:
    chemin = cfg.DATA / "portefeuilles.json"
    if not chemin.exists():
        return []
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        note(f"ATTENTION data/portefeuilles.json illisible : {e}")
        return []
    out = []
    for d in brut if isinstance(brut, list) else []:
        i = re.sub(r"[^a-z0-9-]", "", str(d.get("id", "")).lower())
        if not i or i == "polaris":
            note(f"ATTENTION portefeuille sans identifiant valide ignore : {d}")
            continue
        out.append({
            "id": i, "nom": d.get("nom") or i,
            "contraintes": [c for c in d.get("contraintes", []) if c in cfg.CONTRAINTES],
            "nb_lignes": int(d.get("nb_lignes") or 25),
            "capital": float(d.get("capital") or 100_000),
            "date_creation": d.get("date_creation") or dt.date.today().isoformat(),
            "indice": d.get("indice") if d.get("indice") in cfg.INDICES else "URTH",
            "archive": bool(d.get("archive", False)),
        })
    return out


# --------------------------------------------------------- construction -----
def eligibles(ev: pd.DataFrame) -> pd.DataFrame:
    verdict = ev["verdict"].fillna("").str.split(" - ").str[0].str.strip()
    m = (ev["liste_suivi"].fillna(False) & verdict.isin(cfg.REMPLACANT_VERDICTS)
         & ~ev["veto_qualitatif"] & ev["negociable"].fillna(False)
         & ~ev["bm_implausible"].fillna(False))
    return ev[m].sort_values("rang")


def construire(d: dict, ev: pd.DataFrame, taux: dict, aujourdhui: dt.date) -> pd.DataFrame:
    """Les N premiers eligibles, equiponderes au cours du jour."""
    choix = eligibles(ev).head(d["nb_lignes"])
    if len(choix) < d["nb_lignes"]:
        note(f"portefeuille {d['id']} : {len(choix)} titres eligibles seulement "
             f"pour {d['nb_lignes']} demandes")
    if choix.empty:
        return pd.DataFrame()
    poche = d["capital"] / len(choix)
    fx = choix["devise"].map(lambda x: taux.get(x, np.nan))
    cours_eur = choix["cours"] / fx
    return pd.DataFrame({
        "Ticker": choix["Ticker"].values, "date_entree": aujourdhui.isoformat(),
        "devise": choix["devise"].values, "prix_entree": choix["cours"].values,
        "taux_entree": fx.values, "quantite": (poche / cours_eur).values,
        "rang_entree": choix["rang"].values,
    })


# ------------------------------------------------------------- indices ------
def perf_indice_eur(symbole: str, depuis: str) -> float:
    """Performance en euros d'un indice depuis une date : variation du prix en
    devise locale corrigee de la variation du change."""
    import yfinance as yf
    devise = cfg.INDICES.get(symbole, ("", "EUR"))[1]
    try:
        h = yf.Ticker(symbole).history(start=depuis)["Close"].dropna()
        if len(h) < 2:
            return 0.0 if len(h) == 1 else np.nan
        p = float(h.iloc[-1] / h.iloc[0])
        if devise != "EUR":
            fx = yf.Ticker(f"EUR{devise}=X").history(start=depuis)["Close"].dropna()
            if len(fx) >= 2:
                p *= float(fx.iloc[0] / fx.iloc[-1])
        return p - 1
    except Exception as e:                              # noqa: BLE001
        note(f"indice {symbole} indisponible : {e}")
        return np.nan


# --------------------------------------------------------------- suivi ------
def suivre(d: dict, pos: pd.DataFrame, ev: pd.DataFrame, taux: dict,
           aujourdhui: dt.date, perf_indice: float) -> dict:
    p = pos.merge(ev.reindex(columns=COLONNES_FICHE), on="Ticker", how="left",
                  suffixes=("", "_ev"))
    p["devise"] = p["devise"].fillna(p.get("devise_ev"))
    fx = p["devise"].map(lambda x: taux.get(x, np.nan))
    p["valeur_eur"] = p["quantite"] * p["cours"] / fx
    p["cout_eur"] = p["quantite"] * p["prix_entree"] / p["taux_entree"]
    p["perf"] = p["valeur_eur"] / p["cout_eur"] - 1          # en euros, change compris
    p["perf_locale"] = p["cours"] / p["prix_entree"] - 1
    p["perf_relative"] = p["perf"] - (perf_indice if np.isfinite(perf_indice) else 0.0)
    total = float(p["valeur_eur"].sum())
    p["poids"] = p["valeur_eur"] / total if total else np.nan

    chemin_h = DOSSIER / f"{d['id']}_historique.csv"
    hist = pd.read_csv(chemin_h) if chemin_h.exists() else pd.DataFrame(
        columns=["date", "Ticker", "zone_dcf", "zone_degradation", "zone"])
    lignes, nouvelles = [], []
    for r in p.itertuples():
        a_cours = np.isfinite(r.cours) if r.cours is not None else False
        z = {"rang": sg.zone_rang(r.rang), "dcf": sg.zone_dcf(r.marge),
             "decrochage": sg.zone_decrochage(r.perf_relative),
             # itertuples renomme les colonnes a barre oblique : lecture directe
             "degradation": sg.zone_degradation(p.at[r.Index, "GP/A ajuste"],
                                                p.at[r.Index, "mediane_secteur"])}
        if not a_cours:
            z = {k: sg.OK for k in z}
        globale = sg.zone_globale(z)
        nouvelles.append({"date": aujourdhui.isoformat(), "Ticker": r.Ticker,
                          "zone_dcf": z["dcf"], "zone_degradation": z["degradation"],
                          "zone": globale})
        lignes.append((r, z, globale))
    hist = pd.concat([hist, pd.DataFrame(nouvelles)], ignore_index=True) \
             .drop_duplicates(subset=["date", "Ticker"], keep="last")
    hist.to_csv(chemin_h, index=False)

    detenus = set(p["Ticker"])
    candidats = sg.remplacants_eligibles(ev[ev["liste_suivi"].fillna(False)], detenus,
                                         set(ev.loc[ev["veto_qualitatif"], "Ticker"]))
    ecarts = p.groupby("Secteur")["poids"].sum().to_dict()
    sortie = []
    for r, z, globale in lignes:
        clot = max(sg.compter_clotures(hist, r.Ticker, "zone_dcf"),
                   sg.compter_clotures(hist, r.Ticker, "zone_degradation"))
        confirme = (clot >= cfg.CLOTURES_CONFIRMATION or z["rang"] == sg.SORTIE
                    or z["decrochage"] == sg.SORTIE)
        remp = None
        if globale == sg.SORTIE:
            m = sg.meilleur_remplacant(candidats, r.Secteur, ecarts)
            if m is not None:
                remp = {"Ticker": m["Ticker"], "Societe": m["Societe"],
                        "rang": _propre(m["rang"]), "verdict": m["verdict"]}
        sortie.append({
            "ticker": r.Ticker, "societe": r.Societe, "pays": r.Pays,
            "region": r.Region, "secteur": r.Secteur, "devise": r.devise,
            "quantite": _propre(r.quantite), "prix_entree": _propre(r.prix_entree),
            "cours": _propre(r.cours), "valeur_eur": _propre(r.valeur_eur),
            "poids": _propre(r.poids), "perf": _propre(r.perf),
            "perf_locale": _propre(r.perf_locale), "perf_relative": _propre(r.perf_relative),
            "rang": _propre(r.rang), "rang_entree": _propre(r.rang_entree),
            "verdict": r.verdict, "marge": _propre(r.marge),
            "zone_rang": z["rang"], "zone_dcf": z["dcf"],
            "zone_decrochage": z["decrochage"], "zone_degradation": z["degradation"],
            "zone": globale, "clotures_consecutives": clot,
            "sortie_confirmee": bool(confirme and globale == sg.SORTIE),
            "remplacant": remp,
        })
    cout = float(p["cout_eur"].sum())
    return {
        **d, "cle_univers": cle(d["contraintes"]),
        "valeur_eur": total, "cout_eur": cout,
        "perf": total / d["capital"] - 1 if d["capital"] else None,
        "indice_nom": cfg.INDICES[d["indice"]][0],
        "perf_indice": _propre(perf_indice), "nb_lignes_reelles": len(p),
        "repartition_region": {k: float(v) for k, v in p.groupby("Region")["poids"].sum().items()},
        "repartition_secteur": {k: float(v) for k, v in p.groupby("Secteur")["poids"].sum().items()},
        "repartition_devise": {k: float(v) for k, v in p.groupby("devise")["poids"].sum().items()},
        "lignes": sortie,
    }


def ecrire_etats() -> None:
    """docs/etats.json : exercices publies par titre, pour la fiche d'analyse."""
    chemin = cfg.DATA / "etats_annuels.csv"
    if not chemin.exists():
        return
    e = pd.read_csv(chemin).sort_values(["Ticker", "cloture"])
    cols = [c for c in e.columns if c != "Ticker"]
    out = {t: [{k: _propre(v) for k, v in r.items()} for r in g[cols].to_dict("records")]
           for t, g in e.groupby("Ticker")}
    (cfg.DOCS / "etats.json").write_text(json.dumps(out, ensure_ascii=False,
                                                    separators=(",", ":")), encoding="utf-8")


# --------------------------------------------------------- orchestration ----
def calculer(univers_complet, rang_in, dcf_in, hist_ca, wacc, cours, taux,
             bloques, vetos, aujourdhui: dt.date) -> None:
    defs = [d for d in definitions() if not d["archive"]]
    # Les quatre combinaisons, toujours : la page laisse cocher chaque
    # contrainte separement.
    combos = {}
    for c in ([], ["europe"], ["stocktrak"], ["europe", "stocktrak"]):
        combos[cle(c)] = c
    classements = {}
    for k, c in combos.items():
        ev = classer_univers(univers_complet, c, rang_in, dcf_in, hist_ca, wacc,
                             cours, taux, bloques, vetos)
        classements[k] = ev
        ecrire_classement(ev, k, c)
        note(f"univers {k} : {len(ev)} titres, {int(ev['rang'].notna().sum())} classes, "
             f"{int(ev['liste_suivi'].fillna(False).sum())} en liste de suivi")

    DOSSIER.mkdir(parents=True, exist_ok=True)
    etats = []
    for d in defs:
        ev = classements[cle(d["contraintes"])]
        chemin = DOSSIER / f"{d['id']}.csv"
        if chemin.exists():
            pos = pd.read_csv(chemin)
        else:
            pos = construire(d, ev, taux, aujourdhui)
            if pos.empty:
                note(f"ATTENTION portefeuille {d['id']} : aucun titre eligible, non construit")
                continue
            pos.to_csv(chemin, index=False)
            d["date_creation"] = aujourdhui.isoformat()
            note(f"portefeuille {d['id']} construit : {len(pos)} lignes au {aujourdhui}")
        depuis = str(pos["date_entree"].min())
        etats.append(suivre(d, pos, ev, taux, aujourdhui, perf_indice_eur(d["indice"], depuis)))

    ecrire_etats()
    (cfg.DOCS / "portefeuilles.json").write_text(json.dumps({
        "date": aujourdhui.isoformat(),
        "contraintes": cfg.CONTRAINTES,
        "indices": {k: v[0] for k, v in cfg.INDICES.items()},
        "univers": {k: {"contraintes": c, "nb_titres": len(classements[k]),
                        "nb_classes": int(classements[k]["rang"].notna().sum())}
                    for k, c in combos.items()},
        "portefeuilles": etats,
    }, ensure_ascii=False, indent=1, default=_propre), encoding="utf-8")
    note(f"docs/portefeuilles.json ecrit ({len(etats)} portefeuilles personnels)")

    # Backtest : le samedi (comptes rafraichis), ou des qu'il en manque un.
    from . import backtest as bt
    voulus = {"polaris": (list(cfg.CONTRAINTES_POLARIS), 26, "^STOXX"),
              "monde": ([], 30, "URTH")}
    for d in defs:
        voulus[d["id"]] = (d["contraintes"], d["nb_lignes"], d["indice"])
    manquants = {k: v for k, v in voulus.items()
                 if not (cfg.DOCS / "backtest" / f"{k}.json").exists()}
    a_faire = voulus if aujourdhui.weekday() == cfg.JOUR_FONDAMENTAUX else manquants
    if a_faire:
        bt.tout(univers_complet, a_faire)
