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


# ------------------------------------------------ seances cloturees ---------
# Ajoute le 19/11/2026. Pendant les heures de bourse, la derniere ligne que
# renvoie Yahoo est la seance EN COURS : un passage a 14 h valorisait le fonds
# au cours intraday, et la valeur changeait a chaque passage. On ne garde la
# ligne du jour qu'une fois la place fermee (heure locale de cloture, avec une
# marge) ; sinon on prend la seance precedente, deja cloturee.
CLOTURES = {
    ("Europe/Paris", "17:45"): [".PA", ".AS", ".BR", ".MC", ".MI", ".LS", ".IR", ".HE", ".VI",
                                ".DE", ".F", ".ST", ".CO", ".OL", ".SW", ".VX", ".WA", ".AT",
                                ".PR", ".BD"],
    ("Europe/London", "16:45"): [".L"], ("America/New_York", "16:15"): ["", ".TO"],
    ("America/Sao_Paulo", "17:15"): [".SA"], ("America/Mexico_City", "15:15"): [".MX"],
    ("America/Santiago", "16:15"): [".SN"], ("America/Bogota", "16:15"): [".CL"],
    ("Asia/Tokyo", "15:45"): [".T"], ("Asia/Hong_Kong", "16:20"): [".HK"],
    ("Asia/Seoul", "15:45"): [".KS", ".KQ"], ("Asia/Taipei", "13:45"): [".TW", ".TWO"],
    ("Asia/Shanghai", "15:15"): [".SS", ".SZ"], ("Asia/Kolkata", "15:45"): [".NS", ".BO"],
    ("Australia/Sydney", "16:30"): [".AX"], ("Pacific/Auckland", "17:00"): [".NZ"],
    ("Asia/Singapore", "17:15"): [".SI"], ("Asia/Kuala_Lumpur", "17:15"): [".KL"],
    ("Asia/Bangkok", "16:45"): [".BK"], ("Asia/Jakarta", "16:15"): [".JK"],
    ("Asia/Manila", "15:15"): [".PS"], ("Asia/Riyadh", "15:30"): [".SR"],
    ("Asia/Qatar", "13:30"): [".QA"], ("Asia/Dubai", "15:15"): [".AE", ".AD", ".DU"],
    ("Asia/Kuwait", "13:00"): [".KW"], ("Africa/Johannesburg", "17:15"): [".JO"],
    ("Asia/Jerusalem", "17:45"): [".TA"], ("Europe/Istanbul", "18:15"): [".IS"],
    ("Africa/Cairo", "14:45"): [".CA"],
}
_PLACE_CLOTURE = {s: k for k, sufs in CLOTURES.items() for s in sufs}


def _cloture_de(ticker: str) -> tuple[str, str]:
    for s in sorted(_PLACE_CLOTURE, key=len, reverse=True):
        if s and ticker.endswith(s):
            return _PLACE_CLOTURE[s]
    return _PLACE_CLOTURE[""] if "." not in ticker else ("Europe/Paris", "17:45")


def seance_close(ticker: str, jour: dt.date, maintenant: dt.datetime | None = None) -> bool:
    """La seance `jour` (date locale de la place) est-elle terminee ?"""
    from zoneinfo import ZoneInfo
    tz, heure = _cloture_de(ticker)
    z = ZoneInfo(tz)
    now = (maintenant or dt.datetime.now(dt.timezone.utc)).astimezone(z)
    if jour < now.date():
        return True
    if jour > now.date():
        return False
    h, m = map(int, heure.split(":"))
    return now.time() >= dt.time(h, m)


# --------------------------------------------------------------- cours -------
_INCOMPLETES: dict[str, dt.date] = {}


