# -*- coding: utf-8 -*-
"""
Taux sans risque 10 ans par devise, lus automatiquement.

Ajoute le 19/11/2026. Jusque-la, les taux hors dollar de config.py etaient des
ordres de grandeur saisis a la main, sans source : verifies ce jour contre
l'OCDE, plusieurs etaient faux de plus d'un point (yen 1,50 % saisi pour
2,76 %, real 13,50 % pour 9,29 %). Sources, toutes gratuites et sans cle :

  - Yahoo  ^TNX      Treasury 10 ans, quotidien (USD ; HKD et monnaies du Golfe
                     arrimees au dollar en prennent le taux) ;
  - BCE    YC        courbe AAA de la zone euro, 10 ans, quotidien : reference
                     de l'euro pour mesurer les ecarts ;
  - BCE    IRS       taux longs des pays de l'UE hors euro, mensuel ;
  - OCDE   IRLT      taux longs des pays membres et partenaires, mensuel.

Un taux absent de ces sources (Taiwan, une partie de l'Asie du Sud-Est,
Egypte, Perou, Turquie) reste celui de config.py, signale « saisi a la main »
avec un rappel annuel sur la page.

Les taux sont mis en cache dans data/taux_sans_risque.csv et relus chaque
samedi (les series BCE et OCDE sont mensuelles) ; ^TNX est relu chaque soir.
Le fonds n'en depend pas : ses devises sont europeennes et sa convention de
WACC est figee depuis septembre.
"""

from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import requests

from . import config as cfg
from .journal import note

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
CHEMIN = cfg.DATA / "taux_sans_risque.csv"

BCE_COURBE = ("https://data-api.ecb.europa.eu/service/data/YC/"
              "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=5&format=csvdata")
BCE_UE = {"PLN": "PL", "HUF": "HU", "CZK": "CZ", "SEK": "SE", "DKK": "DK"}
BCE_UE_URL = ("https://data-api.ecb.europa.eu/service/data/IRS/M.{pays}.L.L40.CI.0000..N.Z"
              "?lastNObservations=1&format=csvdata")
OCDE = {"JPY": "JPN", "KRW": "KOR", "CAD": "CAN", "AUD": "AUS", "NZD": "NZL", "ILS": "ISR",
        "MXN": "MEX", "CLP": "CHL", "COP": "COL", "GBP": "GBR", "CHF": "CHE", "NOK": "NOR",
        "INR": "IND", "BRL": "BRA", "ZAR": "ZAF", "CNY": "CHN", "IDR": "IDN", "TRY": "TUR"}
OCDE_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/"
            "{pays}.M.IRLT.PA.....?lastNObservations=1&format=csvfilewithlabels")
ARRIMEES_USD = ("HKD", "SAR", "AED", "QAR", "KWD")
# Une serie dont la derniere observation a plus de 6 mois n'est plus un taux
# du jour (l'Indonesie s'arrete a decembre 2024 dans l'OCDE).
FRAICHEUR_MAX_JOURS = 190


def _get(u: str) -> requests.Response:
    """Deux essais : le serveur de la BCE repond parfois lentement."""
    for essai in range(2):
        try:
            r = requests.get(u, headers=UA, timeout=60)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if essai:
                raise


def _frais(periode: str) -> bool:
    try:
        d = pd.Period(periode).end_time.date()
    except Exception:                                   # noqa: BLE001
        return False
    return (dt.date.today() - d).days <= FRAICHEUR_MAX_JOURS


def lire_sources() -> list[dict]:
    """Toutes les sources, une ligne par devise : taux decimal, source, date."""
    out = []
    try:
        d = pd.read_csv(io.StringIO(_get(BCE_COURBE).text)).dropna(subset=["OBS_VALUE"])
        out.append({"devise": "EUR", "taux": float(d["OBS_VALUE"].iloc[-1]) / 100,
                    "source": "BCE, courbe AAA zone euro 10 ans", "date": str(d["TIME_PERIOD"].iloc[-1])})
    except Exception as e:                              # noqa: BLE001
        note(f"taux BCE (euro) indisponible : {e}")
    try:
        u = BCE_UE_URL.format(pays="+".join(BCE_UE.values()))
        d = pd.read_csv(io.StringIO(_get(u).text))
        inv = {v: k for k, v in BCE_UE.items()}
        for r in d.itertuples():
            if r.REF_AREA in inv and _frais(r.TIME_PERIOD):
                out.append({"devise": inv[r.REF_AREA], "taux": float(r.OBS_VALUE) / 100,
                            "source": "BCE, taux long UE", "date": str(r.TIME_PERIOD)})
    except Exception as e:                              # noqa: BLE001
        note(f"taux BCE (UE hors euro) indisponibles : {e}")
    try:
        d = pd.read_csv(io.StringIO(_get(OCDE_URL.format(pays="+".join(OCDE.values()))).text))
        inv = {v: k for k, v in OCDE.items()}
        for r in d.itertuples():
            if r.REF_AREA in inv and _frais(r.TIME_PERIOD):
                out.append({"devise": inv[r.REF_AREA], "taux": float(r.OBS_VALUE) / 100,
                            "source": "OCDE, taux long", "date": str(r.TIME_PERIOD)})
    except Exception as e:                              # noqa: BLE001
        note(f"taux OCDE indisponibles : {e}")
    return out


def taux_du_jour(usd: float | None) -> pd.DataFrame:
    """Table complete devise -> taux, avec la source. Relit BCE et OCDE le
    samedi ou si le cache manque ; le dollar du jour vient de ^TNX."""
    cache = pd.read_csv(CHEMIN) if CHEMIN.exists() else pd.DataFrame()
    if cache.empty or dt.date.today().weekday() == cfg.JOUR_FONDAMENTAUX:
        lus = pd.DataFrame(lire_sources())
        if not lus.empty:
            # Une source muette ne fait pas disparaitre le dernier taux connu.
            cache = pd.concat([cache, lus], ignore_index=True) \
                if not cache.empty else lus
            cache = cache.drop_duplicates("devise", keep="last")
    lignes = {r.devise: r._asdict() for r in cache.itertuples(index=False)} if not cache.empty else {}
    if usd is not None:
        for dv in ("USD",) + ARRIMEES_USD:
            lignes[dv] = {"devise": dv, "taux": usd,
                          "source": "Yahoo ^TNX" + ("" if dv == "USD" else " (devise arrimee au dollar)"),
                          "date": dt.date.today().isoformat()}
    for dv, t in cfg.TAUX_SANS_RISQUE_DEVISE.items():
        if dv not in lignes:
            lignes[dv] = {"devise": dv, "taux": t, "source": "saisi a la main (config.py)",
                          "date": cfg.DATE_TAUX_MANUELS}
    table = pd.DataFrame(list(lignes.values()))[["devise", "taux", "source", "date"]]
    table.sort_values("devise").to_csv(CHEMIN, index=False)
    return table
