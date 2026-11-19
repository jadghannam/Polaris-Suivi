# -*- coding: utf-8 -*-
"""
Parametres annuels de Damodaran : betas desendettes par secteur et par region,
primes de risque par pays.

Ajoute le 19/11/2026. Damodaran publie ses fichiers a des adresses fixes,
mis a jour en janvier (betas) et en fevrier (primes par pays). Chaque samedi,
la plateforme regarde la date de mise a jour (en-tete Last-Modified) ; si un
fichier a change, elle le telecharge, recalcule la table et la PROPOSE :
  - docs/wacc_regions_propose.json : table proposee, avec l'ecart a l'active ;
  - data/wacc_regions.csv           : table ACTIVE, ecrite par le bouton
                                      « Appliquer » de la page (cle GitHub).
La toute premiere table est activee directement : il n'y a rien a comparer.

Le fonds n'est PAS concerne : son WACC (data/wacc_secteurs.csv) est fige
depuis septembre, regle ecrite avant d'etre appliquee. Ces parametres ne
servent qu'aux univers sans la contrainte StockTrak.

Ce qu'on prend chez Damodaran :
  - beta desendette corrige de la tresorerie, moyenne des industries d'un
    secteur ponderee par leur nombre de societes ;
  - ratio D/E et taux d'impot effectif de ces memes industries ;
  - prime de risque actions totale du pays (prime mature + prime pays) et
    ecart de defaut du pays, pour le cout de la dette.
"""

from __future__ import annotations

import datetime as dt
import io
import json
from email.utils import parsedate_to_datetime

import numpy as np
import pandas as pd
import requests

from . import config as cfg
from .journal import note

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
DOSSIER = cfg.DATA / "damodaran"
ACTIVE = cfg.DATA / "wacc_regions.csv"
PROPOSE = cfg.DOCS / "wacc_regions_propose.json"

# Fichier de betas par region de la plateforme.
FICHIER_REGION = {
    "Europe": "betaEurope.xls", "Amerique du Nord": "betas.xls", "Japon": "betaJapan.xls",
    "Pacifique": "betaGlobal.xls",
    "Chine": "betaemerg.xls", "Coree": "betaemerg.xls", "Taiwan": "betaemerg.xls",
    "Inde": "betaemerg.xls", "Asie emergente": "betaemerg.xls",
    "Amerique latine": "betaemerg.xls", "Moyen-Orient et Afrique": "betaemerg.xls",
}
FICHIERS = sorted(set(FICHIER_REGION.values())) + ["ctryprem.xlsx"]

