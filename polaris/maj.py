# -*- coding: utf-8 -*-
"""
Mise a jour quotidienne. Point d'entree unique.

    python -m polaris.maj

Enchainement : cours du jour -> classement -> DCF inverse -> zones et
persistance -> remplacants -> ecriture de docs/data.json, que la page de suivi
lit telle quelle. Les fondamentaux ne sont retelecharges qu'une fois par
semaine (voir collecte.doit_rafraichir_fondamentaux).
"""

from __future__ import annotations

import datetime as dt
import json
import zlib

import numpy as np
import pandas as pd

from . import classement as cl
from . import collecte, config as cfg, dcf, signaux as sg
from . import obligations as ob
from . import portefeuilles as pfs
from . import positions as ps
from .journal import note, lignes, vider


def _lire(nom):
    return pd.read_csv(cfg.DATA / nom)


def _nan(o):
    """json ne sait pas serialiser NaN de facon lisible : on met None."""
    if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
        return None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def _propre(d: dict) -> dict:
    return {k: _nan(v) for k, v in d.items()}


COLONNES_RANG = ["ca", "cogs", "profit_brut", "actif", "fonds_propres", "devise_etats"]
# Montants du DCF, tenus en euros dans fondamentaux_dcf.csv.
MONTANTS_DCF = (["dette_nette", "minoritaires", "mises_en_equivalence"]
                + [f"{k}_{s}" for k in ("ebit", "da", "capex", "dbfr") for s in ("n2", "n1", "n")])


def _remplacer(nom: str, neuf: pd.DataFrame, cles=("Ticker",)) -> None:
    """Remplace (ou ajoute) les lignes de `neuf` dans data/<nom>."""
    chemin = cfg.DATA / nom
    ancien = pd.read_csv(chemin) if chemin.exists() else pd.DataFrame(columns=neuf.columns)
    tout = pd.concat([ancien, neuf], ignore_index=True)
    tout = tout.drop_duplicates(subset=list(cles), keep="last")
    cols = list(ancien.columns) + [c for c in neuf.columns if c not in ancien.columns]
    tout[cols].to_csv(chemin, index=False)


def rafraichir_monde(tickers: list[str], taux: dict) -> None:
    """Comptes complets des titres hors fonds : rang (devise de publication,
    avec sa devise), DCF (converti en euros), et exercices en format long."""
    etats: list = []
    neufs = collecte.fondamentaux(tickers, etats)
    if neufs.empty:
        note(f"univers mondial : aucun compte lu sur {len(tickers)} titres")
        return
    _remplacer("fondamentaux_rang.csv", neufs.reindex(columns=["Ticker"] + COLONNES_RANG))
    div = neufs["devise_etats"].fillna("EUR").map(lambda d: taux.get(d, np.nan))
    d = neufs.reindex(columns=["Ticker", "taux_impot", "actions_m"] + MONTANTS_DCF).copy()
    for c in MONTANTS_DCF:
        d[c] = pd.to_numeric(d[c], errors="coerce") / div
    _remplacer("fondamentaux_dcf.csv", d[div.notna()])
    if etats:
        _remplacer("etats_annuels.csv", pd.DataFrame(etats), cles=("Ticker", "cloture"))
    note(f"univers mondial : comptes lus pour {len(neufs)} / {len(tickers)} titres")


