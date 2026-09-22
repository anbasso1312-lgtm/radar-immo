from __future__ import annotations
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from pathlib import Path
import sqlite3, json, datetime, math, os
from connectors import enrich
from financial_engine import monthly_payment as _monthly_payment, quick_metrics, price_curve
from version import APP_VERSION
from acquisition_cost_engine import estimate_acquisition_costs
from resale_engine import analyze_resale
from property_condition_engine import classify_condition
from opportunity_analysis_engine import analyze_opportunity
from purchase_market_database import add_observations as add_purchase_observations, market_band as purchase_market_band
from purchase_data_pipeline import import_dvfplus_csv, import_asking_csv
from data_status import purchase_data_status
from purchase_seed_loader import load_verified_seed
from works_cost_engine import estimate_scope
from transformation_engine import compare_states
from land_potential_engine import screen_land

app = FastAPI(title='RADAR IMMO', version=APP_VERSION)
DB=Path(__file__).resolve().parent/'radar.db'

def con():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=con(); c.executescript('''
    CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,name TEXT UNIQUE,url TEXT,category TEXT,access_mode TEXT,zone TEXT,status TEXT,frequency TEXT,notes TEXT,last_scan TEXT);
    CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY,origin TEXT,source_id INTEGER,title TEXT,address TEXT,price REAL,surface REAL,rooms INTEGER,rent REAL,works REAL,current_value REAL,renovated_value REAL,status TEXT,confidence TEXT,why TEXT,created_at TEXT,updated_at TEXT);
    ''')
    seeds=[
      ('DVF / Etalab','https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres/','transactions','open_data','France','ACTIVE','monthly','Transactions réalisées; base de comparables.'),
      ('Géoportail de l’Urbanisme','https://www.geoportail-urbanisme.gouv.fr/','urbanisme','open_data','France','ACTIVE','weekly','PLU, servitudes et documents d’urbanisme.'),
      ('Géorisques','https://www.georisques.gouv.fr/','risques','open_data','France','ACTIVE','monthly','Risques physiques et environnementaux.'),
      ('ADEME DPE','https://data.ademe.fr/','energie','open_data','France','ACTIVE','monthly','DPE et données énergétiques.'),
      ('INSEE','https://www.insee.fr/','socio_market','open_data','France','ACTIVE','quarterly','Données statistiques territoriales.'),
      ('Cadastre','https://cadastre.data.gouv.fr/','parcelles','open_data','France','ACTIVE','monthly','Parcelles et géométrie cadastrale.'),
      ('Off-market Pierre','', 'off_market','manual','Bordeaux','ACTIVE','continuous','Agents, notaires, réseau, propriétaires, apporteurs.')]
    for s in seeds: c.execute('INSERT OR IGNORE INTO sources(name,url,category,access_mode,zone,status,frequency,notes) VALUES(?,?,?,?,?,?,?,?)',s)
    c.commit(); c.close()
init_db()

class DealInput(BaseModel):
    address:str='Bordeaux'; price:float=Field(gt=0); surface:float=Field(gt=0); rooms:int=Field(2,ge=1); monthly_rent:float=Field(0,ge=0); works:float=Field(0,ge=0); acquisition_cost_rate:float=Field(.08,ge=0,le=.2); down_payment:float=Field(0,ge=0); annual_rate:float=Field(.035,ge=0,le=.2); loan_years:int=Field(25,ge=1,le=35); insurance_rate:float=Field(.003,ge=0,le=.05); property_tax:float=Field(0,ge=0); annual_nonrecoverable_charges:float=Field(0,ge=0); annual_maintenance_rate:float=Field(.01,ge=0,le=.1); vacancy_rate:float=Field(.05,ge=0,le=.5); management_rate:float=Field(0,ge=0,le=.3); current_value:Optional[float]=None; renovated_value:Optional[float]=None; target_margin:float=0; exit_cost_rate:float=.05; reserve_months:int=6; strategy:Literal['hold','renovate','transform','resell']='hold'