# Industries Damodaran -> secteurs GICS de la plateforme. Financieres,
# assurances et immobilier absents : exclus de la methode.
SECTEURS = {
    "Services de communication": ["Advertising", "Broadcasting", "Cable TV", "Entertainment",
        "Publishing & Newspapers", "Software (Entertainment)", "Software (Internet)",
        "Telecom (Wireless)", "Telecom. Services"],
    "Technologies de l'information": ["Computer Services", "Computers/Peripherals",
        "Electronics (Consumer & Office)", "Electronics (General)", "Semiconductor",
        "Semiconductor Equip", "Software (System & Application)", "Telecom. Equipment"],
    "Sante": ["Drugs (Biotechnology)", "Drugs (Pharmaceutical)", "Healthcare Products",
        "Healthcare Support Services", "Heathcare Information and Technology",
        "Hospitals/Healthcare Facilities"],
    "Energie": ["Coal & Related Energy", "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)", "Oil/Gas Distribution", "Oilfield Svcs/Equip."],
    "Materiaux": ["Building Materials", "Chemical (Basic)", "Chemical (Diversified)",
        "Chemical (Specialty)", "Construction Supplies", "Metals & Mining",
        "Packaging & Container", "Paper/Forest Products", "Precious Metals", "Steel"],
    "Industrie": ["Aerospace/Defense", "Air Transport", "Business & Consumer Services",
        "Diversified", "Electrical Equipment", "Engineering/Construction",
        "Environmental & Waste Services", "Information Services", "Machinery",
        "Office Equipment & Services", "Shipbuilding & Marine", "Transportation",
        "Transportation (Railroads)", "Trucking"],
    "Consommation discretionnaire": ["Apparel", "Auto & Truck", "Auto Parts", "Education",
        "Furn/Home Furnishings", "Homebuilding", "Hotel/Gaming", "Recreation",
        "Restaurant/Dining", "Retail (Automotive)", "Retail (Building Supply)",
        "Retail (Distributors)", "Retail (General)", "Retail (Special Lines)",
        "Rubber& Tires", "Shoe"],
    "Consommation de base": ["Beverage (Alcoholic)", "Beverage (Soft)", "Farming/Agriculture",
        "Food Processing", "Food Wholesalers", "Household Products",
        "Retail (Grocery and Food)", "Tobacco"],
    "Services aux collectivites": ["Green & Renewable Energy", "Power", "Utility (General)",
        "Utility (Water)"],
}
# Noms de pays de la plateforme -> noms de Damodaran, quand ils different.
PAYS_DAMODARAN = {
    "Etats-Unis": "United States", "Royaume-Uni": "United Kingdom", "Allemagne": "Germany",
    "Suisse": "Switzerland", "Pays-Bas": "Netherlands", "Espagne": "Spain", "Italie": "Italy",
    "Suede": "Sweden", "Danemark": "Denmark", "Belgique": "Belgium", "Finlande": "Finland",
    "Norvege": "Norway", "Autriche": "Austria", "Irlande": "Ireland", "Pologne": "Poland",
    "Grece": "Greece", "Japon": "Japan", "Chine": "China", "Coree du Sud": "Korea",
    "Australie": "Australia", "Nouvelle-Zelande": "New Zealand", "Singapour": "Singapore",
    "Inde": "India", "Bresil": "Brazil", "Arabie saoudite": "Saudi Arabia",
    "Afrique du Sud": "South Africa", "Mexique": "Mexico", "Malaisie": "Malaysia",
    "Thailande": "Thailand", "Indonesie": "Indonesia", "Turquie": "Turkey",
    "Emirats arabes unis": "Abu Dhabi", "Koweit": "Kuwait", "Chili": "Chile", "Perou": "Peru",
    "Colombie": "Colombia", "Hongrie": "Hungary", "Republique tcheque": "Czech Republic",
    "Egypte": "Egypt", "Israel": "Israel", "Taiwan": "Taiwan", "Hong Kong": "Hong Kong",
    "Canada": "Canada", "France": "France", "Portugal": "Portugal", "Luxembourg": "Luxembourg",
    "Qatar": "Qatar", "Philippines": "Philippines", "Jersey": "Jersey (States of)",
    "Guernesey": "Guernsey (States of)", "Ile de Man": "Isle of Man",
}


def _get(f: str, methode: str = "get") -> requests.Response:
    r = getattr(requests, methode)(BASE + f, headers=UA, timeout=60)
    r.raise_for_status()
    return r


