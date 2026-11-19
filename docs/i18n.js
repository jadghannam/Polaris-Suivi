/* Langue de l'interface (19/11/2026) : francais (reference) ou anglais.
   Le code de la page et le programme ecrivent en francais ; en anglais, cette
   couche traduit ce qui s'affiche : textes fixes, textes avec des nombres
   (regles a motif), verdicts, zones, motifs, secteurs, pays, regions. Le
   journal d'execution technique reste en francais.
   Charge AVANT les autres scripts : LANG et LOCALE servent aussi au format
   des nombres et des dates. */
(function(){
"use strict";
let lang="fr";
try{lang=localStorage.getItem("polaris_langue")||"fr"}catch(e){}
window.LANG=lang==="en"?"en":"fr";
window.LOCALE=window.LANG==="en"?"en-GB":"fr-FR";
window.choisirLangue=l=>{try{localStorage.setItem("polaris_langue",l)}catch(e){} location.reload()};
document.documentElement.lang=window.LANG;
if(window.LANG!=="en"){window.T=s=>s;return}

/* ------------------------------------------------- textes exacts ------- */
const D={
// navigation, en-tete
"Portefeuille":"Portfolio","Synthèse":"Summary","Lignes et recommandations":"Holdings and recommendations",
"Remplaçants":"Replacements","Obligations":"Bonds","Mise à jour":"Update","Outils":"Tools",
"Univers":"Universe","Backtest":"Backtest","Polaris — fonds StockTrak":"Polaris — StockTrak fund",
"+ Nouveau portefeuille…":"+ New portfolio…","Réparti MSCI ACWI":"MSCI ACWI allocation",
"Classement global":"Global ranking","🔒 Europe · StockTrak":"🔒 Europe · StockTrak",
"Suivi des portefeuilles":"Portfolio monitoring","Suivi du fonds · groupe G2 · Master 222":"Fund monitoring · group G2 · Master 222",
"Polaris — Suivi du fonds":"Polaris — Fund monitoring","Données du":"Data as of","Positions :":"Positions:",
"Chargement…":"Loading…","Langue":"Language","lignes":"holdings","ligne":"holding","saisie initiale":"initial entry",
// tuiles
"Valeur du fonds":"Fund value","Actions":"Equities","Obligations et ETF":"Bonds and ETFs","Liquidités":"Cash",
"non saisies":"not entered","Performance des lignes":"Holdings performance","Signaux":"Signals",
"Poche actions":"Equity sleeve","Transactions":"Transactions","Prochain comité":"Next committee",
"Contre l'indice":"Versus the index","en euros":"in euros","restantes":"remaining","· écart":"· gap",
"de rotation · rythme":"turnover · pace",
// tableaux
"Titre":"Stock","Secteur":"Sector","Poids":"Weight","Perf.":"Perf.","vs indice":"vs index","Jour":"Day",
"Secteur jour":"Sector day","Rang":"Rank","Seuil":"Threshold","Marge":"Margin","Zone":"Zone",
"StockTrak":"StockTrak","Pays":"Country","Verdict":"Verdict","Cours":"Price","À acheter":"To buy",
"Montant":"Amount","Région":"Region","Perf. €":"Perf. €","Perf. locale":"Local perf.","Rang entrée":"Entry rank",
"Marge DCF":"DCF margin","Symbole":"Symbol","Type":"Type","Description":"Description","Quantité":"Quantity",
"Devise":"Currency","Prix payé":"Price paid","Valeur €":"Value €","Motif":"Reason","Depuis":"Since",
"Obligation":"Bond","Score":"Score","Crédit /25":"Credit /25","Risque /25":"Risk /25","Valo. /25":"Valuation /25",
"Divers. /15":"Divers. /15","Horizon /10":"Horizon /10","YTM":"YTM","Duration":"Duration",
"Alpha central":"Central alpha","Alpha stress":"Stress alpha","GP/A ajusté":"Adj. GP/A","B/M":"B/M",
"Pct rentab.":"Profit. pct","Pct valo.":"Value pct","Verdict DCF":"DCF verdict","#":"#",
"obligation":"bond","future":"future","ETF":"ETF","détenue":"held",
// sections
"À surveiller":"To monitor","Remplaçants prêts":"Ready replacements","Remplaçants éligibles":"Eligible replacements",
"Obligations détenues":"Bonds held","Disponibles, non investies":"Available, not invested",
"Blocages":"Blocks","Journal d'exécution":"Run log","dernier passage du programme":"latest program run",
"Expositions":"Exposures","ce que le bottom-up ne choisit pas, mais qu'il faut voir":"what bottom-up does not choose, but must be watched",
"Régions":"Regions","Devises":"Currencies","Secteurs":"Sectors","Lignes":"Holdings","Statistiques":"Statistics",
"rendements mensuels en euros, dividendes compris":"monthly returns in euros, dividends included",
"Quintiles du score combiné":"Combined-score quintiles",
"Q1 = meilleurs scores · la prime existe si l'escalier descend":"Q1 = best scores · the premium exists if the staircase goes down",
"Rebalancements":"Rebalancings","Limites":"Limitations","Allocation MSCI ACWI":"MSCI ACWI allocation",
"Toutes les lignes sont en zone OK.":"All holdings are in the OK zone.",
"Aucun candidat éligible aujourd’hui.":"No eligible candidate today.",
"Aucune obligation du classeur détenue.":"No bond from the workbook is held.",
"Exécutable maintenant":"Executable now",
// boutons, formulaires
"bloquer":"block","bloqué":"blocked","débloquer":"unblock","Envoyer le compte":"Send the account",
"Envoyer l'export et le compte":"Send the export and the account","Enregistrer":"Save","Oublier la clé":"Forget the key",
"Mettre à jour les positions":"Update positions","Transactions consommées":"Transactions used","Liquidités (€)":"Cash (€)",
"Glisse l'export ici ou":"Drop the export here or","parcours":"browse","Clé GitHub":"GitHub key","Dépôt":"Repository",
"utiliser":"use","— à corriger":"— to be corrected","— ta saisie s'en écarte":"— your entry differs",
"Exporter en PDF":"Export to PDF","Fermer":"Close","Poser un veto":"Place a veto","Lever le veto":"Lift the veto",
"Archiver ce portefeuille":"Archive this portfolio","Annuler":"Cancel","Créer":"Create","Appliquer":"Apply","Source":"Source",
"Nouveau portefeuille":"New portfolio","Nom":"Name","Nombre de lignes":"Number of holdings","Capital (€)":"Capital (€)",
"Indice de comparaison":"Benchmark index","Répartition":"Allocation",
"Pondérations MSCI ACWI par région, classement dans chaque région":"MSCI ACWI weights by region, ranking within each region",
"Libre : les N premiers du classement global, équipondérés":"Free: top N of the global ranking, equal-weighted",
"Contrainte Europe — région Europe uniquement":"Europe constraint — Europe region only",
"Contrainte StockTrak — titres vérifiés dans StockTrak":"StockTrak constraint — stocks verified in StockTrak",
"Contrainte Europe":"Europe constraint","Contrainte StockTrak":"StockTrak constraint","Toutes régions":"All regions",
"Classés seulement":"Ranked only","Classer par région":"Rank by region","Rechercher un titre":"Search a stock",
"Afficher 100 de plus":"Show 100 more","Fiche indisponible":"Sheet unavailable",
// fiche
"POLARIS · FICHE D'ANALYSE":"POLARIS · ANALYSIS SHEET","Score combiné":"Combined score","Liste de suivi":"Watch list",
"Oui":"Yes","Non":"No","50 % rentabilité · 50 % valorisation":"50% profitability · 50% valuation",
"1 · Classement Novy-Marx (2013)":"1 · Novy-Marx ranking (2013)","2 · DCF inversé":"2 · Reverse DCF",
"Rentabilité brute / actif (GP/A)":"Gross profit / assets (GP/A)","Médiane du secteur":"Sector median",
"GP/A ajusté du secteur":"Sector-adjusted GP/A","Book-to-market":"Book-to-market","Capitalisation":"Market cap",
"Percentile de rentabilité":"Profitability percentile","Percentile de valorisation":"Valuation percentile",
"FCFF normatif (moyenne 3 ans)":"Normalised FCFF (3-year average)","WACC":"WACC",
"Valeur d'entreprise de marché":"Market enterprise value","Dette nette":"Net debt",
"Croissance implicite g₁ (5 ans)":"Implied growth g₁ (5 years)","CAGR du CA retenu":"Revenue CAGR used",
"Seuil de veto":"Veto threshold","Marge (g₁ − seuil)":"Margin (g₁ − threshold)",
"Dispersion pour ±50 pb de WACC":"Dispersion for ±50 bp of WACC","g₁ implicite":"implied g₁",
"CAGR retenu":"CAGR used","Exercice":"Fiscal year","Chiffre d'affaires":"Revenue","Marge brute":"Gross margin",
"EBIT":"EBIT","Marge EBIT":"EBIT margin","Actif total":"Total assets","GP/A":"GP/A","Fonds propres":"Equity","FCFF":"FCFF",
"Document d'analyse, pas un conseil en investissement":"Analysis document, not investment advice",
"veto qualitatif actif":"qualitative veto active","planchers franchis":"floors passed","sous un plancher":"below a floor",
"univers du fonds (Europe · StockTrak)":"fund universe (Europe · StockTrak)","univers mondial":"world universe",
"Pas de verdict":"No verdict",
"Le marché n'anticipe aucune croissance au-delà de la croissance perpétuelle : le cours ne demande rien que l'entreprise n'ait déjà prouvé.":
"The market expects no growth beyond perpetual growth: the price asks for nothing the company has not already proven.",
"Le marché demande moins de croissance que celle que la société a réellement réalisée.":"The market asks for less growth than the company has actually achieved.",
"Le marché demande plus que l'historique, mais dans la marge de tolérance : titre à surveiller.":"The market asks for more than history, but within the tolerance margin: stock to monitor.",
"Veto quantitatif : le cours suppose nettement plus de croissance que l'entreprise n'a su en produire.":"Quantitative veto: the price implies clearly more growth than the company has been able to deliver.",
"Abstention : la valeur dépend davantage du taux d'actualisation que de l'entreprise (dispersion > 40 % pour ±50 pb de WACC).":"Abstention: the value depends more on the discount rate than on the company (dispersion > 40% for ±50 bp of WACC).",
"Flux normatif négatif : le modèle ne s'applique pas.":"Negative normalised flow: the model does not apply.",
"Données incomplètes : le DCF n'a pas pu être calculé.":"Incomplete data: the DCF could not be computed.",
"Attention :":"Warning:","book-to-market hors plage plausible, donnée à vérifier avant toute décision.":"book-to-market outside the plausible range, data to check before any decision.",
"La rentabilité brute est rapportée à l'actif puis comparée à la médiane du secteur GICS, parce que l'intensité capitalistique varie d'un secteur à l'autre. Les deux jambes sont négativement corrélées : leur combinaison est moins volatile que chacune. Planchers : 40":
"Gross profit is scaled by assets and compared with the GICS sector median, because capital intensity differs across sectors. The two legs are negatively correlated: their combination is less volatile than either. Floors: 40",
"percentile de rentabilité, 30":"percentile for profitability, 30","de valorisation.":"for valuation.",
"On ne cherche pas la valeur de l'action : on résout la croissance du flux que le cours suppose, et on la compare à celle que la société a réellement réalisée. Seuil = CAGR + max(50 % × |CAGR| ; 1,5 pt), jamais sous la croissance perpétuelle de 2 %.":
"We do not estimate the share's value: we solve for the cash-flow growth the price implies, and compare it with what the company actually achieved. Threshold = CAGR + max(50% × |CAGR|; 1.5 pt), never below the 2% perpetual growth.",
"Historique non encore collecté pour ce titre (rafraîchi chaque semaine).":"History not yet collected for this stock (refreshed weekly).",
// zones et verdicts
"OK":"OK","surveillance":"watch","sortie":"exit","en attente":"pending",
"A - Le marche n'attend aucune croissance":"A - The market expects no growth",
"B - Attente inferieure a l'historique realise":"B - Expectation below realised history",
"C - Attente superieure a l'historique, dans la marge":"C - Expectation above history, within the margin",
"D - VETO QUANTITATIF":"D - QUANTITATIVE VETO","ABSTENTION - modele non discriminant":"ABSTENTION - model not discriminating",
"FLUX NEGATIF - modele inapplicable":"NEGATIVE FLOW - model not applicable","DONNEES INCOMPLETES":"INCOMPLETE DATA",
"FLUX NEGATIF":"NEGATIVE FLOW","DONNEES INCOMPLETES.":"INCOMPLETE DATA.","ABSTENTION":"ABSTENTION",
// secteurs
"Consommation de base":"Consumer Staples","Consommation discretionnaire":"Consumer Discretionary","Energie":"Energy",
"Industrie":"Industrials","Materiaux":"Materials","Sante":"Health Care","Services aux collectivites":"Utilities",
"Services de communication":"Communication Services","Technologies de l'information":"Information Technology",
// regions
"Europe":"Europe","Amerique du Nord":"North America","Japon":"Japan","Pacifique":"Pacific","Chine":"China",
"Coree":"Korea","Taiwan":"Taiwan","Inde":"India","Asie emergente":"Emerging Asia","Amerique latine":"Latin America",
"Moyen-Orient et Afrique":"Middle East and Africa",
// pays
"Royaume-Uni":"United Kingdom","France":"France","Allemagne":"Germany","Suisse":"Switzerland","Pays-Bas":"Netherlands",
"Espagne":"Spain","Italie":"Italy","Suede":"Sweden","Danemark":"Denmark","Belgique":"Belgium","Finlande":"Finland",
"Norvege":"Norway","Autriche":"Austria","Irlande":"Ireland","Pologne":"Poland","Grece":"Greece","Etats-Unis":"United States",
"Coree du Sud":"South Korea","Australie":"Australia","Nouvelle-Zelande":"New Zealand","Singapour":"Singapore",
"Bresil":"Brazil","Arabie saoudite":"Saudi Arabia","Afrique du Sud":"South Africa","Mexique":"Mexico",
"Malaisie":"Malaysia","Thailande":"Thailand","Indonesie":"Indonesia","Turquie":"Turkey",
"Emirats arabes unis":"United Arab Emirates","Koweit":"Kuwait","Chili":"Chile","Perou":"Peru","Colombie":"Colombia",
"Hongrie":"Hungary","Republique tcheque":"Czech Republic","Egypte":"Egypt","Israel":"Israel",
// rappels, divers
"Revue annuelle des vetos et des verifications StockTrak":"Annual review of vetoes and StockTrak checks",
"Mise a jour annuelle Damodaran disponible":"Annual Damodaran update available",
"Chaque veto repose-t-il encore sur un fait etabli ? Chaque titre verifie l'est-il toujours ?":
"Does each veto still rest on an established fact? Is each verified stock still verified?",
"achat a la cible":"purchase at target","achat au maximum des liquidites disponibles":"purchase at the maximum available cash",
"historique 10 ans":"10-year history","repli : mediane du secteur":"fallback: sector median",
"repli : mediane du secteur dans la region":"fallback: sector median within the region",
"convention du fonds (septembre 2026)":"fund convention (September 2026)",
"Damodaran region x secteur, prime du pays":"Damodaran region × sector, country premium",
"convention du fonds, decalee de l'ecart de taux":"fund convention, shifted by the rate gap",
"Données officielles à jour.":"Official data up to date.",
"Envoi reçu ; en attente du recalcul officiel par le programme.":"Upload received; waiting for the program's official recalculation.",
"Les données du programme ne sont pas encore chargées.":"The program's data is not loaded yet.",
"Table proposée introuvable.":"Proposed table not found.",
"Remplaçants recalculés par le programme.":"Replacements recalculated by the program.",
"Toute ligne de l'export absente de l'univers est traitée comme un ETF : elle compte dans la valeur du fonds et l'allocation, sans classement ni DCF.":
"Any export line missing from the universe is treated as an ETF: it counts in the fund value and allocation, without ranking or DCF.",
"Éligible : liste de suivi (60 premiers), deux planchers franchis, verdict DCF A ou B, aucun veto qualitatif, négociable sur StockTrak. Clique un nom pour sa fiche d'analyse.":
"Eligible: watch list (top 60), both floors passed, DCF verdict A or B, no qualitative veto, tradable on StockTrak. Click a name for its analysis sheet.",
"Un titre bloqué reste calculé et visible, mais n'est plus proposé comme remplaçant : le suivant dans le classement prend sa place. Le clic écrit directement dans":
"A blocked stock is still computed and shown, but is no longer proposed as a replacement: the next one in the ranking takes its place. The click writes directly to",
"Après chaque passage d'ordres : corrige les deux chiffres lus dans StockTrak, puis dépose l'export. La page se met à jour tout de suite, puis le programme recalcule tout avec les cours Yahoo du moment, en quelques minutes.":
"After each round of orders: correct the two figures read in StockTrak, then drop the export. The page updates immediately, then the program recalculates everything with current Yahoo prices, within a few minutes.",
"Les poids suivent l'indice : ils sont relus dans les fichiers iShares MSCI World et Emerging Markets à chaque reconstruction de l'univers. Un portefeuille « réparti ACWI » donne à chaque région exactement son poids.":
"Weights follow the index: they are re-read from the iShares MSCI World and Emerging Markets files at each universe rebuild. An “ACWI-allocated” portfolio gives each region exactly its weight.",
"Construit par la méthode au prochain passage du programme : les N premiers rangs de la liste de suivi de l'univers choisi, verdict DCF A ou B, sans veto, équipondérés. Décoche les contraintes pour l'ouvrir au-delà de l'univers du fonds.":
"Built by the method at the next program run: the top N of the chosen universe's watch list, DCF verdict A or B, no veto, equal-weighted. Untick the constraints to open it beyond the fund's universe.",
"Portefeuille introuvable. S'il vient d'être créé, le programme le construira à son prochain passage (quelques minutes).":
"Portfolio not found. If it was just created, the program will build it at its next run (a few minutes).",
"Classement « monde » pas encore calculé : il le sera au prochain passage du programme.":"“World” ranking not computed yet: it will be at the next program run.",
"Backtest pas encore calculé : il l'est chaque samedi.":"Backtest not computed yet: it runs every Saturday.",
"Stratégie":"Strategy","Univers équipondéré":"Equal-weighted universe",
"Performance cumulée":"Cumulative performance","Rendement annualisé":"Annualised return","Volatilité annualisée":"Annualised volatility",
"Ratio de Sharpe":"Sharpe ratio","Perte maximale":"Maximum drawdown","Bêta":"Beta","Tracking error":"Tracking error",
"Ratio d'information":"Information ratio","Mois battant la référence":"Months beating the benchmark",
"Polaris (Europe · StockTrak)":"Polaris (Europe · StockTrak)","Univers mondial, 40 lignes réparties ACWI":"World universe, 40 holdings ACWI-allocated",
"Classement seul : ni DCF inverse ni veto qualitatif (historique de flux trop court).":"Ranking only: no reverse DCF or qualitative veto (cash-flow history too short).",
"Biais du survivant : univers d'aujourd'hui, societes disparues absentes.":"Survivorship bias: today's universe, delisted companies absent.",
"Environ trois ans : trop court pour conclure sur une prime, utile pour verifier la mecanique.":"About three years: too short to conclude on a premium, useful to check the mechanics.",
"Cours ajustes des dividendes ; frais de transaction non deduits.":"Dividend-adjusted prices; transaction costs not deducted.",
};

/* ------------------------------------------- textes a motif (nombres) -- */
const R=[
[/^Au comité du (.+)$/,"At the committee of $1"],
[/^depuis le lancement, sur un capital de (.+) €$/,"since launch, on a capital of $1 €"],
[/^(\d+) lignes? · (\d+) ETF à part$/,"$1 holdings · $2 ETFs separately"],
[/^(\d+) lignes?$/,"$1 holdings"],[/^(\d+) surveillance$/,"$1 on watch"],[/^(\d+) sortie$/,"$1 exit"],
[/^(\d+) lignes · triées par urgence$/,"$1 holdings · sorted by urgency"],
[/^(\d+) lignes? hors zone OK$/,"$1 holding(s) outside the OK zone"],
[/^(\d+) éligibles?$/,"$1 eligible"],
[/^(\d+) titres? non négociables? sur StockTrak$/,"$1 stock(s) not tradable on StockTrak"],
[/^(\d+) sur (\d+) notées · score horizon \/100$/,"$1 of $2 rated · horizon score /100"],
[/^(\d+) obligations · triées par score$/,"$1 bonds · sorted by score"],
[/^période en cours :$/,"current period:"],
[/^comités restants$/,"committees remaining"],
[/^restantes · (\d+) comités restants$/,"remaining · $1 committees remaining"],
[/^· (\d+) comités restants$/,"· $1 committees remaining"],
[/^échanges max · (\d+) comités restants$/,"exchanges max · $1 committees remaining"],
[/^export StockTrak du (.+)$/,"StockTrak export of $1"],[/^Clôtures du$/,"Closes of"],
[/^Valeur à vérifier :$/,"Value to check:"],
[/^pas de cours ou de change du jour pour (.+) ; leur dernière valeur publiée est reprise, la ligne n'est pas retirée du total\.$/,
 "no price or exchange rate today for $1; their last published value is used, the holding is not removed from the total."],[/^aperçu (.+)$/,"preview $1"],
[/^(\d+) \/ (\d+) clôtures(.*)$/,(m,a,b,c)=>`${a} / ${b} closes${c.replace(" — confirmée"," — confirmed").replace(/acheter\s*$/,"buy ")}`],
[/^(.*) · acheter$/,"$1 · buy"],
[/^(\d+) clôtures? \/ (\d+)(.*)$/,(m,a,b,c)=>`${a} close(s) / ${b}${c.replace(" — confirmée"," — confirmed")}`],
[/^ · acheter$/," · buy"],[/^acheter$/,"buy"],
[/^\(rang (.+)\)$/,"(rank $1)"],[/^→ (.+) \(rang (.+)\)$/,"→ $1 (rank $2)"],
[/^remplace (.+) dans le plan du jour$/,"replaces $1 in today's plan"],
[/^marge DCF (.+)$/,"DCF margin $1"],[/^GP\/A ajuste (.+)$/,"adj. GP/A $1"],[/^rang (\d+)$/,"rank $1"],
[/^rang introuvable \(plancher ou liquidite\)$/,"rank not found (floor or liquidity)"],
[/^decrochage (.+) vs indice$/,"drawdown $1 vs index"],
[/^cours indisponible aujourd'hui$/,"price unavailable today"],
[/^cours de l'export StockTrak \(Yahoo indisponible\)$/,"price from the StockTrak export (Yahoo unavailable)"],
[/^bloque dans StockTrak, donc sans rang : a arbitrer en comite$/,"blocked in StockTrak, hence unranked: to be decided in committee"],
[/^book-to-market implausible \((.+)\) : donnee a verifier, aucun signal tire du cours$/,"implausible book-to-market ($1): data to check, no signal drawn from the price"],
[/^En attente de confirmation \((\d+) \/ (\d+) clôtures\)$/,"Awaiting confirmation ($1 / $2 closes)"],
[/^Pas de vente avant la (\d+)e clôture, même en comité\.$/,"No sale before close no. $1, not even at the committee."],
[/^sortie non confirmee \((\d+) \/ (\d+) clotures\) : pas de vente avant la (\d+)e cloture, meme en comite$/,"exit not confirmed ($1 / $2 closes): no sale before close no. $3, not even at the committee"],
[/^sortie confirmee, remplacant disponible, (\d+) transactions restantes dans l'enveloppe apres l'echange$/,"confirmed exit, replacement available, $1 transactions left in the envelope after the exchange"],
[/^enveloppe de la periode epuisee \((.+)\)$/,"period envelope exhausted ($1)"],
[/^echanges reserves aux comites \(config\.py\)$/,"exchanges reserved for committees (config.py)"],
[/^pas de remplacement : (.+) EUR achetables, sous (.+) de la cible ; la vente reste en liquidites$/,"no replacement: $1 EUR purchasable, below $2 of the target; the sale proceeds stay in cash"],
[/^aucun remplacant eligible : la ligne n'est pas vendue \(pas de sortie sans remplacant\)$/,"no eligible replacement: the holding is not sold (no exit without a replacement)"],
[/^historique (\d+) ans(.*)$/,(m,a,b)=>`${a}-year history${b.replace("saisi en septembre 2026","entered in September 2026").replace(/prolonge avec Yahoo jusqu'en (\d+)/,"extended with Yahoo to $1").replace(/Yahoo, (\d+) exercices/,"Yahoo, $1 fiscal years")}`],
[/^(\d+) taux sans risque saisis a la main$/,"$1 risk-free rates entered by hand"],
[/^(\d+) historiques de CA a verifier$/,"$1 revenue histories to check"],
[/^(.+) : aucune source gratuite\. A recaler chaque annee dans config\.py\.$/,"$1: no free source. To be updated every year in config.py."],
[/^(.+) : exercice (\d+) absent chez Yahoo : pas de point de comparaison$/,"$1: fiscal year $2 missing at Yahoo: no comparison point"],
[/^échéance (.+)$/,"due $1"],
[/^capitalisation (.+) Md€$/,"market cap €$1bn"],[/^marge (.+) contre le seuil$/,"margin $1 versus the threshold"],
[/^(.+) titres · (.+) classés · (.+) affichés sur (.+)$/,"$1 stocks · $2 ranked · $3 shown of $4"],
[/^(\d+) titres · équipondérés à la construction$/,"$1 stocks · equal-weighted at construction"],
[/^(\d+) titres? classés$/,"$1 ranked"],
[/^(\d+) titres(.*)$/,(m,a,b)=>`${a} stocks${b.replace(" · rang dans leur région"," · rank within their region")}`],
[/^construit le (.+) sur (.+) € · univers$/,"built on $1 with €$2 · universe"],
[/^hors financières et immobilier, ramenée à 100 % · fichiers iShares du (.+)$/,"excluding financials and real estate, rescaled to 100% · iShares files of $1"],
[/^(.+) · (\d+) titres classés : (.+)$/,"$1 · $2 stocks ranked: $3"],
[/^Stratégie \((\d+) lignes\)$/,"Strategy ($1 holdings)"],
[/^(.+) → (.+) · calculé le (.+)$/,"$1 → $2 · computed on $3"],
[/^(.+) n'est pas dans les classements publiés\.$/,"$1 is not in the published rankings."],
[/^Classement « (.+) » pas encore calculé : il le sera au prochain passage du programme\.$/,"“$1” ranking not computed yet: it will be at the next program run."],
[/^Dans l'univers mondial, le titre est (\d+)$/,"In the world universe, the stock ranks $1"],
[/^(.+) \(millions de (.+)\)$/,"$1 (millions of $2)"],[/^\(millions de (.+)\)$/,"(millions of $1)"],
[/^3 · Comptes publiés$/,"3 · Published accounts"],
[/^portefeuille · ACWI$/,"portfolio · ACWI"],
[/^→ (.+) \(rang (\d+)\)(.*)$/,(m,a,b,c)=>`→ ${a} (rank ${b})${c.replace("acheter","buy")}`],
[/^hors classement et DCF$/,"outside ranking and DCF"],
[/^sur (\d+)\.$/,"out of $1."],[/^Dans l'univers mondial, le titre est (\d+)$/,"In the world universe, the stock ranks $1"],
[/^Surveillance : rang > (\S+), ou marge du DCF au-dessus de (.+?), ou décrochage de (.+?) contre l'indice\. Sortie : rang > (\S+), marge positive confirmée sur (\d+) clôtures, ou décrochage de (.+?)\. Aucune sortie sans remplaçant\. Poids exprimés en part du fonds entier \(actions, ETF, liquidités\)\.$/,
 "Watch: rank > $1, or DCF margin above $2, or drawdown of $3 versus the index. Exit: rank > $4, positive margin confirmed over $5 closes, or drawdown of $6. No exit without a replacement. Weights as a share of the whole fund (equities, ETFs, cash)."],
[/^Échange : la ligne sortante est vendue à 100 % ; .* réserve de (.+?) du fonds \((.+?) € disponibles aujourd'hui\)\. Si l'on ne peut pas acheter au moins (.+?) de la cible, .* \(1\/N du jour, (.+?) €\)\. .*$/,
 "Exchange: the exiting holding is sold 100%; the replacement is bought at the “best possible 1/N”, the average value of the other holdings, (sleeve − holding sold) / (N − 1). The sale pays first; a surplus stays in cash; a shortfall is taken from cash above the $1 fund reserve (€$2 available today). If at least $3 of the target cannot be bought, the holding is not replaced: the proceeds stay in cash. A replacement with no matching exit shows an indicative amount (today's 1/N, €$4). Whole shares at the closing price, to be readjusted to the StockTrak price when placing the order. Other holdings are not rebalanced."],
[/^Détenues mais absentes du classeur, donc non notées : (.+)\.$/,"Held but missing from the workbook, hence not rated: $1."],
[/^Données du classeur au (.+), horizon de liquidation le (.+) \((.+) an\)\. Alpha = .* Stress : \+50 pb Bund et \+50 pb spread\.$/,
 "Workbook data as of $1, liquidation horizon $2 ($3 year). Alpha = approximate total return at the horizon (YTM × H − duration × shock) minus that of the IG index. Stress: +50 bp Bund and +50 bp spread."],
[/^Clé GitHub : à coller une seule fois pour envoyer les exports$/,"GitHub key: paste once to send the exports"],
[/^Clé GitHub enregistrée dans ce navigateur \((.+)\) · dépôt (.+)$/,"GitHub key saved in this browser ($1) · repository $2"],
[/^Créer la clé : github\.com → Settings → Developer settings → Personal access tokens →$/,"Create the key: github.com → Settings → Developer settings → Personal access tokens →"],
[/^→ Generate new token, accès au$/,"→ Generate new token, access to the"],[/^seul dépôt de la plateforme$/,"platform repository only"],
[/^, permission$/,", permission"],
[/^et rien d'autre, expiration au 31 mars 2027\. Elle reste dans ce navigateur et n'est jamais écrite dans la page\.$/,"and nothing else, expiring on 31 March 2027. It stays in this browser and is never written into the page."],
[/^Le classement est refait dans l'univers coché : .*$/,"The ranking is recomputed within the ticked universe: percentiles, sector medians and floors depend on the universe. With both constraints, it is exactly the fund's ranking. Click a row for its analysis sheet."],
[/^Classé par région : le rang est celui du titre$/,"Ranked by region: the rank is the stock's rank"],[/^dans sa région$/,"within its region"],
[/^juillet, comptes clos au moins 4 mois avant$/,"July, accounts closed at least 4 months before"],
[/^· (\d+) titres classés : (.+)$/,"· $1 stocks ranked: $2"],
[/^Montant cible : 1\/N de la valeur actuelle du portefeuille, soit$/,"Target amount: 1/N of the portfolio's current value, i.e."],
[/^Construit par la méthode : (.*)$/,"Built by the method: see the rules in the documentation; zones are the fund's; nothing is sold automatically. Performance in euros, currency effects included."],
[/^Polaris · Novy-Marx \(2013\), « The Other Side of Value », JFE 108\(1\) · données Yahoo Finance$/,"Polaris · Novy-Marx (2013), “The Other Side of Value”, JFE 108(1) · Yahoo Finance data"],
];
function tr(s){
  const k=s.replace(/\s+/g," ").trim(); if(!k) return s;
  let r=D[k];
  if(r==null) for(const [re,en] of R){ if(re.test(k)){ r=k.replace(re,en); break } }
  if(r==null) return s;
  const debut=s.match(/^\s*/)[0], fin=s.match(/\s*$/)[0];
  return debut+r+fin;
}
window.T=tr;
const ATTR=["title","placeholder","aria-label"];
function traduire(n){
  if(n.nodeType===3){ const t=tr(n.nodeValue); if(t!==n.nodeValue) n.nodeValue=t; return }
  if(n.nodeType!==1||n.tagName==="SCRIPT"||n.tagName==="STYLE"||n.classList?.contains("jrn")) return;
  for(const a of ATTR){ const v=n.getAttribute&&n.getAttribute(a); if(v){const t=tr(v); if(t!==v) n.setAttribute(a,t)} }
  for(const c of n.childNodes) traduire(c);
}
const obs=new MutationObserver(ms=>{for(const m of ms){
  if(m.type==="characterData") traduire(m.target);
  else m.addedNodes.forEach(traduire);
}});
const go=()=>{traduire(document.body);obs.observe(document.body,{childList:true,subtree:true,characterData:true});
  document.title=tr(document.title)};
if(document.body) go(); else document.addEventListener("DOMContentLoaded",go);
const c0=window.confirm.bind(window), p0=window.prompt.bind(window);
window.confirm=m=>c0(tr(String(m))); window.prompt=(m,d)=>p0(tr(String(m)),d);
})();