class SourceIn(BaseModel):
    name:str; url:str=''; category:str='listing'; access_mode:str='to_verify'; zone:str='Bordeaux'; status:str='DISCOVERED'; frequency:str='daily'; notes:str=''
class OpportunityIn(BaseModel):
    title:str='Off-market'; address:str='Bordeaux'; price:float=Field(gt=0); surface:float=Field(gt=0); rooms:int=2; rent:float=0; works:float=0; current_value:Optional[float]=None; renovated_value:Optional[float]=None; origin:str='OFF_MARKET'; source_id:Optional[int]=None

def monthly_payment(p,r,y):
    return _monthly_payment(p,r,y)
def clamp(x): return max(0,min(100,x))
def analyze(d:DealInput):
    acq=d.price*d.acquisition_cost_rate; total=d.price+acq+d.works; debt=max(0,total-d.down_payment); pay=monthly_payment(debt,d.annual_rate,d.loan_years); ins=debt*d.insurance_rate/12
    er=d.monthly_rent*(1-d.vacancy_rate); mg=er*d.management_rate; maint=d.price*d.annual_maintenance_rate/12; fixed=d.property_tax/12+d.annual_nonrecoverable_charges/12; cf=er-mg-maint-fixed-pay-ins; noi=(er-mg-maint-fixed)*12; dscr=noi/((pay+ins)*12) if pay+ins else None
    now=d.current_value or d.price; after=d.renovated_value or now; gap=max(0,now-d.price); trans=max(0,after-now-d.works); maxp=(after*(1-d.exit_cost_rate)-d.works-d.target_margin)/(1+d.acquisition_cost_rate); stress=d.monthly_rent*.9*(1-min(.2,d.vacancy_rate+.05))*(1-d.management_rate)-maint*1.25-fixed*1.1-pay-ins
    blockers=[]
    if not d.current_value:blockers.append('Valeur de marché inconnue : comparables requis')
    if d.works and not d.renovated_value:blockers.append('Valeur après travaux non validée')
    if dscr is not None and dscr<1:blockers.append('DSCR < 1')
    if stress<0:blockers.append('Cash-flow stressé négatif')
    why=[]
    if gap>0: why.append(f'Prix sous valeur renseignée de {gap:,.0f} €')
    if trans>0: why.append(f'Valeur potentielle nette de travaux {trans:,.0f} €')
    if d.works/d.price>.10: why.append('Transformation significative à expertiser')
    return {'identity':{'address':d.address,'surface':d.surface,'rooms':d.rooms},'project':{'price':round(d.price),'total_project':round(total),'debt':round(debt)},'market':{'current_value':round(now),'renovated_value':round(after),'perception_gap':round(gap),'transformation_value':round(trans),'max_purchase_price':round(maxp),'price_gap_to_max':round(d.price-maxp)},'operations':{'gross_yield_pct':round(d.monthly_rent*12/d.price*100,2),'monthly_payment':round(pay),'monthly_cashflow':round(cf),'stress_cashflow':round(stress),'dscr':round(dscr,2) if dscr else None},'radar':{'market':round(clamp(50+gap/max(d.price,1)*300)),'cashflow':round(clamp(50+cf/10)),'robustness':round(clamp(60+stress/15-d.works/max(d.price,1)*80)),'confidence':'MOYENNE' if d.current_value or d.renovated_value else 'FAIBLE','blockers':blockers,'why':why or ['Aucune anomalie positive démontrée avec les données disponibles']}}


class EnrichIn(BaseModel):
    address:str
    surface:float=Field(gt=0)

class ResaleAnalysisIn(BaseModel):
    purchase_price:float=Field(gt=0); prudent_exit_value:float=Field(gt=0); works:float=Field(0,ge=0)
    resale_agency_fee:float=Field(0,ge=0); financing_cost:float=Field(0,ge=0); holding_cost:float=Field(0,ge=0)
    technical_costs:float=Field(0,ge=0); contingency:float=Field(0,ge=0); taxes_on_resale:Optional[float]=Field(None,ge=0)
    target_margin_rate:float=Field(.12,ge=0,le=.8)

class ConditionIn(BaseModel):
    observations:list[dict]=Field(default_factory=list)

