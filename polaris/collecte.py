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

Lecon du 05/11/2026 : la premiere version interrogeait Yahoo titre par titre,
soit pres de quatre cents appels pour un univers de 192 valeurs. Le serveur
nous a coupes au bout de 64. Depuis, tout passe par un telechargement groupe,
la devise se deduit du suffixe du ticker au lieu d'un appel reseau, et le
nombre d'actions est lu dans le fichier de fondamentaux. On est passe de
quatre cents appels a trois.
"""

from __future__ import annotations

import datetime as dt
import time

import numpy as np
import pandas as pd
import yfinance as yf

from . import config as cfg
from .journal import note

# --------------------------------------------------- devises par place ------
# Yahoo cote certaines places dans la SOUS-UNITE de la devise : Londres en
# pence. Sans cette conversion, les britanniques ressortent avec un
# book-to-market cent fois trop faible et sont toutes eliminees sans que rien
# ne le signale. C'est l'erreur de septembre, puis celle du 5 novembre.
PLACES = {
    ".L": ("GBP", 100.0),    # Londres cote en pence
    ".PA": ("EUR", 1.0), ".AS": ("EUR", 1.0), ".BR": ("EUR", 1.0),
    ".MC": ("EUR", 1.0), ".MI": ("EUR", 1.0), ".LS": ("EUR", 1.0),
    ".IR": ("EUR", 1.0), ".HE": ("EUR", 1.0), ".VI": ("EUR", 1.0),
    ".DE": ("EUR", 1.0), ".F": ("EUR", 1.0),
    ".ST": ("SEK", 1.0), ".CO": ("DKK", 1.0), ".OL": ("NOK", 1.0),
    ".SW": ("CHF", 1.0), ".VX": ("CHF", 1.0), ".WA": ("PLN", 1.0),
    ".AT": ("EUR", 1.0),
    # Univers mondial, 14/11/2026
    ".T": ("JPY", 1.0), ".HK": ("HKD", 1.0), ".KS": ("KRW", 1.0),
    # MSCI ACWI, 14/11/2026. Trois places cotent, comme Londres, dans une
    # SOUS-UNITE : Johannesburg en cents (ZAc), Tel-Aviv en agorot (ILA),
    # Koweit en fils (KWF, millieme de dinar). Sans diviseur, le B/M de ces
    # titres serait cent ou mille fois trop faible.
    ".JO": ("ZAR", 100.0), ".TA": ("ILS", 100.0), ".KW": ("KWD", 1000.0),
    ".TO": ("CAD", 1.0), ".AX": ("AUD", 1.0), ".SI": ("SGD", 1.0), ".NZ": ("NZD", 1.0),
    ".TWO": ("TWD", 1.0), ".TW": ("TWD", 1.0), ".NS": ("INR", 1.0), ".BO": ("INR", 1.0),
    ".KQ": ("KRW", 1.0), ".SS": ("CNY", 1.0), ".SZ": ("CNY", 1.0),
    ".SA": ("BRL", 1.0), ".SR": ("SAR", 1.0), ".MX": ("MXN", 1.0), ".KL": ("MYR", 1.0),
    ".BK": ("THB", 1.0), ".JK": ("IDR", 1.0), ".PS": ("PHP", 1.0), ".IS": ("TRY", 1.0),
    ".QA": ("QAR", 1.0), ".AE": ("AED", 1.0), ".AD": ("AED", 1.0), ".DU": ("AED", 1.0),
    ".SN": ("CLP", 1.0), ".BD": ("HUF", 1.0), ".PR": ("CZK", 1.0), ".CL": ("COP", 1.0),
    ".CA": ("EGP", 1.0),
}


def place(ticker: str) -> tuple[str, float]:
    """Devise de cotation et diviseur, deduits du suffixe du ticker.

    Sans suffixe, c'est une valeur americaine, donc en dollars. Jusqu'au
    14/11/2026 le repli etait l'euro : tous les titres de l'univers portaient
    un suffixe, et ce repli n'avait jamais servi.
    """
    for suffixe, (devise, diviseur) in PLACES.items():
        if ticker.endswith(suffixe):
            return devise, diviseur
    if "." not in ticker:
        return "USD", 1.0
    return "EUR", 1.0


# --------------------------------------------------------------- cours -------
def _extraire(data, t: str) -> pd.DataFrame | None:
    """Sort le sous-tableau d'un titre d'un telechargement groupe."""
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if t not in data.columns.get_level_values(0):
                return None
            h = data[t].dropna(how="all")
        else:
            h = data.dropna(how="all")
        # Lecon du 10/11/2026 : en soiree, Yahoo renvoie pour les places
        # continentales une ligne du jour avec ouverture, plus haut, plus bas et
        # volume, mais SANS cloture. Prise pour la derniere ligne, elle donnait
        # un cours vide compte comme frais : 17 lignes sur 26 sortaient de la
        # valeur du fonds. Une ligne sans cloture n'est pas un cours.
        if "Close" in h.columns:
            h = h[h["Close"].notna()]
        return h if not h.empty else None
    except Exception:                                   # noqa: BLE001
        return None


def cours_du_jour(tickers: list[str], derniers: pd.DataFrame | None = None
                  ) -> pd.DataFrame:
    """Dernier cours, volume et amplitude du jour, en devise de cotation.

    Un seul telechargement groupe pour tout l'univers, puis un second essai
    pour les manquants. Un titre toujours absent conserve son dernier cours
    connu, marque comme perime : une donnee manquante ne doit JAMAIS ressembler
    a un signal de vente.
    """
    lignes, manquants = [], []
    data = None
    for essai in range(3):
        try:
            data = yf.download(tickers, period="7d", group_by="ticker",
                               auto_adjust=False, progress=False,
                               threads=True)
            break
        except Exception as e:                          # noqa: BLE001
            note(f"telechargement groupe en echec (essai {essai + 1}) : {e}")
            time.sleep(5 * (essai + 1))

    for t in tickers:
        h = _extraire(data, t) if data is not None else None
        if h is None:
            manquants.append(t)
            continue
        d = h.iloc[-1]
        devise, diviseur = place(t)
        lignes.append({
            "Ticker": t, "date": h.index[-1].date().isoformat(),
            "cours": float(d["Close"]) / diviseur,
            "ouverture": float(d["Open"]) / diviseur,
            "haut": float(d["High"]) / diviseur,
            "bas": float(d["Low"]) / diviseur,
            "volume": float(d["Volume"]), "devise": devise, "perime": False,
        })

    # Second essai, par petits paquets et sans precipitation.
    if manquants:
        note(f"second essai pour {len(manquants)} titres manquants")
        for i in range(0, len(manquants), 25):
            paquet = manquants[i:i + 25]
            try:
                d2 = yf.download(paquet, period="7d", group_by="ticker",
                                 auto_adjust=False, progress=False)
                for t in list(paquet):
                    h = _extraire(d2, t)
                    if h is None:
                        continue
                    d = h.iloc[-1]
                    devise, diviseur = place(t)
                    lignes.append({
                        "Ticker": t, "date": h.index[-1].date().isoformat(),
                        "cours": float(d["Close"]) / diviseur,
                        "ouverture": float(d["Open"]) / diviseur,
                        "haut": float(d["High"]) / diviseur,
                        "bas": float(d["Low"]) / diviseur,
                        "volume": float(d["Volume"]), "devise": devise,
                        "perime": False,
                    })
                    manquants.remove(t)
            except Exception as e:                      # noqa: BLE001
                note(f"paquet de rattrapage en echec : {e}")
            time.sleep(2)

    # Dernier recours : le cours connu la veille.
    if manquants and derniers is not None and not derniers.empty:
        connus = derniers.set_index("Ticker")
        for t in list(manquants):
            if t in connus.index:
                l = connus.loc[t].to_dict()
                l.update({"Ticker": t, "perime": True})
                lignes.append(l)
                manquants.remove(t)
        note(f"cours perimes reutilises : {len(derniers)} disponibles")
    if manquants:
        note(f"AUCUN cours pour {len(manquants)} titres : "
             f"{', '.join(manquants[:10])}{' ...' if len(manquants) > 10 else ''}")

    df = pd.DataFrame(lignes)
    if df.empty:
        return df
    df["negociable"] = (df["volume"].fillna(0) >= cfg.VOLUME_MIN_JOUR) & \
                       (df["haut"].fillna(0) > df["bas"].fillna(0)) & \
                       (~df["perime"].fillna(False))
    return df


def taux_de_change() -> dict[str, float]:
    """Unites de devise par euro, comme dans la base (1 EUR = 0,86 GBP)."""
    taux = {"EUR": 1.0}
    paires = [f"EUR{d}=X" for d in cfg.DEVISES]
    try:
        h = yf.download(paires, period="5d", progress=False)["Close"]
        for d, p in zip(cfg.DEVISES, paires):
            s = h[p].dropna() if p in h.columns else pd.Series(dtype=float)
            if not s.empty:
                taux[d] = float(s.iloc[-1])
    except Exception as e:                              # noqa: BLE001
        note(f"taux de change groupes indisponibles : {e}")
    absents = [d for d in cfg.DEVISES if d not in taux]
    if absents:
        note(f"ATTENTION taux manquants : {', '.join(absents)}")
    return taux


def taux_sans_risque() -> dict[str, float]:
    """Taux 10 ans lisibles sur Yahoo, en decimal.

    Seul le Treasury americain y est (^TNX, cote en pourcent). Yahoo ne sert ni
    le JGB, ni le KTB, ni le Bund : ceux-la restent dans config.py. Le dollar de
    Hong Kong est arrime au dollar americain : il en prend le taux.
    """
    out = {}
    try:
        h = yf.Ticker("^TNX").history(period="10d")["Close"].dropna()
        if not h.empty and 0 < float(h.iloc[-1]) < 20:
            out["USD"] = out["HKD"] = float(h.iloc[-1]) / 100
    except Exception as e:                              # noqa: BLE001
        note(f"taux sans risque americain indisponible : {e}")
    return out


def indice(symbole: str = cfg.BENCHMARK, depuis: str = cfg.DATE_LANCEMENT) -> pd.Series:
    """Serie de cloture de l'indice de reference depuis le lancement."""
    try:
        h = yf.Ticker(symbole).history(start=depuis)
    except Exception as e:                              # noqa: BLE001
        note(f"indice {symbole} indisponible : {e}")
        return pd.Series(dtype=float)
    if h.empty:
        note(f"indice {symbole} vide")
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