def _meta() -> dict:
    p = DOSSIER / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def telecharger() -> bool:
    """Telecharge les fichiers qui ont change depuis la derniere fois."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    meta, change = _meta(), False
    for f in FICHIERS:
        try:
            lm = _get(f, "head").headers.get("Last-Modified", "")
            if meta.get(f) == lm and (DOSSIER / f).exists():
                continue
            (DOSSIER / f).write_bytes(_get(f).content)
            meta[f] = lm
            change = True
            note(f"Damodaran : {f} mis a jour ({lm})")
        except Exception as e:                          # noqa: BLE001
            note(f"Damodaran : {f} indisponible ({e})")
    (DOSSIER / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return change


def _industries(fichier: str) -> pd.DataFrame:
    d = pd.read_excel(DOSSIER / fichier, sheet_name="Industry Averages", header=None)
    i = d.index[d[0].astype(str).str.strip() == "Industry Name"][0]
    t = d.iloc[i + 1:].copy()
    t.columns = [str(c).strip() for c in d.iloc[i]]
    t = t[t["Industry Name"].notna()]
    for c in ("Number of firms", "D/E Ratio", "Effective Tax rate",
              "Unlevered beta corrected for cash"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    return t


def table_secteurs() -> pd.DataFrame:
    """Region x secteur : beta desendette, D/E, impot (moyennes ponderees)."""
    lignes = []
    cache = {}
    for region, f in FICHIER_REGION.items():
        if f not in cache:
            cache[f] = _industries(f)
        t = cache[f]
        for secteur, inds in SECTEURS.items():
            g = t[t["Industry Name"].isin(inds)].dropna(
                subset=["Number of firms", "Unlevered beta corrected for cash"])
            if g.empty:
                continue
            w = g["Number of firms"]
            moy = lambda c: float(np.average(g[c].fillna(g[c].median()), weights=w))
            lignes.append({"Region": region, "Secteur": secteur, "fichier": f,
                           "beta_desendette": moy("Unlevered beta corrected for cash"),
                           "de": moy("D/E Ratio"), "impot": moy("Effective Tax rate"),
                           "nb_societes": int(w.sum())})
    return pd.DataFrame(lignes)


def primes_pays() -> pd.DataFrame:
    """Pays Damodaran -> prime de risque actions totale et ecart de defaut."""
    e = pd.read_excel(DOSSIER / "ctryprem.xlsx", sheet_name="ERPs by country", header=None)
    i = e.index[e[0].astype(str).str.strip() == "Country"][0]
    t = e.iloc[i + 1:, :6].copy()
    t.columns = ["pays", "region_dam", "note", "ecart_defaut", "prime_actions", "prime_pays"]
    t = t[t["pays"].notna() & pd.to_numeric(t["prime_actions"], errors="coerce").notna()]
    for c in ("ecart_defaut", "prime_actions", "prime_pays"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t["pays"] = t["pays"].astype(str).str.strip()
    return t[["pays", "ecart_defaut", "prime_actions", "prime_pays"]]


def mettre_a_jour(forcer: bool = False) -> dict:
    """Le samedi : telecharge, recalcule, propose. Renvoie l'etat pour la page."""
    change = telecharger() if forcer or not ACTIVE.exists() or \
        dt.date.today().weekday() == cfg.JOUR_FONDAMENTAUX else False
    if not all((DOSSIER / f).exists() for f in FICHIERS):
        return {"etat": "indisponible"}
    if not change and PROPOSE.exists() and ACTIVE.exists():
        return json.loads(PROPOSE.read_text(encoding="utf-8")).get("etat_resume", {})
    sect, primes = table_secteurs(), primes_pays()
    primes.to_csv(cfg.DATA / "primes_pays.csv", index=False)
    meta = _meta()
    dates = {f: meta.get(f, "") for f in FICHIERS}
    if not ACTIVE.exists():
        sect.to_csv(ACTIVE, index=False)
        note("Damodaran : premiere table de WACC regionale activee")
    actif = pd.read_csv(ACTIVE)
    m = sect.merge(actif, on=["Region", "Secteur"], how="left", suffixes=("", "_actif"))
    ecarts = [{"Region": r.Region, "Secteur": r.Secteur,
               "beta": r.beta_desendette, "beta_actif": r.beta_desendette_actif,
               "de": r.de, "de_actif": r.de_actif} for r in m.itertuples()]
    diff = max((abs(e["beta"] - e["beta_actif"]) for e in ecarts
                if e["beta_actif"] == e["beta_actif"]), default=0.0)
    resume = {"etat": "a_jour" if diff < 1e-6 else "proposee",
              "ecart_beta_max": diff, "fichiers": dates,
              "calcule_le": dt.date.today().isoformat()}
    PROPOSE.write_text(json.dumps({
        "etat_resume": resume, "ecarts": ecarts,
        "csv": sect.to_csv(index=False)}, ensure_ascii=False, indent=1,
        default=lambda o: None), encoding="utf-8")
    if resume["etat"] == "proposee":
        note(f"Damodaran : nouvelle table de WACC proposee (ecart de beta max {diff:.2f}) : "
             f"a appliquer depuis la page")
    return resume


def parametres() -> dict | None:
    """Ce dont le DCF a besoin pour un WACC regional, ou None s'il manque
    quelque chose (le DCF reprend alors la convention du fonds)."""
    if not ACTIVE.exists() or not (cfg.DATA / "primes_pays.csv").exists():
        return None
    sect = pd.read_csv(ACTIVE)
    primes = pd.read_csv(cfg.DATA / "primes_pays.csv").set_index("pays")
    mature = float(primes["prime_actions"].min())    # pays sans prime pays
    return {"secteurs": sect.set_index(["Region", "Secteur"]), "primes": primes,
            "prime_mature": mature}


def prime_du_pays(params: dict, pays: str) -> tuple[float, float]:
    """(prime actions totale, ecart de defaut) d'un pays de la plateforme."""
    p = params["primes"]
    nom = PAYS_DAMODARAN.get(pays, pays)
    if nom in p.index:
        r = p.loc[nom]
        return float(r["prime_actions"]), float(r["ecart_defaut"])
    return params["prime_mature"], 0.0