class OpportunityAnalysisIn(BaseModel):
    purchase_price:float=Field(gt=0); direct_exit_value:Optional[float]=None; renovated_exit_value:Optional[float]=None
    renovation_cost:Optional[float]=Field(None,ge=0); created_m2:Optional[float]=Field(None,ge=0)
    created_m2_value:Optional[float]=Field(None,ge=0); created_m2_cost:Optional[float]=Field(None,ge=0); created_m2_validated:bool=False

class PurchaseObservationIn(BaseModel):
    observations:list[dict]=Field(default_factory=list)
class PurchaseBandIn(BaseModel):
    city:str='Bordeaux'; neighborhood:Optional[str]=None; property_type:Optional[str]=None; rooms:Optional[int]=None; surface:Optional[float]=None; market_kind:Literal['ASKING','TRANSACTION']='ASKING'
class PurchaseCsvIn(BaseModel):
    csv_text:str; city_filter:Optional[str]=None
class AskingCsvIn(BaseModel):
    csv_text:str; source_name:str; source_type:str='AGENCY_OR_SPECIAL_SALE'
class WorksScopeIn(BaseModel):
    items:list[dict]=Field(default_factory=list)
class TransformCompareIn(BaseModel):
    current:dict; target:dict; works:dict; extra_costs:float=0
class LandScreenIn(BaseModel):
    parcel_known:bool=False; urbanism_known:bool=False; access_known:bool=False; networks_known:bool=False; private_rules_known:bool=False; candidate_m2:Optional[float]=None

@app.post('/api/purchase-market/observations')
def api_purchase_observations(x:PurchaseObservationIn): return add_purchase_observations(x.observations)
@app.post('/api/purchase-market/band')
def api_purchase_band(x:PurchaseBandIn): return purchase_market_band(**x.model_dump())
@app.post('/api/purchase-market/import-dvfplus-csv')
def api_purchase_import_dvf(x:PurchaseCsvIn): return import_dvfplus_csv(x.csv_text,x.city_filter)
@app.post('/api/purchase-market/import-asking-csv')
def api_purchase_import_asking(x:AskingCsvIn): return import_asking_csv(x.csv_text,x.source_name,x.source_type)
@app.get('/api/purchase-market/status')
def api_purchase_status(): return purchase_data_status()
@app.post('/api/purchase-market/load-verified-seed')
def api_purchase_seed(): return load_verified_seed()
@app.post('/api/works/cost')
def api_works_cost(x:WorksScopeIn): return estimate_scope(x.items)
@app.post('/api/transformation/compare')
def api_transform_compare(x:TransformCompareIn): return compare_states(x.current,x.target,x.works,x.extra_costs)
@app.post('/api/land/screen')
def api_land_screen(x:LandScreenIn): return screen_land(**x.model_dump())

@app.post('/api/resale/analyze')
def api_resale_analyze(x:ResaleAnalysisIn): return analyze_resale(**x.model_dump())

@app.post('/api/evidence/condition')
def api_condition(x:ConditionIn): return classify_condition(x.observations)

@app.post('/api/opportunity/analyze')
def api_opportunity_analysis(x:OpportunityAnalysisIn): return analyze_opportunity(**x.model_dump())

@app.post('/api/enrich')
def api_enrich(x:EnrichIn):
    try:
        return enrich(x.address,x.surface,os.getenv('GEORISQUES_API_TOKEN'))
    except Exception as e:
        raise HTTPException(status_code=502,detail=f'Enrichissement externe impossible: {e}')

@app.post('/api/research')
def api_research(d:DealInput):
    """Adresse -> données publiques -> analyse financière, sans inventer les champs manquants."""
    try:
        e=enrich(d.address,d.surface,os.getenv('GEORISQUES_API_TOKEN'))
    except Exception as exc:
        raise HTTPException(status_code=502,detail=f'Recherche externe impossible: {exc}')
    dvf=e.get('sources',{}).get('dvf',{})
    if not d.current_value and dvf.get('estimated_value'):
        d=d.model_copy(update={'current_value':float(dvf['estimated_value'])})
    a=analyze(d)
    a['research']=e
    a['radar']['confidence']='MOYENNE' if dvf.get('count',0)>=5 else a['radar']['confidence']
    if dvf.get('count',0): a['radar']['why'].append(f"{dvf['count']} mutations DVF+ comparables présélectionnées; médiane {dvf.get('median_price_m2') or '?'} €/m²")
    return a