def _ratio(df: pd.DataFrame, cles: list[str], col) -> float | None:
    """Comme _val, sans conversion en millions (taux, ratios)."""
    for k in cles:
        if k in df.index:
            v = df.loc[k, col]
            if pd.notna(v):
                return float(v)
    return None


def _etats_long(t: str, inc, bil, cf, devise: str) -> list[dict]:
    """Un exercice par ligne, tous ceux que Yahoo publie (quatre en general).

    Sert au backtest point-in-time et a la fiche d'analyse : on garde la date
    de cloture de chaque exercice pour ne jamais utiliser un compte avant
    qu'il ait pu etre publie.
    """
    out = []
    for col in inc.columns:
        cb = col if col in bil.columns else None
        cc = col if (cf is not None and not cf.empty and col in cf.columns) else None
        l = {"Ticker": t, "cloture": pd.Timestamp(col).date().isoformat(),
             "devise_etats": devise,
             "ca": _val(inc, ["Total Revenue", "Operating Revenue"], col),
             "cogs": _val(inc, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], col),
             "ebit": _val(inc, ["EBIT", "Operating Income"], col),
             "taux_impot": _ratio(inc, ["Tax Rate For Calcs"], col)}
        if cb is not None:
            l.update(actif=_val(bil, ["Total Assets"], cb),
                     fonds_propres=_val(bil, ["Stockholders Equity", "Common Stock Equity"], cb),
                     dette=_val(bil, ["Total Debt"], cb),
                     tresorerie=_val(bil, ["Cash And Cash Equivalents",
                                           "Cash Cash Equivalents And Short Term Investments"], cb),
                     minoritaires=_val(bil, ["Minority Interest"], cb),
                     actions_m=_val(bil, ["Ordinary Shares Number", "Share Issued"], cb))
        if cc is not None:
            capex = _val(cf, ["Capital Expenditure"], cc)
            bfr = _val(cf, ["Change In Working Capital"], cc)
            l.update(da=_val(cf, ["Depreciation And Amortization",
                                  "Depreciation Amortization Depletion"], cc),
                     capex=abs(capex) if capex is not None else None,
                     dbfr=-bfr if bfr is not None else None)
        out.append(l)
    return out


