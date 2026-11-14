/* Extension du 14/11/2026.
   - onglets : Polaris (contraintes verrouillees), portefeuilles personnels,
     Univers (contraintes a cocher), Backtest ;
   - creation d'un portefeuille : ecrit data/portefeuilles.json (cle GitHub),
     le programme le construit a son prochain passage ;
   - fiche d'analyse par titre, imprimable en PDF (A4).
   S'appuie sur les fonctions de la page : E, S, N, esc, cls, badge, jour, gh,
   cle, depot, toast, utf8b64, b64utf8, render, DATA. */
(function(){
"use strict";
const CACHE={};
async function charger(chemin){
  if(CACHE[chemin]!==undefined) return CACHE[chemin];
  try{
    const r=await fetch(chemin+"?"+Date.now(),{cache:"no-store"});
    CACHE[chemin]=r.ok?await r.json():null;
  }catch(e){CACHE[chemin]=null}
  return CACHE[chemin];
}
const CONTR={europe:"Europe",stocktrak:"StockTrak"};
const cleU=c=>{const s=[...new Set(c||[])].sort();return s.length?s.join("-"):"monde"};
const chips=c=>`<span class="chips">${Object.keys(CONTR).map(k=>
  `<span class="chip ${(c||[]).includes(k)?"":"off"}">${CONTR[k]}</span>`).join("")}</span>`;
const md=v=>v==null||isNaN(v)?"—":N(v/1000,1);          // millions -> milliards
const code=v=>String(v||"").split(" - ")[0].trim();

let ONGLET="polaris", PFS=null;
const KONG="polaris_onglet";
try{ONGLET=localStorage.getItem(KONG)||"polaris"}catch(e){}

/* ---------------------------------------------------------- squelette ---- */
const header=document.querySelector("header");
const nav=document.createElement("nav"); nav.className="onglets"; nav.id="onglets";
header.after(nav);
const vue=document.createElement("div"); vue.id="vue"; vue.hidden=true;
document.getElementById("app").after(vue);
const voile=document.createElement("div"); voile.id="fiche"; voile.className="voile"; voile.hidden=true;
document.body.appendChild(voile);
voile.addEventListener("click",e=>{if(e.target===voile) fermer()});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!voile.hidden) fermer()});
function fermer(){voile.hidden=true;voile.innerHTML="";document.body.classList.remove("imprime")}

function onglets(){
  const pf=(PFS?.portefeuilles||[]);
  const b=(id,html)=>`<button data-o="${esc(id)}" class="${ONGLET===id?"on":""}">${html}</button>`;
  nav.innerHTML=b("polaris",`Polaris <span class="verrou">🔒 Europe · StockTrak</span>`)
    +pf.map(p=>b("pf:"+p.id,esc(p.nom))).join("")
    +`<span class="sep"></span>`
    +b("univers","Univers")+b("backtest","Backtest")
    +`<button class="plus" data-o="nouveau">+ Nouveau portefeuille</button>`;
  nav.querySelectorAll("button").forEach(x=>x.onclick=()=>{
    const o=x.dataset.o; if(o==="nouveau"){formulaire();return}
    ONGLET=o; try{localStorage.setItem(KONG,o)}catch(e){} afficher();
  });
}
async function afficher(){
  onglets();
  const polaris=ONGLET==="polaris";
  document.getElementById("depot").hidden=!polaris;
  document.getElementById("app").hidden=!polaris;
  vue.hidden=polaris;
  if(polaris) return;
  vue.innerHTML='<p class="note">Chargement…</p>';
  try{
    if(ONGLET==="univers") await vueUnivers();
    else if(ONGLET==="backtest") await vueBacktest();
    else if(ONGLET.startsWith("pf:")) vuePortefeuille(ONGLET.slice(3));
  }catch(e){vue.innerHTML=`<div class="card err">${esc(e.message||e)}</div>`}
}