@app.post('/api/quick-radar')
def quick_radar(d:DealInput):
    rent=d.monthly_rent
    kwargs=dict(acquisition_cost_rate=d.acquisition_cost_rate,down_payment=d.down_payment,annual_rate=d.annual_rate,loan_years=d.loan_years,insurance_rate=d.insurance_rate,property_tax=d.property_tax if d.property_tax>0 else None,annual_charges=d.annual_nonrecoverable_charges if d.annual_nonrecoverable_charges>0 else None,maintenance_rate=d.annual_maintenance_rate,vacancy_rate=d.vacancy_rate,management_rate=d.management_rate)
    base=quick_metrics(price=d.price,rent=rent,works=d.works,**kwargs)
    curve=price_curve(asking_price=d.price,rent=rent,works=d.works,kwargs=kwargs)
    # Max price for cash-flow >= 0, solved by bisection with the same assumptions.
    lo,hi=max(1000.0,d.price*.25),d.price*1.25
    for _ in range(50):
        mid=(lo+hi)/2
        if quick_metrics(price=mid,rent=rent,works=d.works,**kwargs)['monthly_cashflow']>=0: lo=mid
        else: hi=mid
    max_cf0=round(lo)
    missing=[]
    if d.property_tax<=0: missing.append('Taxe foncière réelle')
    if d.annual_nonrecoverable_charges<=0: missing.append('Charges copropriété / syndic non récupérables')
    if d.monthly_rent<=0: missing.append('Loyer de marché')
    if d.works<=0: missing.append('Budget travaux si nécessaire')
    verdict='À INVESTIGUER' if rent>0 and (base['monthly_cashflow']>=0 or d.price<=max_cf0*1.08) else 'À ÉCARTER AU PRIX ACTUEL'
    return {'asking_price':round(d.price),'quick':base,'price_curve':curve,'max_price_cashflow_zero':max_cf0,'verdict':verdict,'missing':missing,'method':'QUICK_RADAR_ESTIMATES'}

@app.get('/api/health')
def health():return {'status':'ok','version':APP_VERSION}
@app.get('/api/config-status')
def config_status(): return {'georisques_token': bool(os.getenv('GEORISQUES_API_TOKEN')), 'bdnb':'open_no_auth', 'dpe':'open_data'}
@app.post('/api/analyze')
def api_analyze(d:DealInput):return analyze(d)
@app.get('/api/sources')
def sources():
    c=con(); x=[dict(r) for r in c.execute('SELECT * FROM sources ORDER BY status,name')]; c.close(); return x
@app.post('/api/sources')
def add_source(s:SourceIn):
    c=con(); cur=c.execute('INSERT INTO sources(name,url,category,access_mode,zone,status,frequency,notes) VALUES(?,?,?,?,?,?,?,?)',(s.name,s.url,s.category,s.access_mode,s.zone,s.status,s.frequency,s.notes)); c.commit(); i=cur.lastrowid;c.close();return {'id':i,'status':'created'}
