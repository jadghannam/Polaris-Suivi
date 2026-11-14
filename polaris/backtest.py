# -*- coding: utf-8 -*-
"""
Backtest point-in-time du classement Novy-Marx.

    python -m polaris.backtest          # tous les univers utilises

Ajoute le 14/11/2026. Ce que le backtest fait, et ce qu'il ne fait pas :

- Rebalancement annuel le 1er juillet. A cette date, on ne retient pour chaque
  societe que le dernier exercice clos AU MOINS quatre mois plus tot : c'est le
  delai de publication. Un compte clos le 31/12 n'est donc utilise qu'a partir
  du 1er juillet suivant. Aucun chiffre posterieur a la date n'entre dans le
  calcul : c'est ce qui le rend point-in-time.
- Meme methode que le fonds : GP/A ajuste de la mediane du secteur, B/M,
  percentiles dans l'univers, moitie-moitie, planchers 40/30, garde-fou B/M.
  Les N premiers, equiponderes, tenus douze mois.
- Rendements mensuels en euros, dividendes compris (cours ajustes Yahoo),
  change compris.

Limites, ecrites dans la sortie pour que personne ne les oublie :

- pas de DCF inverse ni de veto qualitatif : trois exercices de flux sont
  necessaires au FCFF normatif, et Yahoo n'en donne que quatre ;
- biais du survivant : l'univers est celui d'aujourd'hui. Une societe sortie
  de l'indice depuis, ou disparue, n'y est pas. Le biais flatte la strategie
  ET l'univers equipondere de comparaison, d'ou l'interet de l'ecart entre
  les deux plutot que du niveau ;
- environ trois ans d'historique : trop court pour conclure sur une prime
  factorielle, assez pour verifier que la mecanique ne produit pas
  n'importe quoi. Les quintiles servent a ca.
"""

from __future__ import annotations

import datetime as dt
import json
import time

import numpy as np
import pandas as pd
import yfinance as yf

from . import config as cfg
from .collecte import place
from .journal import note

MOIS_REBALANCEMENT = 7
DECALAGE_PUBLICATION_MOIS = 4
TAUX_SANS_RISQUE_EUR = 0.025      # moyenne approximative de l'ESTR sur la periode
CHEMIN_PRIX = cfg.DATA / "prix_mensuels.csv"


# ------------------------------------------------------------- donnees -----
def prix_mensuels(tickers: list[str], forcer: bool = False) -> pd.DataFrame:
    """Clotures mensuelles ajustees (dividendes), devise de cotation, en cache
    une semaine dans data/prix_mensuels.csv (dates en lignes, titres en colonnes)."""
    if CHEMIN_PRIX.exists() and not forcer:
        p = pd.read_csv(CHEMIN_PRIX, index_col=0, parse_dates=True)
        age = (dt.date.today() - dt.date.fromtimestamp(CHEMIN_PRIX.stat().st_mtime)).days
        if age < 7 and set(tickers) <= set(p.columns):
            return p
    morceaux = []
    for i in range(0, len(tickers), 150):
        paquet = tickers[i:i + 150]
        for essai in range(3):
            try:
                d = yf.download(paquet, period="5y", interval="1mo", auto_adjust=True,
                                group_by="ticker", progress=False, threads=True)
                break
            except Exception as e:                      # noqa: BLE001
                note(f"backtest : paquet de cours en echec ({e})")
                time.sleep(5 * (essai + 1))
        else:
            continue
        cols = {}
        for t in paquet:
            try:
                s = d[t]["Close"] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
            except KeyError:
                continue
            s = s.dropna()
            if s.size:
                cols[t] = s / place(t)[1]
        if cols:
            morceaux.append(pd.DataFrame(cols))
        time.sleep(1)
    p = pd.concat(morceaux, axis=1) if morceaux else pd.DataFrame()
    p.index = pd.to_datetime(p.index).to_period("M").to_timestamp()
    p = p.groupby(level=0).last()
    p.to_csv(CHEMIN_PRIX)
    return p