/* ------------------------------------------------ portefeuille perso ---- */
function repartition(titre,o){
  const l=Object.entries(o||{}).sort((a,b)=>b[1]-a[1]);
  return `<div class="panneau"><h3>${titre}</h3>${l.map(([k,v])=>`<div class="barre-l">
    <span class="t">${esc(k)}</span><span class="v">${E(v,1)}</span>
    <span class="b"><i style="width:${Math.max(1,v*100)}%"></i></span></div>`).join("")||'<p class="note">—</p>'}</div>`;
}
function vuePortefeuille(id){
  const p=(PFS?.portefeuilles||[]).find(x=>x.id===id);
  if(!p){vue.innerHTML=`<div class="card err">Portefeuille introuvable. S'il vient d'être créé,
    le programme le construira à son prochain passage (quelques minutes).</div>`;return}
  const rel=(p.perf??NaN)-(p.perf_indice??NaN);
  const ordre={sortie:0,surveillance:1,ok:2};
  const lignes=p.lignes.slice().sort((a,b)=>(ordre[a.zone]??3)-(ordre[b.zone]??3)||(a.rang??999)-(b.rang??999));
  const surv=lignes.filter(l=>l.zone==="surveillance").length, sort=lignes.filter(l=>l.zone==="sortie").length;
  const cu=p.cle_univers;
  vue.innerHTML=`<div class="tiles">
    <div class="tile large"><div class="k">${esc(p.nom)}</div>
      <div class="v">${N(p.valeur_eur)}<small>€</small>
        <span class="${cls(p.perf)}" style="font-size:16px;margin-left:12px">${S(p.perf,2)}</span></div>
      <div class="s">construit le ${esc(jour(p.date_creation))} sur ${N(p.capital)} € · univers ${chips(p.contraintes)}</div></div>
    <div class="tile"><div class="k">Contre l'indice</div>
      <div class="v ${cls(rel)}">${S(rel,2)}</div>
      <div class="s">${esc(p.indice_nom)} <b>${S(p.perf_indice,2)}</b> en euros</div></div>
    <div class="tile"><div class="k">Signaux</div>
      <div class="v">${surv+sort}<small>ligne${surv+sort>1?"s":""}</small></div>
      <div class="points"><span><i style="background:var(--warn)"></i>${surv} surveillance</span>
        <span><i style="background:var(--bad)"></i>${sort} sortie</span></div></div>
  </div>
  <h2>Expositions <span class="n">ce que le bottom-up ne choisit pas, mais qu'il faut voir</span></h2>
  <div class="repart">${repartition("Régions",p.repartition_region)}${repartition("Devises",p.repartition_devise)}
    ${repartition("Secteurs",p.repartition_secteur)}</div>
  <h2>Lignes <span class="n">${p.nb_lignes_reelles} titres · équipondérés à la construction</span></h2>
  <div class="card"><table><thead><tr><th class="l">Titre</th><th class="l">Région</th><th class="l">Secteur</th>
    <th>Poids</th><th>Perf. €</th><th>Perf. locale</th><th>vs indice</th><th>Rang entrée</th><th>Rang</th>
    <th class="l">Verdict</th><th>Marge</th><th class="zc">Zone</th></tr></thead><tbody>${lignes.map(l=>`<tr>
    <td class="l"><span class="soc lien-fiche" data-f="${esc(l.ticker)}" data-u="${esc(cu)}">${esc(l.societe)}</span><span class="tick">${esc(l.ticker)}</span>
      ${l.remplacant?`<div class="rempl vers">→ ${esc(l.remplacant.Societe)} (rang ${N(l.remplacant.rang)})</div>`:""}
      ${l.zone==="sortie"?`<div class="rempl">${l.clotures_consecutives} clôture(s)${l.sortie_confirmee?" — confirmée":""}</div>`:""}</td>
    <td class="l">${esc(l.region||"")}</td><td class="l">${esc(l.secteur||"")}</td><td>${E(l.poids)}</td>
    <td class="${cls(l.perf)}">${S(l.perf)}</td><td class="${cls(l.perf_locale)}">${S(l.perf_locale)}</td>
    <td class="${cls(l.perf_relative)}">${S(l.perf_relative)}</td>
    <td>${N(l.rang_entree)}</td><td>${N(l.rang)}</td><td class="l">${esc(code(l.verdict)||"—")}</td>
    <td class="${l.marge>0?"neg":"pos"}">${S(l.marge,2)}</td><td class="zc">${badge(l.zone)}</td></tr>`).join("")}
  </tbody></table></div>
  <p class="note">Construit par la méthode : les ${p.nb_lignes} premiers rangs de la liste de suivi de son univers,
    verdict DCF A ou B, sans veto qualitatif, équipondérés au cours du jour de construction. Les zones sont celles
    du fonds ; rien n'est vendu automatiquement. Performance en euros, change compris.</p>
  <p style="margin-top:18px"><button class="btn" id="archiver">Archiver ce portefeuille</button></p>`;
  liensFiche(vue);
  document.getElementById("archiver").onclick=()=>archiver(p);
}

