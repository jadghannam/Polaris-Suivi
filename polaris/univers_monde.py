# -*- coding: utf-8 -*-
"""
Construction de l'univers mondial.

    python -m polaris.univers_monde            # reconstruit data/univers.csv
    python -m polaris.univers_monde --essai    # n'ecrit rien, affiche le bilan

Cinq indices : STOXX Europe 600, S&P 500, Nikkei 225, Hang Seng China
Enterprises (Chine cotee a Hong Kong) et KOSPI 200. Decide le 14/11/2026 : la
plateforme doit pouvoir servir au-dela du fonds, sur tout ce qu'un investisseur
europeen peut acheter. L'univers du fonds n'en est qu'un sous-ensemble, obtenu
par deux contraintes que la page laisse cocher :

  - Europe    : Region == "Europe" ;
  - StockTrak : verifie_stocktrak renseigne, c'est-a-dire controle a la main
                dans StockTrak. Aucun titre ajoute ici ne l'est.

Les 192 lignes deja presentes ne sont JAMAIS modifiees : symbole, secteur,
pays et date de verification restent tels qu'ils ont ete saisis. On leur ajoute
seulement Region et Indice. C'est ce qui garantit que le fonds, contraintes
cochees, retrouve exactement son classement.

Les financieres et l'immobilier sont exclus, comme partout ailleurs dans la
methode : ni la rentabilite brute ni le DCF sur flux operationnels n'ont de
sens pour une banque ou une fonciere.

Sources : fichier des positions de l'ETF iShares STOXX Europe 600 (EXSA, GICS
et place de cotation), Wikipedia pour les quatre autres. Pour Nikkei, HSCEI et
KOSPI, Wikipedia donne des classifications locales (Nikkei, HSICS, KRX) qui ne
sont pas GICS : le secteur est alors celui de Yahoo, ramene a la nomenclature
GICS. Limite assumee, ecrite dans CONTEXTE.md.
"""

from __future__ import annotations

import io
import re
import sys
import time

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from . import config as cfg

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
# Le site suisse sert le CSV ; le site allemand renvoie la page HTML.
EXSA = ("https://www.ishares.com/ch/individual/en/products/251931/"
        "ishares-stoxx-europe-600-ucits-etf-de-fund/1495092304805.ajax"
        "?fileType=csv&fileName=EXSA_holdings&dataType=fund")