def cloture_par_cotation(t: str, jour: dt.date) -> float | None:
    """Cloture officielle d'une seance par la cotation Yahoo (regularMarketPrice),
    acceptee seulement si son horodatage tombe sur cette seance, heure locale
    de la place. Un appel par titre : reserve aux titres qui comptent."""
    from zoneinfo import ZoneInfo
    try:
        i = yf.Ticker(t).info or {}
    except Exception:                                   # noqa: BLE001
        return None
    px, ts = i.get("regularMarketPrice"), i.get("regularMarketTime")
    if px is None or ts is None:
        return None
    tz, _ = _cloture_de(t)
    quand = dt.datetime.fromtimestamp(ts, dt.timezone.utc).astimezone(ZoneInfo(tz))
    if quand.date() == jour:
        return float(px)
    # La place a rouvert depuis : la cotation est celle du jour, et la cloture
    # precedente est celle de la seance cherchee, si c'etait bien la derniere
    # seance ouvree avant (pas de seance intercalee).
    if quand.date() > jour:
        prec = quand.date() - dt.timedelta(days=1)
        while prec.weekday() >= 5:
            prec -= dt.timedelta(days=1)
        if prec == jour and i.get("regularMarketPreviousClose") is not None:
            return float(i["regularMarketPreviousClose"])
    return None


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
        # Seance en cours : ecartee tant que la place n'a pas cloture.
        if not h.empty and not seance_close(t, h.index[-1].date()):
            h = h.iloc[:-1]
        # Seance cloturee SANS cloture dans la serie quotidienne (constate le
        # 20/11/2026 pour toute l'Europe : la ligne du 19/11 avait ouverture,
        # plus haut, plus bas et volume, mais pas de cloture, le lendemain
        # matin encore). On la signale pour la completer par la cotation.
        if not h.empty and "Close" in h.columns and pd.isna(h["Close"].iloc[-1]) \
                and h[["High", "Low"]].iloc[-1].notna().all():
            r = h.iloc[-1]
            _INCOMPLETES[t] = (h.index[-1].date(), {k: float(r[k]) for k in ("Open", "High", "Low", "Volume")
                                                    if k in h.columns and pd.notna(r[k])})
        if "Close" in h.columns:
            h = h[h["Close"].notna()]
        # Dans un telechargement groupe, la ligne peut meme manquer en entier :
        # on compare au calendrier. Si la derniere seance qui devrait etre
        # cloturee n'est pas dans les donnees, on la signale aussi. Un jour
        # ferie est sans risque : la cotation porterait alors la date de la
        # seance precedente et serait refusee.
        attendue = derniere_seance(t)
        if not h.empty and h.index[-1].date() < attendue and t not in _INCOMPLETES:
            _INCOMPLETES[t] = (attendue, {})
        return h if not h.empty else None
    except Exception:                                   # noqa: BLE001
        return None


def derniere_seance(t: str, maintenant: dt.datetime | None = None) -> dt.date:
    """Date locale de la derniere seance cloturee de la place (jours ouvres)."""
    from zoneinfo import ZoneInfo
    tz, _ = _cloture_de(t)
    j = (maintenant or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(tz)).date()
    for _ in range(7):
        if j.weekday() < 5 and seance_close(t, j, maintenant):
            return j
        j -= dt.timedelta(days=1)
    return j


def cours_du_jour(tickers: list[str], derniers: pd.DataFrame | None = None,
                  prioritaires: set[str] | None = None) -> pd.DataFrame:
    """Voir _cours_du_jour. `prioritaires` : titres dont une cloture absente
    de la serie quotidienne est completee par la cotation (univers du fonds,
    lignes detenues). Pour les autres, la seance precedente reste retenue."""
    _INCOMPLETES.clear()
    df = _cours_du_jour(tickers, derniers)
    if df.empty or not _INCOMPLETES:
        return df
    a_completer = [t for t in _INCOMPLETES if t in (prioritaires or set())]
    faits = []
    for t in a_completer:
        jour, ohlv = _INCOMPLETES[t]
        px = cloture_par_cotation(t, jour)
        if px is None:
            continue
        devise, diviseur = place(t)
        i = df.index[df["Ticker"] == t]
        if len(i):
            # La seance du jour, complete : sa cloture par la cotation, et
            # ouverture, extremes et volume de la ligne quotidienne.
            df.loc[i, ["date", "cours"]] = [jour.isoformat(), px / diviseur]
            for k, col in (("Open", "ouverture"), ("High", "haut"), ("Low", "bas")):
                if k in ohlv:
                    df.loc[i, col] = ohlv[k] / diviseur
            if "Volume" in ohlv:
                df.loc[i, "volume"] = ohlv["Volume"]
            faits.append(t)
        time.sleep(0.2)
    reste = len(_INCOMPLETES) - len(faits)
    note(f"clotures absentes de la serie quotidienne Yahoo : {len(_INCOMPLETES)} titres ; "
         f"{len(faits)} completees par la cotation"
         + (f", {reste} gardent la seance precedente" if reste else ""))
    return df