def main() -> None:
    vider()
    aujourdhui = dt.date.today()
    note(f"mise a jour du {aujourdhui.isoformat()}")

    # Univers mondial (14/11/2026) et univers du fonds. Tout ce qui suit
    # jusqu'a l'ecriture de data.json ne voit QUE l'univers du fonds, filtre
    # par ses deux contraintes : c'est ce qui le garde identique a ce qu'il
    # etait avant l'extension. Les portefeuilles personnels sont calcules a
    # la fin, a part (polaris/portefeuilles.py).
    univers_complet = _lire("univers.csv")
    univers = pfs.filtrer(univers_complet, cfg.CONTRAINTES_POLARIS)
    note(f"univers : {len(univers_complet)} titres, dont {len(univers)} dans celui du fonds")
    # Blocages manuels : titres que StockTrak ne permet pas d'acheter en
    # pratique (volume insuffisant, symbole absent, cours aberrant). Les
    # calculs restent faits et visibles, mais le titre n'est plus proposable.
    chemin_bloc = cfg.DATA / "blocages.csv"
    blocages = pd.read_csv(chemin_bloc) if chemin_bloc.exists() else pd.DataFrame(
        columns=["Ticker", "date", "motif"])
    bloques = set(blocages["Ticker"].dropna())
    if bloques:
        note(f"blocages manuels actifs : {len(bloques)} "
             f"-> {', '.join(sorted(bloques))}")
    # Vetos qualitatifs : exclusions decidees sur un fait etabli (fusion,
    # offre, contentieux), datees. Le titre reste classe et visible, mais il
    # n'est jamais propose en remplacement. On retire la ligne du fichier le
    # jour ou le fait qui la justifie a disparu, en le datant dans le commit.
    chemin_veto = cfg.DATA / "vetos.csv"
    vetos_df = pd.read_csv(chemin_veto) if chemin_veto.exists() else pd.DataFrame(
        columns=["Ticker", "date", "motif"])
    vetos = set(vetos_df["Ticker"].dropna())
    if vetos:
        note(f"vetos qualitatifs actifs : {len(vetos)} -> {', '.join(sorted(vetos))}")
    # Positions : dernier export StockTrak de data/, sinon positions.csv.
    # Les ETF sont separes ici et ne passent ni par le classement ni par le
    # DCF ; ils ne reviennent que dans la valeur du fonds et l'allocation.
    toutes, source = ps.charger(univers)
    positions = toutes[toutes["type"] == "action"].copy()
    # ETF et obligations : hors classement et DCF, mais dans la valeur du fonds.
    # Les futures y sont aussi, pour leur seul P/L (voir plus bas).
    etf = toutes[toutes["type"].isin(["etf", "obligation", "future"])].copy()
    etat = ps.compte()
    hist_ca = _lire("historique_ca.csv")
    wacc = _lire("wacc_secteurs.csv")

    # ---------------------------------------------------------- collecte ----
    taux = collecte.taux_de_change()
    note(f"taux de change : {', '.join(f'{k} {v:.4f}' for k, v in taux.items())}")
    chemin_cours = cfg.DATA / "cours.csv"
    derniers = pd.read_csv(chemin_cours) if chemin_cours.exists() else None
    cours = collecte.cours_du_jour(univers_complet["Ticker"].tolist(), derniers)
    if not cours.empty:
        # On garde les cours du jour : ils serviront de repli si Yahoo nous
        # coupe demain. Une donnee manquante ne doit jamais ressembler a un
        # signal de vente.
        cours[~cours["perime"].fillna(True).astype(bool)].to_csv(chemin_cours, index=False)
    # Un cours "frais" doit exister : un perime=False avec un cours vide a deja
    # affiche 192/192 alors que 17 lignes detenues n'avaient pas de prix.
    # Le seuil de fiabilite se mesure sur l'univers du fonds.
    frais_ok = ((~cours["perime"].fillna(True).astype(bool)) & cours["cours"].notna()) \
        if not cours.empty else pd.Series(dtype=bool)
    frais = int((frais_ok & cours["Ticker"].isin(univers["Ticker"])).sum()) if not cours.empty else 0
    if len(univers_complet) > len(univers):
        note(f"cours frais univers mondial : {int(frais_ok.sum())} / {len(univers_complet)}")
    note(f"cours frais : {frais} / {len(univers)}")
    if frais < 0.8 * len(univers):
        note("ATTENTION moins de 80 % de cours frais : classement peu fiable, "
             "aucune decision ne devrait etre prise sur cette execution")
    fantomes = cours.loc[~cours["negociable"].fillna(False), "Ticker"].tolist()
    if fantomes:
        note(f"lignes sans volume du jour (test de liquidite) : {len(fantomes)} "
             f"-> {', '.join(fantomes[:8])}{' ...' if len(fantomes) > 8 else ''}")
    jamais_verifies = univers.loc[univers["verifie_stocktrak"].isna(), "Ticker"].tolist()
    if jamais_verifies:
        note(f"titres jamais verifies dans StockTrak : {len(jamais_verifies)} "
             f"-> non proposables tant que le controle n'est pas fait")

    rang_in = _lire("fondamentaux_rang.csv")
    dcf_in = _lire("fondamentaux_dcf.csv")
    if collecte.doit_rafraichir_fondamentaux(aujourdhui):
        note("rafraichissement hebdomadaire des fondamentaux")
        etats_fonds: list = []
        neufs = collecte.fondamentaux(univers["Ticker"].tolist(), etats_fonds)
        if etats_fonds:
            # Historique des exercices : fiche d'analyse et backtest. Sans
            # effet sur le classement du fonds.
            _remplacer("etats_annuels.csv", pd.DataFrame(etats_fonds),
                       cles=("Ticker", "cloture"))
        if not neufs.empty:
            # fondamentaux_dcf.csv est tenu EN EUROS (pas de colonne devise),
            # alors que Yahoo publie en devise de publication. Corrige le
            # 14/11/2026 : le premier rafraichissement avait ecrit la dette
            # nette d'Assa Abloy en couronnes (63 955 au lieu de 5 678 MEUR),
            # gonfle sa VE, et fait passer Assa Abloy, Essity et Royal Unibrew
            # en veto DCF. Conversion au taux du jour, avant la mise a jour.
            div = neufs["devise_etats"].fillna("EUR").map(lambda d: taux.get(d, np.nan))
            sans_taux = neufs.loc[div.isna(), "Ticker"].tolist()
            if sans_taux:
                note(f"ATTENTION comptes sans taux de change, dette non mise a jour : "
                     f"{', '.join(sans_taux)}")
            for c in ("dette_nette", "minoritaires", "mises_en_equivalence"):
                if c in neufs.columns:
                    neufs[c] = neufs[c] / div
            for cible, colonnes in (
                # La devise voyage avec les montants : sans elle, les chiffres
                # fraichement collectes (en devise de publication) se
                # melangeraient aux valeurs de depart (en euros) et le
                # book-to-market des britanniques et des nordiques serait faux.
                ("fondamentaux_rang.csv", ["ca", "cogs", "profit_brut",
                                           "actif", "fonds_propres",
                                           "devise_etats"]),
                ("fondamentaux_dcf.csv", ["dette_nette", "minoritaires",
                                          "mises_en_equivalence"]),
            ):
                ancien = _lire(cible).set_index("Ticker")
                maj = neufs.set_index("Ticker")[[c for c in colonnes
                                                 if c in neufs.columns]]
                ancien.update(maj)
                ancien.reset_index().to_csv(cfg.DATA / cible, index=False)
            note(f"fondamentaux mis a jour pour {len(neufs)} titres")

    # Univers mondial : les titres hors fonds sans comptes sont amorces, puis
    # chacun est relu un jour ouvre sur cinq. Jamais un titre du fonds.
    hors = [t for t in univers_complet["Ticker"] if t not in set(univers["Ticker"])]
    if hors:
        connus = set(rang_in["Ticker"]) & set(dcf_in["Ticker"])
        a_lire = [t for t in hors if t not in connus][:cfg.AMORCAGE_MAX]
        if aujourdhui.weekday() < 5:
            a_lire += [t for t in hors if t in connus
                       and zlib.crc32(t.encode()) % cfg.TRANCHES_FONDAMENTAUX == aujourdhui.weekday()]
        if a_lire:
            rafraichir_monde(a_lire, taux)
            # Les comptes tout juste lus servent des aujourd'hui pour les titres
            # hors fonds ; ceux du fonds restent ceux lus en debut de passage.
            du_fonds = set(univers["Ticker"])
            for nom in ("rang", "dcf"):
                frais_ = _lire(f"fondamentaux_{nom}.csv")
                frais_ = frais_[~frais_["Ticker"].isin(du_fonds)]
                garde = rang_in if nom == "rang" else dcf_in
                garde = pd.concat([garde[garde["Ticker"].isin(du_fonds)], frais_],
                                  ignore_index=True)
                if nom == "rang":
                    rang_in = garde
                else:
                    dcf_in = garde

    # ------------------------------------------------- classement et DCF ----
    if "actions_m" in dcf_in.columns:
        rang_in = rang_in.merge(dcf_in[["Ticker", "actions_m"]], on="Ticker",
                                how="left")
    clt = cl.classer(univers, rang_in, cours, taux, bloques)
    ev = dcf.evaluer(clt, dcf_in, hist_ca, wacc)

    # ----------------------------------------------------- indice et perf ---
    idx = collecte.indice()
    perf_indice = (float(idx.iloc[-1] / idx.iloc[0] - 1)
                   if len(idx) > 1 else np.nan)
    note(f"{cfg.BENCHMARK_NOM} depuis le lancement : {perf_indice:+.2%}"
         if np.isfinite(perf_indice) else "indice indisponible")

    # La devise de la position et celle de la cotation sont la meme chose :
    # on garde celle du marche et on ecarte le doublon avant la fusion.
    pf = positions.drop(columns=["devise"]).merge(ev, on="Ticker", how="left")
    pf["devise"] = pf["devise"].fillna("EUR")
    # Garde-fou : une devise que la table de change ne connait pas donnerait
    # une valeur vide en silence, et la ligne disparaitrait du total.
    inconnues = sorted(set(pf["devise"]) - set(taux))
    if inconnues:
        note(f"ATTENTION devises sans taux de change : {', '.join(inconnues)}")
    pf["cours_local"] = pf["cours"]
    # Sans cours Yahoo, on garde le dernier cours de l'export StockTrak plutot
    # que de laisser la ligne sortir de la valeur du fonds en silence.
    sans_yahoo = pf["cours_local"].isna() & pf["cours_stocktrak"].notna()
    pf["cours_source"] = np.where(sans_yahoo, "stocktrak", "yahoo")
    pf.loc[sans_yahoo, "cours_local"] = pf.loc[sans_yahoo, "cours_stocktrak"]
    if sans_yahoo.any():
        note(f"ATTENTION cours Yahoo absent, cours de l'export StockTrak utilise : "
             f"{', '.join(pf.loc[sans_yahoo, 'Ticker'])}")
    sans_cours = pf.loc[pf["cours_local"].isna(), "Ticker"].tolist()
    if sans_cours:
        note(f"ATTENTION aucun cours pour des lignes detenues, valeur du fonds "
             f"incomplete : {', '.join(sans_cours)}")
    pf["perf"] = pf["cours_local"] / pf["prix_paye_local"] - 1
    pf["perf_relative"] = pf["perf"] - perf_indice
    # Cours StockTrak et cours Yahoo doivent dire la meme chose : un ecart de
    # plus de 10 % est le symptome des lignes fantomes (HIGH cote au centieme).
    ecart = pf["cours_stocktrak"] / pf["cours_local"] - 1
    for r in pf[ecart.abs() > 0.10].itertuples():
        note(f"ATTENTION cours StockTrak {r.cours_stocktrak:.4g} contre Yahoo "
             f"{r.cours_local:.4g} pour {r.Ticker} ({r.cours_stocktrak / r.cours_local - 1:+.0%})")
    pf["valeur_eur"] = pf["quantite"] * pf["cours_local"] / \
        pf["devise"].map(lambda d: taux.get(d, np.nan))
    total = pf["valeur_eur"].sum()

    # ETF : cours de l'export (Yahoo ne les suit pas), convertis en euros.
    inconnues = sorted(set(etf["devise"]) - set(taux))
    if inconnues:
        note(f"ATTENTION devises d'ETF sans taux de change : {', '.join(inconnues)}")
    etf["cours_local"] = etf["cours_stocktrak"]
    etf["perf"] = etf["cours_local"] / etf["prix_paye_local"] - 1
    etf["perf_relative"] = etf["perf"] - perf_indice
    etf["valeur_eur"] = etf["quantite"] * etf["cours_local"] / \
        etf["devise"].map(lambda d: taux.get(d, np.nan))
    # Un future ne vaut pas son nominal : il vaut son gain ou sa perte latente
    # (P/L de l'export, deja en euros). Le nominal reste affiche a part.
    est_future = etf["type"] == "future"
    etf["notionnel_eur"] = np.where(est_future, etf["valeur_marche_stocktrak"], np.nan)
    etf.loc[est_future, "valeur_eur"] = etf.loc[est_future, "pl_stocktrak"].fillna(0.0)
    total_etf = float(pd.to_numeric(etf["valeur_eur"]).sum()) if len(etf) else 0.0
    liquidites = etat["liquidites_eur"]
    # Controle des liquidites saisies : capital - cout des positions, cout tel
    # que StockTrak le compte en euros (valeur de marche - P/L). Exact tant
    # qu'aucune vente n'a realise de gain ou de perte ; au-dela, indicatif.
    # Les futures n'ont pas de cout d'achat : seul leur depot de garantie sort
    # des liquidites, et l'export ne le donne pas. D'ou un ecart residuel
    # possible quand le fonds en detient.
    payes = toutes[toutes["type"] != "future"]
    a_terme = int((toutes["type"] == "future").sum())
    mv, pl = payes["valeur_marche_stocktrak"], payes["pl_stocktrak"]
    liq_estimees = (cfg.CAPITAL_INITIAL - float((mv - pl).sum())
                    if len(payes) and mv.notna().all() and pl.notna().all() else np.nan)
    if np.isfinite(liq_estimees):
        if not np.isfinite(liquidites):
            note(f"liquidites non saisies ; d'apres l'export : {liq_estimees:,.0f} EUR")
        elif abs(liquidites - liq_estimees) > 0.01 * max(liq_estimees, 1.0):
            note(f"ATTENTION liquidites saisies {liquidites:,.0f} EUR, l'export en "
                 f"implique {liq_estimees:,.0f} (capital - cout des positions"
                 + (f", hors depot de garantie de {a_terme} future(s)" if a_terme else "")
                 + ") : a verifier dans StockTrak")
    total_fonds = float(total) + total_etf + (liquidites if np.isfinite(liquidites) else 0.0)
    # Poids dans le fonds entier (actions, ETF, liquidites) pour l'affichage ;
    # poids dans la poche actions pour l'ecart sectoriel, qui compare la poche
    # actions a son indice.
    pf["poids"] = pf["valeur_eur"] / total_fonds
    pf["poids_poche"] = pf["valeur_eur"] / total
    etf["poids"] = etf["valeur_eur"] / total_fonds

    # Performance mediane du secteur, calculee sur notre propre univers : elle
    # dit si la baisse d'un titre suit son secteur ou lui est propre. Faute
    # d'historique local au demarrage, on la mesure sur la variation du jour ;
    # data/historique.csv s'accumule et prendra le relais.
    perf_sect = {}
    for s, bloc in ev.groupby("Secteur"):
        v = (bloc["cours"] - bloc["ouverture"]) / bloc["ouverture"]
        perf_sect[s] = float(v.median()) if v.notna().any() else np.nan
    pf["perf_jour"] = (pf["cours"] - pf["ouverture"]) / pf["ouverture"]
    pf["perf_jour_secteur"] = pf["Secteur"].map(perf_sect)

    # ------------------------------------------------------- historique -----
    chemin_hist = cfg.DATA / "historique.csv"
    hist = pd.read_csv(chemin_hist) if chemin_hist.exists() else pd.DataFrame(
        columns=["date", "Ticker", "rang", "g1", "seuil", "marge",
                 "zone_rang", "zone_dcf", "zone_decrochage", "zone"])

    gpa = dict(zip(pf["Ticker"], pf["GP/A ajuste"]))
    med = dict(zip(pf["Ticker"], pf["mediane_secteur"]))

    def zones(r) -> tuple[dict, list[str]]:
        """Zones d'une ligne detenue, et le motif d'une donnee douteuse.

        Une ligne sans rang tombe d'ordinaire en sortie immediate. Quand ce
        rang manque a cause d'une donnee suspecte ou d'un blocage, ce serait
        une donnee qui ressemble a un signal de vente : la ligne passe en
        surveillance, avec le motif, et le comite tranche.
        """
        z = {
            "rang": sg.zone_rang(r.rang),
            "dcf": sg.zone_dcf(r.marge),
            "decrochage": sg.zone_decrochage(r.perf_relative),
            "degradation": sg.zone_degradation(gpa.get(r.Ticker), med.get(r.Ticker)),
        }
        motifs = []
        if bool(getattr(r, "bm_implausible", False)):
            # Cours dans la mauvaise unite : rang, DCF et decrochage reposent
            # tous sur ce cours. Seule la jambe comptable reste lisible.
            z.update(rang=sg.SURVEILLANCE, dcf=sg.OK, decrochage=sg.OK)
            motifs.append(f"book-to-market implausible ({bm.get(r.Ticker, np.nan):.3g}) : "
                          "donnee a verifier, aucun signal tire du cours")
        elif bool(getattr(r, "bloque", False)) and not np.isfinite(r.rang):
            z["rang"] = sg.SURVEILLANCE
            motifs.append("bloque dans StockTrak, donc sans rang : a arbitrer en comite")
        return z, motifs

    bm = dict(zip(pf["Ticker"], pf["B/M"]))
    lignes_hist = []
    for r in pf.itertuples():
        z, _ = zones(r)
        lignes_hist.append({
            "date": aujourdhui.isoformat(), "Ticker": r.Ticker,
            "rang": r.rang, "g1": r.g1, "seuil": r.seuil, "marge": r.marge,
            "zone_rang": z["rang"], "zone_dcf": z["dcf"],
            "zone_decrochage": z["decrochage"],
            "zone_degradation": z["degradation"], "zone": sg.zone_globale(z),
        })
    hist = pd.concat([hist, pd.DataFrame(lignes_hist)], ignore_index=True)
    hist = hist.drop_duplicates(subset=["date", "Ticker"], keep="last")
    hist.to_csv(chemin_hist, index=False)

    # --------------------------------------------------------- signaux ------
    detenus = set(positions["Ticker"])
    ecarts = {}
    for s, bloc in pf.groupby("Secteur"):
        ecarts[s] = float(bloc["poids_poche"].sum())
    candidats = sg.remplacants_eligibles(ev[ev["liste_suivi"].fillna(False)], detenus,
                                         vetos)

    portefeuille = []
    for r in pf.itertuples():
        donnees = bool(np.isfinite(r.cours_local)) and not bool(getattr(r, "perime", False))
        if donnees:
            z, motifs_donnees = zones(r)
        else:
            # Pas de cours frais : on ne sait rien, donc on ne signale rien.
            z = {k: sg.OK for k in ("rang", "dcf", "decrochage", "degradation")}
            motifs_donnees = []
        globale = sg.zone_globale(z)
        clotures = sg.compter_clotures(hist, r.Ticker, "zone_dcf")
        clotures_deg = sg.compter_clotures(hist, r.Ticker, "zone_degradation")
        confirme = (clotures >= cfg.CLOTURES_CONFIRMATION
                    or clotures_deg >= cfg.CLOTURES_CONFIRMATION
                    or z["rang"] == sg.SORTIE
                    or z["decrochage"] == sg.SORTIE)
        # Un titre doit savoir dire POURQUOI il est la ou il est : sans ca,
        # une ligne en sortie dont les trois zones visibles affichent "ok"
        # est incomprehensible.
        motifs = list(motifs_donnees)
        if not donnees:
            motifs.append("cours indisponible aujourd'hui")
        elif r.cours_source == "stocktrak":
            motifs.append("cours de l'export StockTrak (Yahoo indisponible)")
        if z["rang"] != sg.OK and not motifs_donnees:
            motifs.append("rang " + ("introuvable (plancher ou liquidite)"
                                     if not np.isfinite(r.rang) else f"{int(r.rang)}"))
        if z["dcf"] != sg.OK:
            motifs.append(f"marge DCF {r.marge:+.2%}")
        if z["decrochage"] != sg.OK:
            motifs.append(f"decrochage {r.perf_relative:+.1%} vs indice")
        if z["degradation"] != sg.OK:
            motifs.append(f"GP/A ajuste {gpa.get(r.Ticker):+.4f}")
        remp = None
        if globale == sg.SORTIE:
            m = sg.meilleur_remplacant(candidats, r.Secteur, ecarts)
            if m is not None:
                remp = {"Ticker": m["Ticker"], "Societe": m["Societe"],
                        "Secteur": m["Secteur"], "rang": _nan(m["rang"]),
                        "verdict": m["verdict"], "marge": _nan(m["marge"])}
        portefeuille.append(_propre({
            "ticker": r.Ticker, "stocktrak": r.symbole_stocktrak,
            "societe": r.Societe, "pays": r.Pays, "secteur": r.Secteur,
            "quantite": r.quantite, "devise": r.devise,
            "prix_paye": r.prix_paye_local, "cours": r.cours_local,
            "cours_source": r.cours_source, "cours_stocktrak": r.cours_stocktrak,
            "valeur_eur": r.valeur_eur, "poids": r.poids,
            "poids_poche": r.poids_poche, "type": "action",
            "perf": r.perf, "perf_relative": r.perf_relative,
            "perf_jour": r.perf_jour, "perf_jour_secteur": r.perf_jour_secteur,
            "rang": r.rang, "g1": r.g1, "seuil": r.seuil, "marge": r.marge,
            "verdict": r.verdict, "dispersion": r.dispersion,
            "zone_rang": z["rang"], "zone_dcf": z["dcf"],
            "zone_decrochage": z["decrochage"],
            "zone_degradation": z["degradation"], "zone": globale,
            "motifs": motifs, "donnees_fraiches": donnees,
            "gpa_ajuste": gpa.get(r.Ticker),
            "mediane_secteur": med.get(r.Ticker),
            "clotures_consecutives": max(clotures, clotures_deg),
            "sortie_confirmee": bool(confirme and globale == sg.SORTIE),
            "remplacant": remp,
        }))

    # Obligations IG : score horizon du classeur, rapproche des obligations
    # detenues (export StockTrak).
    classement_ig = ob.scorer(ob.charger())
    lignes_ig, hors_ig = ob.rapprocher(classement_ig, etf[etf["type"] == "obligation"])

    lignes_etf = [_propre({
        "ticker": r.Ticker, "stocktrak": r.symbole_stocktrak,
        "description": r.description, "type": r.type,
        "quantite": r.quantite, "devise": r.devise,
        "prix_paye": r.prix_paye_local, "cours": r.cours_local,
        "valeur_eur": r.valeur_eur, "poids": r.poids,
        "perf": r.perf, "perf_relative": r.perf_relative,
        "notionnel_eur": r.notionnel_eur,
    }) for r in etf.itertuples()]

    # Transactions consommees : saisies dans data/compte.csv avec l'export.
    transactions_initiales = cfg.TRANSACTIONS_CONSTRUCTION
    transactions = etat["transactions"]
    note(f"transactions consommees : {transactions} "
         f"(data/compte.csv au {etat['date']})")

    # Table compacte de l'univers : la page s'en sert pour relire un export
    # depose dans le navigateur avant le passage du programme.
    cols_u = ["Ticker", "Symbole StockTrak", "Societe", "Pays", "Secteur",
              "devise", "cours", "rang", "g1", "seuil", "marge", "verdict"]
    table_univers = [_propre(x) for x in
                     ev.reindex(columns=cols_u).to_dict("records")]

    sortie = {
        "date": aujourdhui.isoformat(),
        "benchmark": {"nom": cfg.BENCHMARK_NOM,
                      "perf_depuis_lancement": _nan(perf_indice)},
        "source_positions": source,
        "fonds": {
            "valeur_eur": _nan(total_fonds),
            "actions_eur": _nan(float(total)),
            "etf_eur": _nan(total_etf),
            "liquidites_eur": _nan(liquidites),
            "liquidites_estimees_eur": _nan(liq_estimees),
            "capital_eur": cfg.CAPITAL_INITIAL,
            "perf": _nan(total_fonds / cfg.CAPITAL_INITIAL - 1),
            "date_compte": etat["date"],
        },
        "portefeuille": {
            "valeur_eur": _nan(float(total)),
            "nb_lignes": int(len(pf)),
            "perf_moyenne": _nan(float(pf["perf"].mean())),
            "lignes": portefeuille,
            "etf": lignes_etf,
        },
        "taux": taux,
        "obligations_ig": {
            "date_donnees": cfg.OBLIG_DATE_DONNEES,
            "liquidation": cfg.OBLIG_LIQUIDATION,
            "horizon_ans": ob.horizon_annees(),
            "indice": {"ytm": cfg.OBLIG_BENCH_YTM, "duration": cfg.OBLIG_BENCH_DURATION},
            "lignes": lignes_ig,
            "hors_classeur": hors_ig,
        },
        "univers": table_univers,
        "remplacants": [_propre(x) for x in candidats.head(20)[
            ["Ticker", "Societe", "Secteur", "Pays", "rang", "verdict",
             "g1", "seuil", "marge"]].to_dict("records")],
        "ecartes": [_propre(x) for x in clt[clt["bloque"]][
            ["Ticker", "Societe", "Secteur", "rang"]].to_dict("records")],
        "budget": sg.budget(transactions, transactions_initiales, aujourdhui),
        "parametres": {
            "rang_surveillance": cfg.RANG_SURVEILLANCE,
            "rang_sortie": cfg.RANG_SORTIE,
            "marge_surveillance": cfg.MARGE_DCF_SURVEILLANCE,
            "clotures_confirmation": cfg.CLOTURES_CONFIRMATION,
            "decrochage_reexamen": cfg.DECROCHAGE_REEXAMEN,
            "decrochage_sortie": cfg.DECROCHAGE_SORTIE,
        },
        "blocages": blocages.to_dict("records"),
        "vetos": vetos_df.to_dict("records"),
        "journal": lignes(),
    }

    cfg.DOCS.mkdir(exist_ok=True)
    (cfg.DOCS / "data.json").write_text(
        json.dumps(sortie, ensure_ascii=False, indent=1, default=_nan),
        encoding="utf-8")
    note(f"docs/data.json ecrit ({len(portefeuille)} lignes, "
         f"{len(sortie['remplacants'])} remplacants)")

    # Portefeuilles personnels et classements par univers filtre. Apres le
    # fonds, et a part : une erreur ici ne doit pas empecher sa mise a jour.
    # Taux sans risque hors Europe : ceux que Yahoo donne remplacent la saisie
    # de config.py pour ce passage. Sans effet sur le fonds (devises europeennes,
    # et son DCF est deja ecrit plus haut).
    lus = collecte.taux_sans_risque()
    cfg.TAUX_SANS_RISQUE_DEVISE.update(lus)
    note("taux sans risque hors Europe : " + ", ".join(
        f"{k} {v:.2%}{' (Yahoo)' if k in lus else ' (config.py, a valider)'}"
        for k, v in cfg.TAUX_SANS_RISQUE_DEVISE.items()))
    try:
        pfs.calculer(univers_complet, rang_in, dcf_in, hist_ca, wacc, cours, taux,
                     bloques, vetos, aujourdhui)
    except Exception as e:                              # noqa: BLE001
        note(f"ATTENTION portefeuilles personnels non calcules : {e}")
    # Le journal de data.json est reecrit pour inclure ces dernieres lignes.
    sortie["journal"] = lignes()
    (cfg.DOCS / "data.json").write_text(
        json.dumps(sortie, ensure_ascii=False, indent=1, default=_nan),
        encoding="utf-8")


if __name__ == "__main__":
    main()