GICS_FR = {
    "Information Technology": "Technologies de l'information",
    "Health Care": "Sante", "Energy": "Energie",
    "Consumer Staples": "Consommation de base", "Industrials": "Industrie",
    "Utilities": "Services aux collectivites", "Materials": "Materiaux",
    "Consumer Discretionary": "Consommation discretionnaire",
    "Communication": "Services de communication",
    "Communication Services": "Services de communication",
}
# Secteurs Yahoo (Morningstar), proches de GICS. Financieres et immobilier
# n'y figurent pas : un titre sans correspondance est exclu.
YAHOO_FR = {
    "Technology": "Technologies de l'information", "Healthcare": "Sante",
    "Energy": "Energie", "Consumer Defensive": "Consommation de base",
    "Industrials": "Industrie", "Utilities": "Services aux collectivites",
    "Basic Materials": "Materiaux", "Consumer Cyclical": "Consommation discretionnaire",
    "Communication Services": "Services de communication",
}
PLACES_ISHARES = {
    "Euronext Amsterdam": ".AS", "SIX Swiss Exchange": ".SW",
    "London Stock Exchange": ".L", "Xetra": ".DE", "Deutsche Boerse Xetra": ".DE",
    "Nyse Euronext - Euronext Paris": ".PA", "Bolsa De Madrid": ".MC",
    "Borsa Italiana": ".MI", "Omx Nordic Exchange Copenhagen A/S": ".CO",
    "Nyse Euronext - Euronext Brussels": ".BR", "Nasdaq Omx Nordic": ".ST",
    "Nasdaq Omx Helsinki Ltd.": ".HE", "Wiener Boerse Ag": ".VI",
    "Oslo Bors Asa": ".OL", "Irish Stock Exchange - All Market": ".IR",
    "Warsaw Stock Exchange/Equities/Main Market": ".WA",
    "Nyse Euronext - Euronext Lisbon": ".LS", "Athens Exchange S.A. Cash Market": ".AT",
}
# Symboles iShares qui ne se deduisent pas du symbole Yahoo par la regle.
# Chaque entree doit etre constatee, pas devinee : le 14/11/2026, Roche
# (bon de jouissance) a ete mise ici en ROG.SW par habitude, alors que Yahoo
# la cote desormais ROP.SW, comme iShares. Vide pour l'instant.
EXCEPTIONS_STOXX: dict[str, str] = {}
PAYS_FR = {
    "United Kingdom": "Royaume-Uni", "France": "France", "Germany": "Allemagne",
    "Switzerland": "Suisse", "Netherlands": "Pays-Bas", "Spain": "Espagne",
    "Italy": "Italie", "Sweden": "Suede", "Denmark": "Danemark",
    "Belgium": "Belgique", "Finland": "Finlande", "Norway": "Norvege",
    "Austria": "Autriche", "Ireland": "Irlande", "Poland": "Pologne",
    "Portugal": "Portugal", "Greece": "Grece", "Luxembourg": "Luxembourg",
    "Jersey": "Jersey", "Isle of Man": "Ile de Man", "Guernsey": "Guernesey",
    "United States": "Etats-Unis", "Japan": "Japon", "China": "Chine",
    "South Korea": "Coree du Sud",
}
REGION_INDICE = {"STOXX 600": "Europe", "S&P 500": "Amerique du Nord",
                 "Nikkei 225": "Japon", "HSCEI": "Chine", "KOSPI 200": "Coree"}

# ---------------------------------------------------- MSCI ACWI (14/11/2026)
# L'indice de reference des portefeuilles personnels est le MSCI ACWI. Ses
# constituants et ses poids viennent de deux fichiers iShares, relus a chaque
# reconstruction :
#   - SWDA, MSCI World (23 pays developpes, replication complete) ;
#   - IEMM, MSCI Emerging Markets (grandes et moyennes capitalisations).
# Le fichier de l'ETF ACWI lui-meme (SSAC) n'est PAS une source fiable des
# poids : il echantillonne et ne detient ni l'Inde ni l'Arabie saoudite en
# direct (constate le 14/11/2026). Il sert seulement a mesurer la part des
# pays developpes dans l'ACWI, sur les titres qu'il partage avec SWDA.
ISHARES_CH = ("https://www.ishares.com/ch/individual/en/products/{p}/x/"
              "1495092304805.ajax?fileType=csv&fileName={f}_holdings&dataType=fund")
FICHIERS_MSCI = {"MSCI World": ("251882", "SWDA"), "MSCI EM": ("251858", "IEMM")}
FICHIER_ACWI = ("251850", "SSAC")