def _cours_du_jour(tickers: list[str], derniers: pd.DataFrame | None = None
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


CHEMIN_CHANGE = cfg.DATA / "taux_change.csv"
BCE_CHANGE = ("https://data-api.ecb.europa.eu/service/data/EXR/D.{devises}.EUR.SP00.A"
              "?lastNObservations=1&format=csvdata")


def _change_bce(devises: list[str]) -> dict[str, tuple[float, str]]:
    """Taux de reference de la BCE (un par jour ouvre, vers 16 h) : la
    reference officielle pour valoriser en euros, stable sur la journee."""
    import io
    import requests
    out = {}
    try:
        r = requests.get(BCE_CHANGE.format(devises="+".join(devises)), timeout=60,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text))
        for x in d.itertuples():
            if pd.notna(x.OBS_VALUE):
                out[x.CURRENCY] = (float(x.OBS_VALUE), str(x.TIME_PERIOD))
    except Exception as e:                              # noqa: BLE001
        note(f"taux de reference BCE indisponibles : {e}")
    return out


def taux_de_change() -> dict[str, float]:
    """Unites de devise par euro, comme dans la base (1 EUR = 0,86 GBP).

    19/11/2026 : trois sources, dans l'ordre.
      1. Taux de reference de la BCE (publies une fois par jour) ;
      2. Yahoo pour les devises que la BCE ne publie pas, en ne gardant que la
         derniere journee CLOTUREE (pas le taux de l'instant) ;
      3. le dernier taux connu (data/taux_change.csv) si les deux se taisent.
    Corrige le jour ou Yahoo n'a pas renvoye la couronne suedoise : les trois
    lignes suedoises avaient disparu de la valeur du fonds (921 kEUR affiches
    au lieu d'un million). Une devise qui manque ne fait plus disparaitre de
    ligne : elle garde son dernier taux, et le journal le dit.
    """
    taux, source = {"EUR": 1.0}, {"EUR": ("EUR", "")}
    bce = _change_bce(list(cfg.DEVISES))
    for d, (v, jour) in bce.items():
        taux[d], source[d] = v, ("BCE", jour)
    reste = [d for d in cfg.DEVISES if d not in taux]
    if reste:
        paires = [f"EUR{d}=X" for d in reste]
        try:
            h = yf.download(paires, period="7d", progress=False)["Close"]
            if isinstance(h, pd.Series):
                h = h.to_frame(paires[0])
            for d, p in zip(reste, paires):
                s = h[p].dropna() if p in h.columns else pd.Series(dtype=float)
                # Journee en cours ecartee : on veut un taux arrete.
                if len(s) > 1 and s.index[-1].date() >= dt.datetime.now(dt.timezone.utc).date():
                    s = s.iloc[:-1]
                if not s.empty:
                    taux[d], source[d] = float(s.iloc[-1]), ("Yahoo", s.index[-1].date().isoformat())
        except Exception as e:                          # noqa: BLE001
            note(f"taux de change Yahoo indisponibles : {e}")
    connus = pd.read_csv(CHEMIN_CHANGE) if CHEMIN_CHANGE.exists() else pd.DataFrame(
        columns=["devise", "taux", "source", "date"])
    anciens = {r.devise: r for r in connus.itertuples()}
    repris = []
    for d in cfg.DEVISES:
        if d not in taux and d in anciens:
            taux[d], source[d] = float(anciens[d].taux), ("dernier connu", str(anciens[d].date))
            repris.append(f"{d} ({anciens[d].date})")
    if repris:
        note(f"ATTENTION taux de change repris du dernier passage : {', '.join(repris)}")
    absents = [d for d in cfg.DEVISES if d not in taux]
    if absents:
        note(f"ATTENTION taux manquants, sans valeur connue : {', '.join(absents)}")
    pd.DataFrame([{"devise": d, "taux": v, "source": source[d][0], "date": source[d][1]}
                  for d, v in taux.items() if d != "EUR"]).to_csv(CHEMIN_CHANGE, index=False)
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