def change_mensuel(devises: set[str]) -> pd.DataFrame:
    """Unites de devise par euro, fin de mois. EUR = 1."""
    autres = sorted(d for d in devises if d and d != "EUR")
    out = {}
    if autres:
        d = yf.download([f"EUR{x}=X" for x in autres], period="5y", interval="1mo",
                        progress=False)["Close"]
        if isinstance(d, pd.Series):
            d = d.to_frame(f"EUR{autres[0]}=X")
        for x in autres:
            if f"EUR{x}=X" in d.columns:
                out[x] = d[f"EUR{x}=X"]
    fx = pd.DataFrame(out)
    fx.index = pd.to_datetime(fx.index).to_period("M").to_timestamp()
    fx = fx.groupby(level=0).last().ffill()
    fx["EUR"] = 1.0
    return fx


# ------------------------------------------------------------ classement ---
def _pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) if s.notna().sum() >= 2 else pd.Series(np.nan, index=s.index)


def classer_a(date: pd.Timestamp, univers: pd.DataFrame, etats: pd.DataFrame,
              prix: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    """Classement tel qu'on aurait pu le faire a `date`, avec ce qui etait publie."""
    limite = (date - pd.DateOffset(months=DECALAGE_PUBLICATION_MOIS)).date().isoformat()
    e = etats[etats["cloture"] <= limite].sort_values("cloture").groupby("Ticker").tail(1)
    df = univers[["Ticker", "Societe", "Secteur", "Region"]].merge(e, on="Ticker", how="inner")
    mois = date - pd.DateOffset(months=1)                 # derniere cloture connue
    if mois not in prix.index:
        return pd.DataFrame()
    df["cours"] = df["Ticker"].map(prix.loc[mois])
    df["devise"] = df["Ticker"].map(lambda t: place(t)[0])
    fx_m = fx.loc[:mois].iloc[-1] if len(fx.loc[:mois]) else fx.iloc[0]
    df["fx_cours"] = df["devise"].map(fx_m)
    df["fx_etats"] = df["devise_etats"].fillna("EUR").map(fx_m)
    df["capitalisation"] = df["cours"] * df["actions_m"] / df["fx_cours"]
    gp = (df["ca"] - df["cogs"]) / df["fx_etats"]
    df["GP/A"] = gp / (df["actif"] / df["fx_etats"])
    df["B/M"] = (df["fonds_propres"] / df["fx_etats"]) / df["capitalisation"]
    df = df[df["GP/A"].notna() & df["B/M"].notna() & (df["capitalisation"] > 0)].copy()
    df["GP/A ajuste"] = df["GP/A"] - df.groupby("Secteur")["GP/A"].transform("median")
    bas, haut = cfg.BM_PLAUSIBLE
    plausible = (df["B/M"] >= bas) & (df["B/M"] <= haut)
    df = df[plausible | (df["B/M"] <= 0)].copy()
    df["r_rent"] = _pct(df["GP/A ajuste"])
    df["r_valo"] = _pct(df["B/M"])
    df["combine"] = cfg.POIDS_RENTABILITE * df["r_rent"] + cfg.POIDS_VALORISATION * df["r_valo"]
    df["plancher_ok"] = (df["r_rent"] >= cfg.PLANCHER_RENTABILITE) & \
                        (df["r_valo"] >= cfg.PLANCHER_VALORISATION)
    return df.sort_values("combine", ascending=False)


# ------------------------------------------------------------ rendements ---
def rendements_eur(prix: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    dev = {t: place(t)[0] for t in prix.columns}
    fx_al = fx.reindex(prix.index).ffill()
    eur = pd.DataFrame({t: prix[t] / fx_al[dev[t]] if dev[t] in fx_al else np.nan
                        for t in prix.columns}, index=prix.index)
    return eur.pct_change(fill_method=None)


def _panier(r: pd.DataFrame, titres: list[str], debut, fin,
            poids: list[float] | None = None) -> pd.Series:
    """Poids de depart (egaux par defaut), qui derivent ensuite (buy and hold)."""
    w = pd.Series(poids if poids is not None else [1.0] * len(titres), index=titres, dtype=float)
    w = w[[t for t in titres if t in r.columns]]
    bloc = r.loc[(r.index > debut) & (r.index <= fin), list(w.index)].fillna(0.0)
    if bloc.empty or w.empty or w.sum() <= 0:
        return pd.Series(dtype=float)
    valeur = (1 + bloc).cumprod() * (w / w.sum())
    total = valeur.sum(axis=1)
    return total / total.shift(1).fillna(1.0) - 1


def statistiques(r: pd.Series, ref: pd.Series | None) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    cumul = (1 + r).cumprod()
    ans = len(r) / 12
    rend = float(cumul.iloc[-1] ** (1 / ans) - 1) if ans > 0 else np.nan
    vol = float(r.std() * np.sqrt(12))
    out = {"rendement_annualise": rend, "volatilite": vol,
           "sharpe": (rend - TAUX_SANS_RISQUE_EUR) / vol if vol else None,
           "perte_max": float((cumul / cumul.cummax() - 1).min()),
           "performance_cumulee": float(cumul.iloc[-1] - 1), "mois": int(len(r))}
    if ref is not None:
        a = pd.concat([r, ref], axis=1, join="inner").dropna()
        if len(a) > 3:
            x, y = a.iloc[:, 1], a.iloc[:, 0]
            beta = float(np.cov(y, x)[0, 1] / x.var()) if x.var() else None
            ecart = y - x
            te = float(ecart.std() * np.sqrt(12))
            out.update(beta=beta, tracking_error=te,
                       ratio_information=float(ecart.mean() * 12 / te) if te else None,
                       mois_gagnants=float((ecart > 0).mean()))
    return out


# ------------------------------------------------------------- moteur -------
def lancer(univers: pd.DataFrame, nom: str, nb_lignes: int, indice: str,
           etats: pd.DataFrame, prix: pd.DataFrame, fx: pd.DataFrame,
           fx_indice: pd.DataFrame, repartition: str = "libre",
           poids_region: dict | None = None) -> dict:
    from .portefeuilles import choisir
    acwi = repartition == "acwi" and bool(poids_region) and univers["Region"].nunique() > 1
    r = rendements_eur(prix[[t for t in univers["Ticker"] if t in prix.columns]], fx)
    if r.empty:
        return {"erreur": "aucun cours"}
    debut_donnees, fin = r.index.min(), r.index.max()
    dates = []
    an = debut_donnees.year
    while True:
        d = pd.Timestamp(an, MOIS_REBALANCEMENT, 1)
        if d > fin:
            break
        if d > debut_donnees:
            dates.append(d)
        an += 1
    strat, equi, quint = [], [], {q: [] for q in range(1, 6)}
    compositions = []
    for i, d in enumerate(dates):
        if acwi:
            # Chaque region classee contre elle-meme, comme sur la plateforme.
            df = pd.concat([classer_a(d, g, etats, prix, fx)
                            for _, g in univers.groupby("Region")], ignore_index=True)
        else:
            df = classer_a(d, univers, etats, prix, fx)
        if len(df) < 20:
            continue
        suivant = dates[i + 1] - pd.DateOffset(months=1) if i + 1 < len(dates) else fin
        el = df[df["plancher_ok"]].sort_values("combine", ascending=False) \
               .assign(rang_combine=lambda x: x["combine"])
        retenus = choisir(el, nb_lignes, "acwi" if acwi else "libre", poids_region or {})
        compositions.append({"date": d.date().isoformat(), "nb_classes": int(len(df)),
                             "titres": [{"Ticker": t, "Societe": s, "Region": g} for t, s, g in
                                        zip(retenus["Ticker"], retenus["Societe"], retenus["Region"])]})
        debut = d - pd.DateOffset(months=1)
        strat.append(_panier(r, retenus["Ticker"].tolist(), debut, suivant,
                             retenus["poids_cible"].tolist()))
        equi.append(_panier(r, df["Ticker"].tolist(), debut, suivant))
        q = pd.qcut(df["combine"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1])
        for k in range(1, 6):
            quint[k].append(_panier(r, df.loc[q == k, "Ticker"].tolist(), debut, suivant))
    if not strat:
        return {"erreur": "historique de comptes insuffisant"}
    s = pd.concat(strat).sort_index()
    e = pd.concat(equi).sort_index()
    qs = {k: pd.concat(v).sort_index() for k, v in quint.items() if v}

    # Indice de comparaison, en euros.
    ref = None
    try:
        h = yf.download(indice, period="5y", interval="1mo", auto_adjust=True,
                        progress=False)["Close"]
        h = h.iloc[:, 0] if isinstance(h, pd.DataFrame) else h
        h.index = pd.to_datetime(h.index).to_period("M").to_timestamp()
        h = h.groupby(level=0).last()
        dev = cfg.INDICES.get(indice, ("", "EUR"))[1]
        if dev != "EUR" and dev in fx_indice:
            h = h / fx_indice[dev].reindex(h.index).ffill()
        ref = h.pct_change().reindex(s.index)
    except Exception as ex:                             # noqa: BLE001
        note(f"backtest : indice {indice} indisponible ({ex})")

    def serie(x):
        c = (1 + x.fillna(0)).cumprod()
        return [{"date": d.date().isoformat(), "v": float(v)} for d, v in c.items()]

    limites_acwi = ["Repartition ACWI : poids des regions d'aujourd'hui appliques a toute la periode "
                    "(l'historique des poids MSCI n'est pas disponible gratuitement)."] if acwi else []
    return {
        "univers": nom, "nb_lignes": nb_lignes, "indice": indice, "repartition": "acwi" if acwi else "libre",
        "indice_nom": cfg.INDICES.get(indice, (indice,))[0],
        "calcule_le": dt.date.today().isoformat(),
        "periode": [s.index.min().date().isoformat(), s.index.max().date().isoformat()],
        "rebalancements": compositions,
        "series": {"strategie": serie(s), "univers_equipondere": serie(e),
                   **({"indice": serie(ref)} if ref is not None else {}),
                   **{f"Q{k}": serie(v) for k, v in qs.items()}},
        "statistiques": {"strategie": statistiques(s, ref if ref is not None else e),
                         "univers_equipondere": statistiques(e, ref),
                         **({"indice": statistiques(ref, None)} if ref is not None else {}),
                         **{f"Q{k}": statistiques(v, None) for k, v in qs.items()}},
        "parametres": {"mois_rebalancement": MOIS_REBALANCEMENT,
                       "decalage_publication_mois": DECALAGE_PUBLICATION_MOIS,
                       "taux_sans_risque": TAUX_SANS_RISQUE_EUR,
                       "planchers": [cfg.PLANCHER_RENTABILITE, cfg.PLANCHER_VALORISATION]},
        "limites": [
            "Classement seul : ni DCF inverse ni veto qualitatif (historique de flux trop court).",
            "Biais du survivant : univers d'aujourd'hui, societes disparues absentes.",
            "Environ trois ans : trop court pour conclure sur une prime, utile pour verifier la mecanique.",
            "Cours ajustes des dividendes ; frais de transaction non deduits.",
        ] + limites_acwi,
    }


def tout(univers_complet: pd.DataFrame, combos: dict[str, tuple], poids_region: dict | None = None) -> None:
    """combos : cle -> (contraintes, nb_lignes, indice, repartition).
    Ecrit docs/backtest/<cle>.json."""
    from .portefeuilles import filtrer
    chemin = cfg.DATA / "etats_annuels.csv"
    if not chemin.exists():
        note("backtest : data/etats_annuels.csv absent, rien a calculer")
        return
    etats = pd.read_csv(chemin)
    tickers = sorted(set(univers_complet["Ticker"]) & set(etats["Ticker"]))
    prix = prix_mensuels(tickers)
    devises = {place(t)[0] for t in tickers} | set(etats["devise_etats"].dropna()) \
        | {v[1] for v in cfg.INDICES.values()}
    fx = change_mensuel(devises)
    dossier = cfg.DOCS / "backtest"
    dossier.mkdir(parents=True, exist_ok=True)
    for k, (contraintes, n, indice, *rep) in combos.items():
        u = filtrer(univers_complet, contraintes)
        res = lancer(u, k, n, indice, etats, prix, fx, fx,
                     rep[0] if rep else "libre", poids_region)
        (dossier / f"{k}.json").write_text(json.dumps(res, ensure_ascii=False,
                                                      separators=(",", ":")), encoding="utf-8")
        st = res.get("statistiques", {}).get("strategie", {})
        note(f"backtest {k} : {st.get('mois', 0)} mois, "
             f"rendement annualise {st.get('rendement_annualise', float('nan')):+.1%}"
             if st else f"backtest {k} : {res.get('erreur')}")


if __name__ == "__main__":
    from .journal import lignes
    u = pd.read_csv(cfg.DATA / "univers.csv")
    from .portefeuilles import allocation_acwi
    tout(u, {"polaris": (["europe", "stocktrak"], 26, "^STOXX", "libre"),
             "monde": ([], 40, "IUSQ.DE", "acwi")}, allocation_acwi().get("region", {}))
    print("\n".join(lignes()))