def fondamentaux(tickers: list[str], etats: list | None = None) -> pd.DataFrame:
    """Comptes du dernier exercice publie, en millions de devise de publication.

    Les conventions de signe de Yahoo sont redressees ici, une fois pour
    toutes : les capex sortent en negatif, la variation du BFR est inversee.
    La devise de publication voyage avec les montants : sans elle, les chiffres
    collectes se melangeraient aux valeurs de depart, qui sont en euros.

    Si `etats` est une liste, chaque exercice publie y est ajoute (format long,
    voir _etats_long). Depuis le 14/11/2026, la ligne porte aussi le nombre
    d'actions et le taux d'impot : un titre nouveau dans l'univers n'avait
    sinon ni capitalisation ni DCF.
    """
    lignes = []
    for i, t in enumerate(tickers):
        try:
            y = yf.Ticker(t)
            inc, bil, cf = y.income_stmt, y.balance_sheet, y.cashflow
            if inc.empty or bil.empty:
                note(f"etats financiers absents pour {t}")
                continue
            c, cb = inc.columns[0], bil.columns[0]
            try:
                devise_etats = (y.info or {}).get("financialCurrency", "EUR")
            except Exception:                           # noqa: BLE001
                devise_etats = None
            if etats is not None:
                etats.extend(_etats_long(t, inc, bil, cf, devise_etats))
            l = {
                "Ticker": t,
                "ca": _val(inc, ["Total Revenue", "Operating Revenue"], c),
                "cogs": _val(inc, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], c),
                "actif": _val(bil, ["Total Assets"], cb),
                "fonds_propres": _val(bil, ["Stockholders Equity",
                                            "Common Stock Equity"], cb),
                "minoritaires": _val(bil, ["Minority Interest"], cb) or 0.0,
                "mises_en_equivalence": _val(
                    bil, ["Investmentin Financial Assets",
                          "Investments In Other Ventures Under Equity Method"], cb) or 0.0,
                "devise_etats": devise_etats or "EUR",
                "actions_m": _val(bil, ["Ordinary Shares Number", "Share Issued"], cb),
                "taux_impot": _ratio(inc, ["Tax Rate For Calcs"], c),
            }
            dette = _val(bil, ["Total Debt"], cb)
            tresorerie = _val(bil, ["Cash And Cash Equivalents",
                                    "Cash Cash Equivalents And Short Term Investments"], cb)
            if dette is not None:
                l["dette_nette"] = dette - (tresorerie or 0.0)
            if l["ca"] is not None and l["cogs"] is not None:
                l["profit_brut"] = l["ca"] - l["cogs"]
            for k, suf in enumerate(["n", "n1", "n2"]):
                if k < len(inc.columns):
                    cc = inc.columns[k]
                    l[f"ebit_{suf}"] = _val(inc, ["EBIT", "Operating Income"], cc)
                if cf is not None and not cf.empty and k < len(cf.columns):
                    cc = cf.columns[k]
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
        except Exception as e:                          # noqa: BLE001
            note(f"echec fondamentaux {t} : {e}")
        if i % 20 == 19:
            time.sleep(1)       # on ne bouscule pas le serveur
    return pd.DataFrame(lignes)


# ----------------------------------------------------------- orchestration ---
def doit_rafraichir_fondamentaux(aujourdhui: dt.date | None = None) -> bool:
    j = aujourdhui or dt.date.today()
    return j.weekday() == cfg.JOUR_FONDAMENTAUX