/* ------------------------------------------------------------ univers ---- */
let FU={europe:true,stocktrak:true,q:"",region:"",classes:true,lim:100};
async function vueUnivers(){
  const c=Object.keys(CONTR).filter(k=>FU[k]);
  const k=cleU(c);
  const u=await charger(`classements/${k}.json`);
  if(!u){vue.innerHTML=`<div class="card err">Classement « ${esc(k)} » pas encore calculé : il le sera au prochain
    passage du programme.</div>`;return}
  const regions=[...new Set(u.lignes.map(l=>l.Region).filter(Boolean))].sort();
  const q=FU.q.trim().toLowerCase();
  let l=u.lignes.filter(x=>(!FU.classes||x.rang!=null)&&(!FU.region||x.Region===FU.region)
    &&(!q||(x.Societe||"").toLowerCase().includes(q)||(x.Ticker||"").toLowerCase().includes(q)));
  l.sort((a,b)=>(a.rang??1e9)-(b.rang??1e9)||(b.rang_combine??-1)-(a.rang_combine??-1));
  const tot=l.length; l=l.slice(0,FU.lim);
  vue.innerHTML=`<div class="filtres">
      <label><input type="checkbox" id="fEu" ${FU.europe?"checked":""}> Contrainte Europe</label>
      <label><input type="checkbox" id="fSt" ${FU.stocktrak?"checked":""}> Contrainte StockTrak</label>
      <select id="fRe"><option value="">Toutes régions</option>${regions.map(r=>
        `<option ${FU.region===r?"selected":""}>${esc(r)}</option>`).join("")}</select>
      <label><input type="checkbox" id="fCl" ${FU.classes?"checked":""}> Classés seulement</label>
      <input type="text" id="fQ" placeholder="Rechercher un titre" value="${esc(FU.q)}" style="width:220px">
      <span class="compte">${u.nb_titres} titres · ${u.nb_classes} classés · ${tot} affichés</span></div>
    <div class="card"><table><thead><tr><th>Rang</th><th class="l">Titre</th><th class="l">Pays</th><th class="l">Secteur</th>
      <th>GP/A ajusté</th><th>B/M</th><th>Pct rentab.</th><th>Pct valo.</th><th>Score</th>
      <th class="l">Verdict DCF</th><th>g₁</th><th>Seuil</th><th>Marge</th></tr></thead><tbody>${l.map(x=>`<tr class="clic" data-f="${esc(x.Ticker)}" data-u="${esc(k)}">
      <td>${x.rang!=null?N(x.rang):'<span class="tick">—</span>'}</td>
      <td class="l"><span class="soc">${esc(x.Societe)}</span><span class="tick">${esc(x.Ticker)}</span>
        ${x.veto_qualitatif?'<span class="badge b-sortie">veto</span>':""}${x.bm_implausible?'<span class="badge b-surv">B/M à vérifier</span>':""}</td>
      <td class="l">${esc(x.Pays||"")}</td><td class="l">${esc(x.Secteur||"")}</td>
      <td class="${cls(x["GP/A ajuste"])}">${S(x["GP/A ajuste"],1)}</td><td>${N(x["B/M"],2)}</td>
      <td>${E(x.rang_rentabilite,0)}</td><td>${E(x.rang_valorisation,0)}</td><td>${N(x.rang_combine*100,1)}</td>
      <td class="l">${esc(code(x.verdict)||"—")}</td><td>${E(x.g1,1)}</td><td>${E(x.seuil,1)}</td>
      <td class="${x.marge>0?"neg":"pos"}">${S(x.marge,1)}</td></tr>`).join("")}</tbody></table></div>
    ${tot>FU.lim?`<button class="btn plus-lignes" id="fPlus">Afficher 100 de plus</button>`:""}
    <p class="note">Le classement est refait dans l'univers coché : percentiles, médianes sectorielles et planchers
      dépendent de l'univers. Avec les deux contraintes, c'est exactement le classement du fonds. Clique une ligne
      pour sa fiche d'analyse.</p>`;
  const re=()=>{FU.lim=100;vueUnivers()};
  document.getElementById("fEu").onchange=e=>{FU.europe=e.target.checked;re()};
  document.getElementById("fSt").onchange=e=>{FU.stocktrak=e.target.checked;re()};
  document.getElementById("fRe").onchange=e=>{FU.region=e.target.value;re()};
  document.getElementById("fCl").onchange=e=>{FU.classes=e.target.checked;re()};
  let t; document.getElementById("fQ").oninput=e=>{clearTimeout(t);t=setTimeout(()=>{FU.q=e.target.value;re();
    const i=document.getElementById("fQ"); i.focus(); i.setSelectionRange(i.value.length,i.value.length)},250)};
  const p=document.getElementById("fPlus"); if(p) p.onclick=()=>{FU.lim+=100;vueUnivers()};
  liensFiche(vue);
}