# Place de cotation iShares -> suffixes Yahoo a essayer, dans l'ordre.
PLACES_MSCI = {
    **{k: [v] for k, v in PLACES_ISHARES.items()},
    "New York Stock Exchange Inc.": [""], "NASDAQ": [""], "Cboe BZX": [""],
    "Toronto Stock Exchange": [".TO"], "Asx - All Markets": [".AX"],
    "Tokyo Stock Exchange": [".T"], "Hong Kong Exchanges And Clearing Ltd": [".HK"],
    "Singapore Exchange": [".SI"], "Tel Aviv Stock Exchange": [".TA"],
    "New Zealand Exchange Ltd": [".NZ"], "Taiwan Stock Exchange": [".TW"],
    "Gretai Securities Market": [".TWO"], "National Stock Exchange Of India": [".NS"],
    "Bse Ltd": [".BO"], "Korea Exchange (Stock Market)": [".KS"],
    "Korea Exchange (Kosdaq)": [".KQ"], "Shanghai Stock Exchange": [".SS"],
    "Shenzhen Stock Exchange": [".SZ"], "XBSP": [".SA"], "Saudi Stock Exchange": [".SR"],
    "Johannesburg Stock Exchange": [".JO"], "Bolsa Mexicana De Valores": [".MX"],
    "Bursa Malaysia": [".KL"], "Stock Exchange Of Thailand": [".BK"],
    "Indonesia Stock Exchange": [".JK"], "Philippine Stock Exchange Inc.": [".PS"],
    "Istanbul Stock Exchange": [".IS"], "Qatar Exchange": [".QA"],
    "Abu Dhabi Securities Exchange": [".AD", ".AE"], "Dubai Financial Market": [".AE", ".DU"],
    "Kuwait Stock Exchange": [".KW"], "Santiago Stock Exchange": [".SN"],
    "Budapest Stock Exchange": [".BD"], "Prague Stock Exchange": [".PR"],
    "Bolsa De Valores De Colombia": [".CL"], "Egyptian Exchange": [".CA"],
}
PAYS_FR.update({
    "Canada": "Canada", "Australia": "Australie", "Hong Kong": "Hong Kong",
    "Singapore": "Singapour", "Israel": "Israel", "New Zealand": "Nouvelle-Zelande",
    "Taiwan": "Taiwan", "India": "Inde", "Korea (South)": "Coree du Sud",
    "Brazil": "Bresil", "Saudi Arabia": "Arabie saoudite", "South Africa": "Afrique du Sud",
    "Mexico": "Mexique", "Malaysia": "Malaisie", "Thailand": "Thailande",
    "Indonesia": "Indonesie", "Philippines": "Philippines", "Turkey": "Turquie",
    "Qatar": "Qatar", "United Arab Emirates": "Emirats arabes unis", "Kuwait": "Koweit",
    "Chile": "Chili", "Peru": "Perou", "Colombia": "Colombie", "Hungary": "Hongrie",
    "Czech Republic": "Republique tcheque", "Egypt": "Egypte",
})
# Regions de classement et d'allocation. Les pays emergents de l'Union
# europeenne vont avec l'Europe, comme dans le STOXX 600.
REGION_PAYS = {
    "Etats-Unis": "Amerique du Nord", "Canada": "Amerique du Nord",
    "Japon": "Japon",
    "Australie": "Pacifique", "Nouvelle-Zelande": "Pacifique", "Hong Kong": "Pacifique",
    "Singapour": "Pacifique",
    "Chine": "Chine", "Coree du Sud": "Coree", "Taiwan": "Taiwan", "Inde": "Inde",
    "Malaisie": "Asie emergente", "Thailande": "Asie emergente",
    "Indonesie": "Asie emergente", "Philippines": "Asie emergente",
    "Bresil": "Amerique latine", "Mexique": "Amerique latine", "Chili": "Amerique latine",
    "Perou": "Amerique latine", "Colombie": "Amerique latine",
    "Arabie saoudite": "Moyen-Orient et Afrique", "Afrique du Sud": "Moyen-Orient et Afrique",
    "Emirats arabes unis": "Moyen-Orient et Afrique", "Qatar": "Moyen-Orient et Afrique",
    "Koweit": "Moyen-Orient et Afrique", "Egypte": "Moyen-Orient et Afrique",
    "Turquie": "Moyen-Orient et Afrique", "Israel": "Moyen-Orient et Afrique",
}


def region_de(pays: str, defaut: str = "Europe") -> str:
    return REGION_PAYS.get(pays, defaut)


def lire_ishares(produit: str, fichier: str) -> pd.DataFrame:
    r = requests.get(ISHARES_CH.format(p=produit, f=fichier), headers=UA, timeout=60)
    r.raise_for_status()
    lignes = r.content.decode("utf-8-sig").splitlines()
    debut = next(i for i, l in enumerate(lignes) if l.startswith("Ticker,"))
    df = pd.read_csv(io.StringIO("\n".join(lignes[debut:])), dtype=str, on_bad_lines="skip")
    df["poids"] = df["Weight (%)"].map(_nombre_suisse) / 100
    return df