@app.post('/api/opportunities')
def add_opp(o:OpportunityIn):
    d=DealInput(address=o.address,price=o.price,surface=o.surface,rooms=o.rooms,monthly_rent=o.rent,works=o.works,current_value=o.current_value,renovated_value=o.renovated_value); a=analyze(d); now=datetime.datetime.now().isoformat(timespec='seconds')
    c=con(); cur=c.execute('INSERT INTO opportunities(origin,source_id,title,address,price,surface,rooms,rent,works,current_value,renovated_value,status,confidence,why,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(o.origin,o.source_id,o.title,o.address,o.price,o.surface,o.rooms,o.rent,o.works,o.current_value,o.renovated_value,'NEW',a['radar']['confidence'],json.dumps(a['radar']['why'],ensure_ascii=False),now,now));c.commit();i=cur.lastrowid;c.close();return {'id':i,'analysis':a}
@app.get('/api/opportunities')
def opps():
    c=con(); rows=[dict(r) for r in c.execute('SELECT * FROM opportunities ORDER BY created_at DESC')];c.close()
    for r in rows:
        try:r['why']=json.loads(r['why'])
        except:r['why']=[]
    return rows
@app.post('/api/scan')
def scan():
    c=con(); now=datetime.datetime.now().isoformat(timespec='seconds'); c.execute("UPDATE sources SET last_scan=? WHERE status='ACTIVE'",(now,)); n=c.execute("SELECT count(*) FROM sources WHERE status='ACTIVE'").fetchone()[0]; c.commit();c.close()
    return {'checked_sources':n,'new_opportunities':0,'time':now,'message':'Connecteurs réseau non activés dans cette V0.2 : le registre et le pipeline sont prêts. Aucun résultat fictif n’est créé.'}
@app.get('/',response_class=HTMLResponse)
def home():return HTMLResponse(INDEX)

INDEX='''<!doctype html><html lang=fr><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>RADAR IMMO</title><style>*{box-sizing:border-box}body{margin:0;background:#091018;color:#edf3f7;font:14px system-ui}.w{max-width:1200px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between}.brand{font-size:24px;font-weight:900}.muted{color:#8fa0ae}.tabs{display:flex;gap:8px;margin:22px 0}.tabs button,.btn{border:1px solid #304252;background:#111c26;color:#edf3f7;border-radius:10px;padding:10px 14px;cursor:pointer}.tabs button.on,.btn.primary{background:#edf3f7;color:#091018;font-weight:800}.panel{display:none}.panel.on{display:block}.grid{display:grid;grid-template-columns:360px 1fr;gap:16px}.card{background:#101a24;border:1px solid #263746;border-radius:14px;padding:16px;margin-bottom:12px}.form{display:grid;grid-template-columns:1fr 1fr;gap:9px}.full{grid-column:1/-1}label{font-size:12px;color:#9aabb8}input,select{width:100%;padding:9px;margin-top:4px;background:#09121a;color:white;border:1px solid #304252;border-radius:8px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.kpi{background:#09121a;padding:12px;border-radius:10px}.kpi b{display:block;font-size:19px;margin-top:4px}.row{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #21313e;padding:10px 0}.pill{padding:3px 7px;border:1px solid #385064;border-radius:99px;font-size:11px}.why{border-left:3px solid #dce6ed;padding:8px 10px;background:#0a131b;margin:6px 0}@media(max-width:800px){.grid{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}.tabs{overflow:auto}}</style></head><body><div class=w><div class=top><div><div class=brand>RADAR IMMO</div><div class=muted>Recherche autonome · Off-market · Analyse</div></div><div class=muted>V0.5 · QUICK RADAR prix → rentabilité → prix cible</div></div><div class=tabs><button class=on data-p=radar>RADAR</button><button data-p=inbox>INBOX</button><button data-p=sources>SOURCES</button><button data-p=off>OFF-MARKET</button></div>
<section id=radar class="panel on"><div class=grid><div class=card><h3>Analyser</h3><form id=f class=form><label class=full>Adresse<input name=address value="Bordeaux"></label><label>Prix €<input name=price type=number value=250000></label><label>Surface m²<input name=surface type=number value=65></label><label>Pièces<input name=rooms type=number value=3></label><label>Loyer/mois<input name=monthly_rent type=number value=1250></label><label>Travaux €<input name=works type=number value=25000></label><label>Valeur actuelle<input name=current_value type=number value=265000></label><label>Valeur rénovée<input name=renovated_value type=number value=310000></label><button type=button id=quick class="btn primary full">QUICK RADAR — RENTABILITÉ</button><button class="btn full">ENRICHIR + ANALYSER</button></form></div><div id=out class=card><span class=muted>Analyse en attente.</span></div></div></section>
<section id=inbox class=panel><div class=card><div class=top><div><h3>Inbox opportunités</h3><div class=muted>Marché + off-market dans le même pipeline.</div></div><button id=scan class="btn primary">SCAN MAINTENANT</button></div><div id=scanmsg class=muted></div><div id=opps></div></div></section>
<section id=sources class=panel><div class=grid><div class=card><h3>Ajouter une source</h3><form id=sf class=form><label class=full>Nom<input name=name required></label><label class=full>URL<input name=url></label><label>Catégorie<input name=category value=listing></label><label>Accès<select name=access_mode><option>to_verify</option><option>api</option><option>open_data</option><option>manual</option><option>partner</option></select></label><label>Zone<input name=zone value=Bordeaux></label><label>Fréquence<input name=frequency value=daily></label><label class=full>Notes<input name=notes></label><button class="btn primary full">AJOUTER</button></form></div><div class=card><h3>Registre des sources</h3><div id=srcs></div></div></div></section>
<section id=off class=panel><div class=grid><div class=card><h3>Injecter un off-market</h3><form id=of class=form><label class=full>Titre<input name=title value="Opportunité réseau"></label><label class=full>Adresse<input name=address value="Bordeaux"></label><label>Prix €<input name=price type=number required></label><label>Surface m²<input name=surface type=number required></label><label>Pièces<input name=rooms type=number value=3></label><label>Loyer<input name=rent type=number value=0></label><label>Travaux<input name=works type=number value=0></label><label>Valeur actuelle<input name=current_value type=number></label><label>Valeur rénovée<input name=renovated_value type=number></label><button class="btn primary full">INJECTER + ANALYSER</button></form></div><div class=card><h3>Règle</h3><p>Une donnée manquante reste <b>UNKNOWN</b>. L’off-market rejoint exactement le même pipeline que les opportunités collectées automatiquement.</p><div class=why>Source → identité → enrichissement → RADAR rapide → anomalies → scénarios → vérifications → action Pierre.</div></div></div></section></div><script>
const $=s=>document.querySelector(s), eur=x=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(x||0);document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));b.classList.add('on');$('#'+b.dataset.p).classList.add('on'); if(b.dataset.p==='sources')loadSources();if(b.dataset.p==='inbox')loadOpps()});
$('#quick').onclick=async()=>{let form=$('#f');let o=Object.fromEntries(new FormData(form));['price','surface','rooms','monthly_rent','works','current_value','renovated_value'].forEach(k=>o[k]=o[k]?Number(o[k]):null);let r=await (await fetch('/api/quick-radar',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(o)})).json();let q=r.quick;$('#out').innerHTML=`<h2>QUICK RADAR</h2><div class=why><b>${r.verdict}</b> · analyse initiale basée sur données saisies + hypothèses identifiées</div><div class=kpis><div class=kpi><span class=muted>Prix affiché</span><b>${eur(r.asking_price)}</b></div><div class=kpi><span class=muted>CF estimé</span><b>${eur(q.monthly_cashflow)}/m</b></div><div class=kpi><span class=muted>Rendement net*</span><b>${q.net_yield_before_financing_pct}%</b></div><div class=kpi><span class=muted>Prix CF=0</span><b>${eur(r.max_price_cashflow_zero)}</b></div></div><h3>Échelle de négociation</h3>${r.price_curve.map(x=>`<div class=row><span>${x.discount_pct?'-'+x.discount_pct+'%':'Prix affiché'} · ${eur(x.price)}</span><b>CF ${eur(x.monthly_cashflow)}/m · brut ${x.gross_yield_pct}%</b></div>`).join('')}<h3>Hypothèses automatiques</h3><div class=why>Taxe foncière: ${eur(q.assumptions.property_tax.value)}/an · ${q.assumptions.property_tax.status}</div><div class=why>Charges: ${eur(q.assumptions.annual_charges.value)}/an · ${q.assumptions.annual_charges.status}</div><h3>À obtenir si le bien passe le filtre</h3>${(r.missing.length?r.missing:['Aucune donnée critique signalée']).map(x=>`<div class=why>${x}</div>`).join('')}<div class=muted>* avant financement; estimation QUICK RADAR, pas une donnée documentée.</div>`};
$('#f').onsubmit=async e=>{e.preventDefault();let o=Object.fromEntries(new FormData(e.target));['price','surface','rooms','monthly_rent','works','current_value','renovated_value'].forEach(k=>o[k]=o[k]?Number(o[k]):null);let d=await (await fetch('/api/research',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(o)})).json();$('#out').innerHTML=`<h2>${d.identity.address}</h2><div class=kpis><div class=kpi><span class=muted>Prix max</span><b>${eur(d.market.max_purchase_price)}</b></div><div class=kpi><span class=muted>CF</span><b>${eur(d.operations.monthly_cashflow)}</b></div><div class=kpi><span class=muted>Stress</span><b>${eur(d.operations.stress_cashflow)}</b></div><div class=kpi><span class=muted>Confiance</span><b>${d.radar.confidence}</b></div></div>${d.research?`<h3>Données publiques connectées</h3><div class=why>Adresse: ${d.research.geocoding.label} · score géocodage ${d.research.geocoding.score??'?'} · commune ${d.research.geocoding.citycode??'?'}</div><div class=why>DVF+: ${d.research.sources.dvf?.count??0} comparables · médiane ${d.research.sources.dvf?.median_price_m2??'?'} €/m² · valeur statistique ${eur(d.research.sources.dvf?.estimated_value)}</div><div class=why>Cadastre: ${d.research.sources.cadastre?.count??0} parcelle(s) · Urbanisme: ${d.research.sources.urbanism?.zone?.libelle||d.research.sources.urbanism?.zone?.typezone||'à vérifier'} · Géorisques: ${d.research.sources.georisques?.status||'à vérifier'}</div><div class=why>BDNB: ${d.research.sources.bdnb?.count??0} candidat(s) bâtiment · DPE ADEME: ${d.research.sources.dpe?.count??0} candidat(s) (identité du lot à confirmer)</div>`:''}<h3>WHY DID RADAR FIND THIS?</h3>${d.radar.why.map(x=>`<div class=why>${x}</div>`).join('')}<h3>Bloquants</h3>${(d.radar.blockers.length?d.radar.blockers:['Aucun blocage automatique détecté']).map(x=>`<div class=why>${x}</div>`).join('')}`};
async function loadSources(){let a=await (await fetch('/api/sources')).json();$('#srcs').innerHTML=a.map(s=>`<div class=row><div><b>${s.name}</b><div class=muted>${s.category} · ${s.zone} · ${s.access_mode}</div></div><div><span class=pill>${s.status}</span><div class=muted>${s.last_scan||'jamais scannée'}</div></div></div>`).join('')};
$('#sf').onsubmit=async e=>{e.preventDefault();await fetch('/api/sources',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});e.target.reset();loadSources()};
$('#of').onsubmit=async e=>{e.preventDefault();let o=Object.fromEntries(new FormData(e.target));['price','surface','rooms','rent','works','current_value','renovated_value'].forEach(k=>o[k]=o[k]?Number(o[k]):null);let r=await (await fetch('/api/opportunities',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(o)})).json();alert('Opportunité #'+r.id+' injectée et analysée.');};
async function loadOpps(){let a=await (await fetch('/api/opportunities')).json();$('#opps').innerHTML=a.length?a.map(o=>`<div class=row><div><b>${o.title}</b><div>${o.address} · ${o.surface} m² · ${eur(o.price)}</div><div class=muted>${(o.why||[]).join(' · ')}</div></div><div><span class=pill>${o.status}</span><div class=muted>${o.origin} · ${o.confidence}</div></div></div>`).join(''):'<p class=muted>Aucune opportunité. Injecte un off-market ou active des connecteurs.</p>'};
$('#scan').onclick=async()=>{let d=await (await fetch('/api/scan',{method:'POST'})).json();$('#scanmsg').textContent=`${d.checked_sources} sources vérifiées · ${d.new_opportunities} nouvelle · ${d.message}`;loadOpps()};
</script></body></html>'''