/* ----------------------------------------------------------- backtest ---- */
let BT="polaris";
function courbe(series,couleurs){
  const noms=Object.keys(series).filter(k=>series[k]&&series[k].length);
  if(!noms.length) return "";
  const W=900,H=300,g=46,d=14,h=16,b=30;
  const toutes=noms.flatMap(k=>series[k]);
  const dates=[...new Set(toutes.map(p=>p.date))].sort();
  const vmin=Math.min(...toutes.map(p=>p.v)), vmax=Math.max(...toutes.map(p=>p.v));
  const x=dt=>g+(dates.indexOf(dt)/(dates.length-1||1))*(W-g-d);
  const y=v=>h+(1-(v-vmin)/((vmax-vmin)||1))*(H-h-b);
  const pas=(vmax-vmin)/4;
  let grille="";
  for(let i=0;i<=4;i++){const v=vmin+pas*i;
    grille+=`<line x1="${g}" x2="${W-d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/>
      <text x="${g-8}" y="${y(v)+4}" fill="var(--ink3)" font-size="11" text-anchor="end">${N((v-1)*100,0)} %</text>`;}
  const ans=dates.filter((dt,i)=>i===0||dt.slice(0,4)!==dates[i-1].slice(0,4));
  const ax=ans.map(dt=>`<text x="${x(dt)}" y="${H-8}" fill="var(--ink3)" font-size="11" text-anchor="middle">${dt.slice(0,4)}</text>`).join("");
  const lignes=noms.map(k=>`<polyline fill="none" stroke="${couleurs[k]||"var(--ink3)"}" stroke-width="${k==="strategie"?2.4:1.5}"
    points="${series[k].map(p=>`${x(p.date).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")}"/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Performance cumulée">${grille}${ax}${lignes}</svg>`;
}
async function vueBacktest(){
  const pf=(PFS?.portefeuilles||[]);
  const choix=[["polaris","Polaris (Europe · StockTrak)"],["monde","Univers mondial, 30 lignes"],
    ...pf.map(p=>[p.id,p.nom])];
  if(!choix.some(c=>c[0]===BT)) BT="polaris";
  const r=await charger(`backtest/${BT}.json`);
  const sel=`<div class="filtres"><select id="bSel">${choix.map(([k,n])=>`<option value="${esc(k)}" ${k===BT?"selected":""}>${esc(n)}</option>`).join("")}</select>
    ${r&&r.periode?`<span class="compte">${esc(jour(r.periode[0]))} → ${esc(jour(r.periode[1]))} · calculé le ${esc(jour(r.calcule_le))}</span>`:""}</div>`;
  if(!r||r.erreur){vue.innerHTML=sel+`<div class="card err">${r?esc(r.erreur):"Backtest pas encore calculé : il l'est chaque samedi."}</div>`;
    document.getElementById("bSel").onchange=e=>{BT=e.target.value;vueBacktest()};return}
  const coul={strategie:"#b8ccd6",univers_equipondere:"#b1bcaa",indice:"#d8c393"};
  const noms={strategie:`Stratégie (${r.nb_lignes} lignes)`,univers_equipondere:"Univers équipondéré",indice:r.indice_nom};
  const st=r.statistiques, ks=["strategie","univers_equipondere","indice"].filter(k=>st[k]);
  const ligne=(lib,f)=>`<tr><td class="l">${lib}</td>${ks.map(k=>`<td>${f(st[k]||{})}</td>`).join("")}</tr>`;
  const qs=[1,2,3,4,5].filter(k=>st["Q"+k]);
  const qmax=Math.max(...qs.map(k=>Math.abs(st["Q"+k].rendement_annualise||0)),0.01);
  vue.innerHTML=sel+`<div class="graphe"><div class="leg">${ks.map(k=>`<span style="--c:${coul[k]}">${esc(noms[k])}</span>`).join("")}</div>
      ${courbe(Object.fromEntries(ks.map(k=>[k,r.series[k]])),coul)}</div>
    <h2>Statistiques <span class="n">rendements mensuels en euros, dividendes compris</span></h2>
    <div class="card"><table><thead><tr><th class="l"></th>${ks.map(k=>`<th>${esc(noms[k])}</th>`).join("")}</tr></thead><tbody>
      ${ligne("Performance cumulée",s=>S(s.performance_cumulee,1))}
      ${ligne("Rendement annualisé",s=>S(s.rendement_annualise,1))}
      ${ligne("Volatilité annualisée",s=>E(s.volatilite,1))}
      ${ligne("Ratio de Sharpe",s=>N(s.sharpe,2))}
      ${ligne("Perte maximale",s=>E(s.perte_max,1))}
      ${ligne("Bêta",s=>N(s.beta,2))}
      ${ligne("Tracking error",s=>E(s.tracking_error,1))}
      ${ligne("Ratio d'information",s=>N(s.ratio_information,2))}
      ${ligne("Mois battant la référence",s=>E(s.mois_gagnants,0))}
    </tbody></table></div>
    <h2>Quintiles du score combiné <span class="n">Q1 = meilleurs scores · la prime existe si l'escalier descend</span></h2>
    <div class="panneau">${qs.map(k=>{const v=st["Q"+k].rendement_annualise;return `<div class="barre-l">
      <span class="t">Q${k}${k===1?" — meilleurs":k===5?" — moins bons":""}</span><span class="v ${cls(v)}">${S(v,1)}</span>
      <span class="b"><i style="width:${Math.abs(v||0)/qmax*100}%;background:${v>=0?"var(--menthe)":"var(--bad)"}"></i></span></div>`}).join("")}</div>
    <h2>Rebalancements <span class="n">1<sup>er</sup> juillet, comptes clos au moins 4 mois avant</span></h2>
    <div class="panneau compo">${r.rebalancements.map(c=>`<div><b>${esc(jour(c.date))}</b> · ${c.nb_classes} titres classés :
      ${c.titres.map(t=>esc(t.Societe)).join(", ")}</div>`).join("")}</div>
    <h2>Limites</h2><ul class="limites">${r.limites.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`;
  document.getElementById("bSel").onchange=e=>{BT=e.target.value;vueBacktest()};
}

/* ------------------------------------------------------- creation ------- */
function slug(s){return String(s).normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase()
  .replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,32)||"portefeuille"}
async function ecrireDefinitions(modifier,message){
  for(let essai=0;;essai++){
    try{
      const br=(await gh("")).default_branch; let liste=[],sha;
      try{const f=await gh(`/contents/data/portefeuilles.json?ref=${br}`);liste=JSON.parse(b64utf8(f.content));sha=f.sha}
      catch(e){if(e.status!==404) throw e}
      liste=modifier(liste);
      const corps={message,content:utf8b64(JSON.stringify(liste,null,1)+"\n"),branch:br}; if(sha) corps.sha=sha;
      await gh("/contents/data/portefeuilles.json",{method:"PUT",body:JSON.stringify(corps)}); return;
    }catch(e){if(!(e.status===409||e.status===422)||essai>=2) throw e}
  }
}
function exigerCle(){
  if(cle()&&depot()) return true;
  toast("Colle d'abord ta clé GitHub (onglet Polaris, en haut de la page).","ko"); return false;
}
function formulaire(){
  const ind=PFS?.indices||{"URTH":"MSCI World (ETF iShares URTH)","^STOXX":"STOXX Europe 600"};
  voile.innerHTML=`<form class="form" id="fNouv">
    <h3>Nouveau portefeuille</h3>
    <div class="d">Construit par la méthode au prochain passage du programme : les N premiers rangs de la liste de
      suivi de l'univers choisi, verdict DCF A ou B, sans veto, équipondérés. Décoche les contraintes pour
      l'ouvrir au-delà de l'univers du fonds.</div>
    <div class="grille">
      <label class="c" style="grid-column:1/-1">Nom<input type="text" id="nNom" required placeholder="Monde Novy-Marx 30"></label>
      <label class="c">Nombre de lignes<input type="number" id="nN" min="5" max="60" value="25"></label>
      <label class="c">Capital (€)<input type="number" id="nCap" min="1000" step="1000" value="100000"></label>
      <label class="c" style="grid-column:1/-1">Indice de comparaison<select id="nInd">${Object.entries(ind).map(([k,v])=>
        `<option value="${esc(k)}">${esc(v)}</option>`).join("")}</select></label>
      <div class="cases">
        <label><input type="checkbox" id="nEu" checked> Contrainte Europe — région Europe uniquement</label>
        <label><input type="checkbox" id="nSt" checked> Contrainte StockTrak — titres vérifiés dans StockTrak</label>
      </div>
    </div>
    <div class="actions"><button type="button" class="btn" id="nAnn">Annuler</button>
      <button type="submit" class="btn prim">Créer</button></div></form>`;
  voile.hidden=false;
  document.getElementById("nAnn").onclick=fermer;
  document.getElementById("fNouv").onsubmit=async ev=>{
    ev.preventDefault(); if(!exigerCle()) return;
    const nom=document.getElementById("nNom").value.trim(); if(!nom) return;
    const c=[]; if(document.getElementById("nEu").checked) c.push("europe");
    if(document.getElementById("nSt").checked) c.push("stocktrak");
    const def={id:slug(nom),nom,contraintes:c,nb_lignes:+document.getElementById("nN").value||25,
      capital:+document.getElementById("nCap").value||100000,indice:document.getElementById("nInd").value,
      date_creation:new Date().toISOString().slice(0,10)};
    try{
      await ecrireDefinitions(l=>{ if(l.some(x=>x.id===def.id)) def.id+="-"+Date.now().toString(36).slice(-4);
        return [...l,def]; }, "portefeuille "+def.id+" cree");
      fermer(); toast(`« ${nom} » créé. Le programme le construit d'ici quelques minutes.`,"ok");
    }catch(e){toast("Création impossible : "+e.message,"ko")}
  };
}
async function archiver(p){
  if(!exigerCle()) return;
  if(!confirm(`Archiver « ${p.nom} » ? Il disparaît des onglets ; ses fichiers restent dans le dépôt.`)) return;
  try{
    await ecrireDefinitions(l=>l.map(x=>x.id===p.id?{...x,archive:true}:x),"portefeuille "+p.id+" archive");
    toast("Archivé. Il disparaîtra au prochain passage du programme.","ok");
  }catch(e){toast("Impossible : "+e.message,"ko")}
}

/* ============================================================ FICHE ===== */
function liensFiche(racine){
  racine.querySelectorAll("[data-f]").forEach(el=>el.addEventListener("click",ev=>{
    ev.stopPropagation(); fiche(el.dataset.f, el.dataset.u||"europe-stocktrak");
  }));
}
window.ficheTitre=(t,u)=>fiche(t,u||"europe-stocktrak");

function jauge(lib,v,plancher){
  return `<div class="jauge"><div class="t"><span>${lib}</span><b>${E(v,0)}</b></div>
    <div class="r"><i style="width:${Math.max(0,Math.min(1,v||0))*100}%"></i>
    ${plancher!=null?`<span class="pl" style="left:${plancher*100}%" data-l="plancher ${E(plancher,0)}"></span>`:""}</div></div>`;
}
function barresDcf(g1,cagr,seuil){
  const vals=[["g₁ implicite",g1,"#3d5a66"],["CAGR retenu",cagr,"#5d6e58"],["Seuil de veto",seuil,"#a2463b"]]
    .filter(x=>x[1]!=null&&isFinite(x[1]));
  if(!vals.length) return "";
  const W=330,H=24*vals.length+20,g=96,lo=Math.min(0,...vals.map(x=>x[1])),hi=Math.max(0.02,...vals.map(x=>x[1]));
  const x=v=>g+(v-lo)/(hi-lo)*(W-g-48);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%"><line x1="${x(0)}" x2="${x(0)}" y1="4" y2="${H-14}" stroke="#c9cec7"/>
    ${vals.map(([l,v,c],i)=>{const y0=8+i*24;return `<text x="0" y="${y0+11}" font-size="10.5" fill="#4a4f49">${l}</text>
      <rect x="${Math.min(x(0),x(v))}" y="${y0}" width="${Math.max(1,Math.abs(x(v)-x(0)))}" height="14" rx="2" fill="${c}"/>
      <text x="${Math.max(x(0),x(v))+5}" y="${y0+11}" font-size="10.5" fill="#1c1e1c" font-weight="700">${E(v,1)}</text>`}).join("")}</svg>`;
}
function lectureVerdict(x){
  const c=code(x.verdict);
  const m={A:["ok","Le marché n'anticipe aucune croissance au-delà de la croissance perpétuelle : le cours ne demande rien que l'entreprise n'ait déjà prouvé."],
    B:["ok","Le marché demande moins de croissance que celle que la société a réellement réalisée."],
    C:["warn","Le marché demande plus que l'historique, mais dans la marge de tolérance : titre à surveiller."],
    D:["bad","Veto quantitatif : le cours suppose nettement plus de croissance que l'entreprise n'a su en produire."],
    ABSTENTION:["warn","Abstention : la valeur dépend davantage du taux d'actualisation que de l'entreprise (dispersion > 40 % pour ±50 pb de WACC)."],
    FLUX:["warn","Flux normatif négatif : le modèle ne s'applique pas."],
    DONNEES:["warn","Données incomplètes : le DCF n'a pas pu être calculé."]};
  const k=Object.keys(m).find(z=>c.startsWith(z))||"DONNEES";
  return m[k];
}
async function fiche(t,cu){
  voile.hidden=false; voile.innerHTML='<div class="feuille"><div class="page">Chargement…</div></div>';
  const [u,umonde,etats]=await Promise.all([charger(`classements/${cu}.json`),
    cu==="monde"?null:charger("classements/monde.json"),charger("etats.json")]);
  const x=(u?.lignes||[]).find(l=>l.Ticker===t)||(umonde?.lignes||[]).find(l=>l.Ticker===t);
  if(!x){voile.innerHTML=`<div class="form"><h3>Fiche indisponible</h3><div class="d">${esc(t)} n'est pas dans les
    classements publiés.</div><div class="actions"><button class="btn" id="fx">Fermer</button></div></div>`;
    document.getElementById("fx").onclick=fermer;return}
  const xm=(umonde?.lignes||[]).find(l=>l.Ticker===t);
  const nomU=cu==="monde"?"univers mondial":cu==="europe-stocktrak"?"univers du fonds (Europe · StockTrak)":"univers "+cu;
  const [ton,lect]=lectureVerdict(x);
  const ex=(etats&&etats[t])||[];
  const dev=ex.length?ex[ex.length-1].devise_etats:"";
  const hist=ex.slice().reverse().map(e=>{
    const gp=e.ca!=null&&e.cogs!=null?e.ca-e.cogs:null;
    const fcff=e.ebit!=null?e.ebit*(1-(e.taux_impot||0))+(e.da||0)-Math.abs(e.capex||0)-(e.dbfr||0):null;
    return `<tr><td>${esc(e.cloture)}</td><td>${N(e.ca)}</td><td>${gp!=null&&e.ca?E(gp/e.ca,1):"—"}</td>
      <td>${N(e.ebit)}</td><td>${e.ebit!=null&&e.ca?E(e.ebit/e.ca,1):"—"}</td><td>${N(e.actif)}</td>
      <td>${gp!=null&&e.actif?E(gp/e.actif,1):"—"}</td><td>${N(e.fonds_propres)}</td>
      <td>${e.dette!=null?N(e.dette-(e.tresorerie||0)):"—"}</td><td>${N(fcff)}</td></tr>`}).join("");
  const aujourd=new Date().toLocaleDateString("fr-FR",{day:"numeric",month:"long",year:"numeric"});
  const nb=u?.nb_classes;
  voile.innerHTML=`<div class="feuille">
    <div class="barre-outils"><button class="btn" id="fFerm">Fermer</button>
      <button class="btn prim" id="fPdf">Exporter en PDF</button></div>
    <div class="page">
    <div class="f-tete"><div><div class="f-marque">POLARIS · FICHE D'ANALYSE</div>
        <h2>${esc(x.Societe)}</h2>
        <div class="id">${esc(x.Ticker)} · ${esc(x.Secteur||"")} · ${esc(x.Pays||"")} · ${esc(x.Indice||x.Region||"")}</div></div>
      <div class="px"><div class="c">${N(x.cours,2)} ${esc(x.devise||"")}</div>
        <div class="s">capitalisation ${md(x.capitalisation)} Md€</div><div class="s">${esc(aujourd)}</div></div></div>

    <div class="f-synthese">
      <div><div class="k">Rang</div><div class="v">${x.rang!=null?N(x.rang):"—"}${nb?`<small style="font-size:11px;color:#7c837a"> / ${nb}</small>`:""}</div>
        <div class="s">${esc(nomU)}</div></div>
      <div><div class="k">Score combiné</div><div class="v">${N((x.rang_combine||0)*100,1)}</div>
        <div class="s">50 % rentabilité · 50 % valorisation</div></div>
      <div><div class="k">Verdict DCF</div><div class="v">${esc(code(x.verdict)||"—")}</div>
        <div class="s">marge ${S(x.marge,1)} contre le seuil</div></div>
      <div><div class="k">Liste de suivi</div><div class="v">${x.liste_suivi?"Oui":"Non"}</div>
        <div class="s">${x.veto_qualitatif?"veto qualitatif actif":x.plancher_ok?"planchers franchis":"sous un plancher"}</div></div>
    </div>
    <div class="f-verdict ${ton}"><b>${esc(x.verdict||"Pas de verdict")}.</b> ${esc(lect)}
      ${xm&&cu!=="monde"&&xm.rang!=null?` Dans l'univers mondial, le titre est ${N(xm.rang)}<sup>e</sup> sur ${umonde.nb_classes}.`:""}
      ${x.bm_implausible?" <b>Attention :</b> book-to-market hors plage plausible, donnée à vérifier avant toute décision.":""}</div>

    <div class="f-deux">
    <div class="f-section"><h3>1 · Classement Novy-Marx (2013)</h3>
      <table><tbody>
        <tr><td>Rentabilité brute / actif (GP/A)</td><td>${E(x["GP/A"],1)}</td></tr>
        <tr><td>Médiane du secteur</td><td>${E(x.mediane_secteur,1)}</td></tr>
        <tr class="fort"><td>GP/A ajusté du secteur</td><td class="${cls(x["GP/A ajuste"])}">${S(x["GP/A ajuste"],1)}</td></tr>
        <tr><td>Book-to-market</td><td>${N(x["B/M"],3)}</td></tr>
        <tr><td>Capitalisation</td><td>${md(x.capitalisation)} Md€</td></tr>
      </tbody></table>
      ${jauge("Percentile de rentabilité",x.rang_rentabilite,0.40)}
      ${jauge("Percentile de valorisation",x.rang_valorisation,0.30)}
      ${jauge("Score combiné",x.rang_combine,null)}
      <p class="f-texte">La rentabilité brute est rapportée à l'actif puis comparée à la médiane du secteur GICS, parce
        que l'intensité capitalistique varie d'un secteur à l'autre. Les deux jambes sont négativement corrélées : leur
        combinaison est moins volatile que chacune. Planchers : 40<sup>e</sup> percentile de rentabilité,
        30<sup>e</sup> de valorisation.</p></div>

    <div class="f-section"><h3>2 · DCF inversé</h3>
      <table><tbody>
        <tr><td>FCFF normatif (moyenne 3 ans)</td><td>${N(x.fcff)} M€</td></tr>
        <tr><td>WACC sectoriel${x.devise&&!["EUR","GBP","SEK","DKK","CHF","NOK","PLN"].includes(x.devise)?" (ajusté devise)":""}</td><td>${E(x.wacc,2)}</td></tr>
        <tr><td>Valeur d'entreprise de marché</td><td>${md(x.ve_marche)} Md€</td></tr>
        <tr><td>Dette nette</td><td>${N(x.dette_nette)} M€</td></tr>
        <tr class="fort"><td>Croissance implicite g₁ (5 ans)</td><td>${E(x.g1,2)}</td></tr>
        <tr><td>CAGR du CA retenu</td><td>${E(x.cagr_retenu,2)}</td></tr>
        <tr><td colspan="2" style="color:#7c837a;font-size:10.5px;text-align:left">${esc(x.origine_cagr||"")}</td></tr>
        <tr><td>Seuil de veto</td><td>${E(x.seuil,2)}</td></tr>
        <tr class="fort"><td>Marge (g₁ − seuil)</td><td class="${x.marge>0?"neg":"pos"}">${S(x.marge,2)}</td></tr>
        <tr><td>Dispersion pour ±50 pb de WACC</td><td>${E(x.dispersion,1)}</td></tr>
      </tbody></table>
      ${barresDcf(x.g1,x.cagr_retenu,x.seuil)}
      <p class="f-texte">On ne cherche pas la valeur de l'action : on résout la croissance du flux que le cours suppose,
        et on la compare à celle que la société a réellement réalisée. Seuil = CAGR + max(50 % × |CAGR| ; 1,5 pt),
        jamais sous la croissance perpétuelle de 2 %.</p></div>
    </div>

    <div class="f-section"><h3>3 · Comptes publiés ${dev?`<span style="color:#7c837a;letter-spacing:0;text-transform:none;font-weight:500">(millions de ${esc(dev)})</span>`:""}</h3>
      ${hist?`<table><thead><tr><th>Exercice</th><th>Chiffre d'affaires</th><th>Marge brute</th><th>EBIT</th><th>Marge EBIT</th>
        <th>Actif total</th><th>GP/A</th><th>Fonds propres</th><th>Dette nette</th><th>FCFF</th></tr></thead><tbody>${hist}</tbody></table>`
        :'<p class="f-texte">Historique non encore collecté pour ce titre (rafraîchi chaque semaine).</p>'}</div>

    <div class="f-pied"><span>Polaris · Novy-Marx (2013), « The Other Side of Value », JFE 108(1) · données Yahoo Finance</span>
      <span>Document d'analyse, pas un conseil en investissement</span></div>
    </div></div>`;
  document.getElementById("fFerm").onclick=fermer;
  document.getElementById("fPdf").onclick=()=>{
    const titre=document.title; document.title=`Polaris - ${x.Societe} - fiche`;
    document.body.classList.add("imprime"); window.print();
    setTimeout(()=>{document.body.classList.remove("imprime");document.title=titre},500);
  };
}
window.addEventListener("afterprint",()=>document.body.classList.remove("imprime"));

/* Liens vers la fiche dans la vue Polaris : la page la redessine souvent, on
   ecoute donc au niveau du conteneur. */
document.getElementById("app").addEventListener("click",ev=>{
  const s=ev.target.closest("[data-f]"); if(!s) return;
  fiche(s.dataset.f,"europe-stocktrak");
});

/* ------------------------------------------------------------ demarrage -- */
charger("portefeuilles.json").then(p=>{PFS=p;
  if(ONGLET.startsWith("pf:")&&!(p?.portefeuilles||[]).some(x=>"pf:"+x.id===ONGLET)) ONGLET="polaris";
  afficher();});
onglets(); afficher();
})();