def _candidats(ticker: str, place: str) -> list[str]:
    sufs = PLACES_MSCI.get(place)
    if sufs is None:
        return []
    s = str(ticker).strip()
    s = re.sub(r"\.(E|R)$", "", s)                 # Istanbul .E, Bangkok .R (NVDR)
    s = s.rstrip(".").rstrip("*")
    if sufs[0] == ".HK":
        s = s.zfill(4)
    if sufs[0] in (".KS", ".KQ"):
        s = s.zfill(6)
    s = re.sub(r"[\s/.]+", "-", s)
    return [s + x for x in sufs]


def msci() -> pd.DataFrame:
    """Constituants MSCI ACWI hors financieres et immobilier, avec leur poids
    dans l'ACWI et des tickers Yahoo candidats (le premier qui cote gagne)."""
    parts = []
    for nom, (p, f) in FICHIERS_MSCI.items():
        d = lire_ishares(p, f)
        d = d[(d["Asset Class"] == "Equity") & (d["poids"] > 0)]
        # Les ETF detenus en ligne (actions A chinoises, une partie du Bresil)
        # ne sont pas des societes.
        d = d[~d["Name"].str.contains(r"\bETF\b|UCITS|ISHARES|ISH ", case=False, regex=True)]
        d["Indice"] = nom
        parts.append(d)
    world, em = parts
    # Part des developpes dans l'ACWI : rapport des poids SSAC / SWDA sur les
    # 50 premieres lignes communes (mediane, insensible aux ecarts de l'ETF).
    acwi = lire_ishares(*FICHIER_ACWI)
    acwi = acwi[acwi["Asset Class"] == "Equity"]
    communs = world.merge(acwi[["Ticker", "Exchange", "poids"]], on=["Ticker", "Exchange"],
                          suffixes=("", "_acwi")).nlargest(50, "poids")
    part_dm = float((communs["poids_acwi"] / communs["poids"]).median())
    print(f"part des pays developpes dans l'ACWI : {part_dm:.1%}")
    world["poids_acwi"] = world["poids"] * part_dm
    em["poids_acwi"] = em["poids"] * (1 - part_dm)
    d = pd.concat([world, em], ignore_index=True)
    d["Pays"] = d["Location"].map(lambda p: PAYS_FR.get(p, p))
    d["Region"] = d["Pays"].map(region_de)
    d["Secteur_source"] = d["Sector"]
    d["Secteur"] = d["Sector"].map(GICS_FR)
    d["candidats"] = [_candidats(t, x) for t, x in zip(d["Ticker"], d["Exchange"])]
    d["Societe"] = d["Name"].str.title()
    return d


def _wiki(page: str) -> str:
    r = requests.get(f"https://en.wikipedia.org/wiki/{page}", headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def _nombre_suisse(s) -> float:
    try:
        return float(str(s).replace("’", "").replace("'", "").replace(",", ""))
    except ValueError:
        return np.nan


# ------------------------------------------------------------- sources -----
def stoxx600() -> pd.DataFrame:
    r = requests.get(EXSA, headers=UA, timeout=60)
    r.raise_for_status()
    texte = r.content.decode("utf-8-sig")
    lignes = texte.splitlines()
    debut = next(i for i, l in enumerate(lignes) if l.startswith("Ticker,"))
    df = pd.read_csv(io.StringIO("\n".join(lignes[debut:])), dtype=str)
    df = df[df["Asset Class"] == "Equity"].copy()

    def yahoo(r):
        suf = PLACES_ISHARES.get(r["Exchange"])
        if suf is None:
            return None
        s = str(r["Ticker"]).strip().rstrip(".")
        s = re.sub(r"[\s/.]+", "-", s)
        return EXCEPTIONS_STOXX.get(s + suf, s + suf)

    df["Ticker_y"] = df.apply(yahoo, axis=1)
    df["Secteur"] = df["Sector"].map(GICS_FR)
    df["Poids"] = df["Weight (%)"].map(_nombre_suisse)
    return pd.DataFrame({
        "Ticker": df["Ticker_y"], "Societe": df["Name"].str.title(),
        "Pays": df["Location"].map(lambda p: PAYS_FR.get(p, p)),
        "Secteur": df["Secteur"], "Secteur_source": df["Sector"],
        "Indice": "STOXX 600"})


def sp500() -> pd.DataFrame:
    t = pd.read_html(io.StringIO(_wiki("List_of_S%26P_500_companies")))[0]
    return pd.DataFrame({
        "Ticker": t["Symbol"].str.replace(".", "-", regex=False),
        "Societe": t["Security"], "Pays": "Etats-Unis",
        "Secteur": t["GICS Sector"].map(GICS_FR), "Secteur_source": t["GICS Sector"],
        "Indice": "S&P 500"})


def nikkei225() -> pd.DataFrame:
    html = _wiki("Nikkei_225")
    res = []
    for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.S):
        texte = re.sub(r"<.*?>", "", m.group(1))
        c = re.search(r"TYO:\s*([0-9A-Z]{4})\)", texte)
        if c:
            res.append((c.group(1) + ".T", texte.split("(TYO")[0].strip()))
    df = pd.DataFrame(res, columns=["Ticker", "Societe"]).drop_duplicates("Ticker")
    df["Pays"], df["Indice"] = "Japon", "Nikkei 225"
    return df


def hscei() -> pd.DataFrame:
    t = pd.read_html(io.StringIO(_wiki("Hang_Seng_China_Enterprises_Index")))
    t = next(x for x in t if "Ticker" in x.columns and len(x) >= 40)
    code = t["Ticker"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
    return pd.DataFrame({"Ticker": code + ".HK", "Societe": t["Name"],
                         "Pays": "Chine", "Indice": "HSCEI"})


def kospi200() -> pd.DataFrame:
    t = pd.read_html(io.StringIO(_wiki("KOSPI_200")))
    t = next(x for x in t if "Symbol" in x.columns and len(x) >= 150)
    code = t["Symbol"].astype(str).str.zfill(6)
    return pd.DataFrame({"Ticker": code + ".KS", "Societe": t["Company"],
                         "Pays": "Coree du Sud", "Indice": "KOSPI 200"})


def secteurs_yahoo(tickers: list[str]) -> dict[str, tuple[str | None, str | None]]:
    """(secteur Yahoo, nom long) titre par titre. Utilise une fois, a la
    construction, depuis un poste : pas dans la chaine quotidienne."""
    out = {}
    for i, t in enumerate(tickers):
        for essai in range(3):
            try:
                info = yf.Ticker(t).info or {}
                out[t] = (info.get("sector"), info.get("longName") or info.get("shortName"))
                break
            except Exception:                           # noqa: BLE001
                time.sleep(3 * (essai + 1))
        else:
            out[t] = (None, None)
        if i % 25 == 24:
            time.sleep(1)
    return out


def valider_cotations(tickers: list[str]) -> set[str]:
    """Tickers pour lesquels Yahoo renvoie au moins une cloture sur 1 mois."""
    ok = set()
    for i in range(0, len(tickers), 200):
        paquet = tickers[i:i + 200]
        d = yf.download(paquet, period="1mo", group_by="ticker", auto_adjust=False,
                        progress=False, threads=True)
        for t in paquet:
            try:
                c = d[t]["Close"] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
                if c.dropna().size:
                    ok.add(t)
            except KeyError:
                pass
        time.sleep(2)
    return ok


# ------------------------------------------------------------ assemblage ---
def _cle_nom(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    for mot in ("plc", "sa", "se", "ag", "nv", "ab", "asa", "spa", "group", "groupe",
                "holding", "holdings", "the", "inc", "corp", "co", "ltd", "a s", "oyj"):
        s = re.sub(rf"\b{mot}\b", " ", s)
    # Nom complet, pas un prefixe : tronque a dix lettres, « International
    # Flavors » et « International Paper » passaient pour IAG.
    return re.sub(r"\s+", "", s)


def construire(essai: bool = False) -> pd.DataFrame:
    tout_actuel = pd.read_csv(cfg.DATA / "univers.csv", dtype=str)
    # Les lignes du fonds sont reprises TELLES QUELLES, contraintes comprises :
    # elles sont posees a la main et ne se recalculent jamais.
    fonds = tout_actuel[tout_actuel["contrainte_stocktrak"].str.upper() == "OUI"].copy()
    anc = tout_actuel.set_index("Ticker")
    print(f"univers du fonds : {len(fonds)} lignes (conservees telles quelles)")

    # 1. MSCI ACWI : constituants, poids, tickers Yahoo.
    m = msci()
    print(f"MSCI ACWI : {len(m)} lignes ({(m['Indice'] == 'MSCI World').sum()} World, "
          f"{(m['Indice'] == 'MSCI EM').sum()} EM)")
    cand = sorted({c for l in m["candidats"] for c in l})
    print(f"validation de {len(cand)} tickers MSCI candidats")
    cotes = valider_cotations(cand)
    m["Ticker_y"] = [next((c for c in l if c in cotes), None) for l in m["candidats"]]
    # Poids et allocation : TOUTES les lignes du fichier, cotees ou non sur
    # Yahoo, pour que l'allocation suive l'indice et pas notre collecte.
    m[["Ticker", "Ticker_y", "Societe", "Pays", "Region", "Secteur_source", "Secteur",
       "Indice", "poids_acwi"]].rename(columns={"Ticker": "Ticker_ishares"}) \
        .to_csv(cfg.DATA / "msci_acwi.csv", index=False) if not essai else None

    # 2. Autres sources, conservees pour la couverture (STOXX 600 en entier,
    #    Nikkei, KOSPI au-dela des grandes capitalisations MSCI).
    autres = []
    for nom, f in (("STOXX 600", stoxx600), ("S&P 500", sp500), ("Nikkei 225", nikkei225),
                   ("HSCEI", hscei), ("KOSPI 200", kospi200)):
        df = f()
        print(f"{nom} : {len(df)} titres lus")
        autres.append(df)
    autres = pd.concat(autres, ignore_index=True)
    autres = autres[autres["Ticker"].notna()]
    autres["Region"] = autres["Pays"].map(lambda p: region_de(p, None))
    autres["Region"] = autres["Region"].fillna(autres["Indice"].map(REGION_INDICE))

    msci_ok = m[m["Ticker_y"].notna()].copy()
    msci_ok["Ticker"] = msci_ok["Ticker_y"]
    neuf = pd.concat([msci_ok[["Ticker", "Societe", "Pays", "Region", "Secteur",
                               "Secteur_source", "Indice"]], autres], ignore_index=True)
    neuf = neuf.drop_duplicates("Ticker", keep="first")      # MSCI d'abord : vrai GICS
    acwi = set(msci_ok["Ticker"])

    # Secteur des sources sans GICS : deja connu dans l'univers, sinon Yahoo.
    sans = neuf["Secteur_source"].isna()
    for i in neuf.index[sans]:
        t = neuf.at[i, "Ticker"]
        if t in anc.index and isinstance(anc.at[t, "Secteur"], str):
            neuf.at[i, "Secteur"], neuf.at[i, "Secteur_source"] = anc.at[t, "Secteur"], "univers"
    a_lire = neuf.loc[neuf["Secteur_source"].isna(), "Ticker"].tolist()
    print(f"secteurs Yahoo a lire : {len(a_lire)}")
    for t, (sect, _) in secteurs_yahoo(a_lire).items():
        neuf.loc[neuf["Ticker"] == t, "Secteur_source"] = sect or "inconnu"
        neuf.loc[neuf["Ticker"] == t, "Secteur"] = YAHOO_FR.get(sect)

    rejets = []
    exclus = neuf["Secteur"].isna()
    for r in neuf[exclus].itertuples():
        rejets.append((r.Ticker, r.Societe, r.Indice, f"secteur exclu : {r.Secteur_source}"))
    neuf = neuf[~exclus]
    for r in m[m["Ticker_y"].isna() & m["Secteur"].notna()].itertuples():
        rejets.append((r.Ticker, r.Societe, r.Indice,
                       f"aucune cotation Yahoo (essaye : {', '.join(r.candidats) or 'place inconnue'})"))

    # Doublons avec le fonds : meme ticker, ou meme nom pour une europeenne.
    connus = set(fonds["Ticker"])
    noms = {_cle_nom(s): t for s, t in zip(fonds["Societe"], fonds["Ticker"])}
    garder = []
    for r in neuf.itertuples():
        if r.Ticker in connus:
            continue
        jumeau = noms.get(_cle_nom(r.Societe)) if r.Region == "Europe" else None
        if jumeau:
            rejets.append((r.Ticker, r.Societe, r.Indice, f"doublon de {jumeau} (univers du fonds)"))
            continue
        garder.append(r.Index)
    neuf = neuf.loc[garder]

    a_valider = [t for t in neuf["Ticker"] if t not in cotes]
    print(f"validation des cotations des autres sources : {len(a_valider)} titres")
    cotes |= valider_cotations(a_valider)
    for r in neuf[~neuf["Ticker"].isin(cotes)].itertuples():
        rejets.append((r.Ticker, r.Societe, r.Indice, "aucune cotation Yahoo"))
    neuf = neuf[neuf["Ticker"].isin(cotes)]

    fonds["Region"] = "Europe"
    fonds["acwi"] = np.where(fonds["Ticker"].isin(acwi), "OUI", "NON")
    ajout = pd.DataFrame({
        "Ticker": neuf["Ticker"], "Symbole StockTrak": "", "Societe": neuf["Societe"],
        "Pays": neuf["Pays"], "Secteur": neuf["Secteur"], "verifie_stocktrak": "",
        "devise_stocktrak": "", "Region": neuf["Region"], "Indice": neuf["Indice"],
        # Un titre nouveau n'est jamais StockTrak : seul Jad peut ecrire OUI.
        "contrainte_europe": np.where(neuf["Region"] == "Europe", "OUI", "NON"),
        "contrainte_stocktrak": "NON",
        "acwi": np.where(neuf["Ticker"].isin(acwi), "OUI", "NON")})
    # Une contrainte deja posee a la main sur une ligne hors fonds l'emporte.
    for c in ("contrainte_europe", "contrainte_stocktrak"):
        ajout[c] = [anc.at[t, c] if t in anc.index and isinstance(anc.at[t, c], str) else v
                    for t, v in zip(ajout["Ticker"], ajout[c])]
    univers = pd.concat([fonds, ajout], ignore_index=True)
    rej = pd.DataFrame(rejets, columns=["Ticker", "Societe", "Indice", "motif"])

    print(f"\nunivers final : {len(univers)} titres, dont {(univers['acwi'] == 'OUI').sum()} MSCI ACWI")
    print(univers.groupby("Region").size().to_string())
    print(f"rejets : {len(rej)}")
    print(rej["motif"].str.split(" :| \\(").str[0].value_counts().to_string())
    if not essai:
        univers.to_csv(cfg.DATA / "univers.csv", index=False)
        rej.to_csv(cfg.DATA / "univers_rejets.csv", index=False)
        print("ecrit : data/univers.csv, data/univers_rejets.csv, data/msci_acwi.csv")
    return univers


if __name__ == "__main__":
    construire(essai="--essai" in sys.argv)


