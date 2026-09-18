from __future__ import annotations
import datetime as dt, math, statistics, os
from typing import Any
import httpx

TIMEOUT=18.0
UA='RADAR-IMMO/0.4 (+local research tool)'

def _get(url:str, params:dict|None=None, headers:dict|None=None)->Any:
    h={'User-Agent':UA,'Accept':'application/json'}
    if headers: h.update(headers)
    with httpx.Client(timeout=TIMEOUT,follow_redirects=True,headers=h) as c:
        r=c.get(url,params=params); r.raise_for_status(); return r.json()

def geocode(address:str)->dict:
    j=_get('https://data.geopf.fr/geocodage/search',{'q':address,'limit':1,'autocomplete':0})
    fs=j.get('features') or []
    if not fs: raise ValueError('Adresse introuvable')
    f=fs[0]; p=f.get('properties',{}); lon,lat=f['geometry']['coordinates'][:2]
    return {'label':p.get('label',address),'score':p.get('score'),'lon':lon,'lat':lat,'citycode':p.get('citycode'),'postcode':p.get('postcode'),'city':p.get('city'),'ban_id':p.get('id')}

def cadastre(lon:float,lat:float)->dict:
    # API Carto accepts a point geometry and returns intersecting cadastral parcel(s).
    geom=f'{{"type":"Point","coordinates":[{lon},{lat}]}}'
    j=_get('https://apicarto.ign.fr/api/cadastre/parcelle',{'geom':geom,'source_ign':'PCI'})
    feats=j.get('features') or []
    if not feats:return {'count':0,'parcels':[]}
    out=[]
    for f in feats[:5]:
        p=f.get('properties',{}); out.append({'id':p.get('id') or p.get('idu'),'commune':p.get('commune'),'section':p.get('section'),'numero':p.get('numero'),'contenance':p.get('contenance')})
    return {'count':len(feats),'parcels':out}

def urbanism(lon:float,lat:float)->dict:
    geom=f'{{"type":"Point","coordinates":[{lon},{lat}]}}'
    result={'zone':None,'prescriptions':[],'status':'screened'}
    # API Carto GPU routes. Failures are handled independently by enrich().
    try:
        j=_get('https://apicarto.ign.fr/api/gpu/zone-urba',{'geom':geom})
        fs=j.get('features') or []
        if fs:
            p=fs[0].get('properties',{}); result['zone']={k:p.get(k) for k in ('libelle','libelong','typezone','partition','nomfic') if p.get(k) is not None}
    except Exception as e: result['zone_error']=str(e)
    try:
        j=_get('https://apicarto.ign.fr/api/gpu/prescription-surf',{'geom':geom})
        for f in (j.get('features') or [])[:20]:
            p=f.get('properties',{}); result['prescriptions'].append({k:p.get(k) for k in ('libelle','txt','typepsc','sttr') if p.get(k) is not None})
    except Exception as e: result['prescription_error']=str(e)
    return result

def dvf_comparables(citycode:str, surface:float, lon:float|None=None, lat:float|None=None, years:int=3)->dict:
    start=str(dt.date.today().year-years)
    lo=max(8.0,surface*.65); hi=surface*1.35
    params={'code_insee':citycode,'anneemut_min':start,'sbati_min':round(lo,1),'sbati_max':round(hi,1),'page_size':500,'fields':'all','ordering':'-datemut'}
    j=_get('https://apidf-preprod.cerema.fr/dvf_opendata/mutations/',params)
    rows=j.get('results',j if isinstance(j,list) else [])
    comps=[]
    for r in rows:
        try:
            val=float(r.get('valeurfonc') or 0); s=float(r.get('sbati') or 0)
            if val<=0 or s<=0: continue
            typ=(r.get('libtypbien') or '').upper()
            # keep residential; exact type is refined later when listing metadata is available
            if typ and not any(x in typ for x in ('APPART','MAISON','LOGEMENT')): continue
            ppm=val/s
            if not (500<=ppm<=20000): continue
            comps.append({'date':r.get('datemut'),'price':round(val),'surface':round(s,1),'price_m2':round(ppm),'type':r.get('libtypbien'),'parcels':r.get('l_idpar')})
        except (TypeError,ValueError): pass
    vals=[x['price_m2'] for x in comps]
    med=statistics.median(vals) if vals else None
    # robust corridor using quartiles when possible
    q1=q3=None
    if len(vals)>=4:
        qs=statistics.quantiles(vals,n=4,method='inclusive'); q1,q3=qs[0],qs[2]
    return {'count':len(comps),'median_price_m2':round(med) if med else None,'q1_price_m2':round(q1) if q1 else None,'q3_price_m2':round(q3) if q3 else None,'estimated_value':round(med*surface) if med else None,'comparables':comps[:30],'source_status':'DVF+ open data / Cerema preproduction'}

def bdnb(address:str, ban_id:str|None=None, citycode:str|None=None)->dict:
    """BDNB Open: bâtiment(s) candidat(s) depuis l'adresse. Sans authentification."""
    base='https://api.bdnb.io/v1/bdnb'
    # Route officielle de géocodage BDNB. On conserve les candidats plutôt que de forcer un match.
    params={'q':address}
    j=_get(f'{base}/geocodage',params)
    rows=j if isinstance(j,list) else (j.get('results') or j.get('features') or j.get('data') or [])
    candidates=[]
    for r in rows[:10]:
        p=r.get('properties',r) if isinstance(r,dict) else {}
        candidates.append({k:p.get(k) for k in ('batiment_groupe_id','cle_interop_adr','rnb_id','adresse','libelle','score') if p.get(k) is not None})
    return {'status':'available','count':len(candidates),'candidates':candidates,'source':'BDNB Open'}

def dpe_candidates(address:str, postcode:str|None=None, surface:float|None=None)->dict:
    """ADEME DPE: candidats par adresse. Un résultat n'est jamais assimilé automatiquement au lot."""
    # Data Fair API du jeu DPE logements existants. Le portail peut faire évoluer l'identifiant;
    # les erreurs restent visibles dans enrich() au lieu d'inventer une donnée.
    url='https://data.ademe.fr/data-fair/api/v1/datasets/dpe-v2-logements-existants/lines'
    params={'size':20,'q':address}
    j=_get(url,params)
    rows=j.get('results') or []
    out=[]
    for r in rows:
        # Les libellés peuvent évoluer; conserver un sous-ensemble utile + brut minimal.
        surf=r.get('Surface_habitable_logement') or r.get('surface_habitable_logement')
        try: surf=float(surf) if surf not in (None,'') else None
        except: surf=None
        delta=None
        if surf and surface: delta=abs(surf-surface)/surface
        out.append({
            'numero_dpe':r.get('N°DPE') or r.get('numero_dpe'),
            'adresse':r.get('Adresse_(BAN)') or r.get('adresse_ban') or r.get('Adresse_brute'),
            'postcode':r.get('Code_postal_(BAN)') or r.get('code_postal_ban'),
            'surface':surf,
            'etiquette_dpe':r.get('Etiquette_DPE') or r.get('etiquette_dpe'),
            'etiquette_ges':r.get('Etiquette_GES') or r.get('etiquette_ges'),
            'date_etablissement':r.get("Date_établissement_DPE") or r.get('date_etablissement_dpe'),
            'surface_delta_pct':round(delta*100,1) if delta is not None else None
        })
    # confiance seulement indicative; identité de lot à confirmer.
    ranked=sorted(out,key=lambda x:(x['surface_delta_pct'] is None,x['surface_delta_pct'] or 999))
    return {'status':'available','count':len(ranked),'candidates':ranked[:10],'identity_warning':'DPE candidat ≠ DPE du lot tant que l’identité n’est pas confirmée','source':'ADEME DPE logements existants'}

def georisques(lon:float,lat:float, token:str|None=None)->dict:
    """Géorisques V2: token transmis dans le header. Routes configurables pour suivre la doc officielle."""
    if not token:
        return {'status':'token_missing','message':'Définir GEORISQUES_API_TOKEN dans .env ou l’environnement local.'}
    headers={'Authorization':f'Bearer {token}'}
    # L'API V2 comporte des endpoints thématiques. On tente le rapport/risques configuré,
    # sans masquer un éventuel changement de route côté fournisseur.
    endpoints=[
        os.getenv('GEORISQUES_V2_ENDPOINT','https://www.georisques.gouv.fr/api/v2/risques'),
    ]
    errors=[]
    for url in endpoints:
        try:
            j=_get(url,{'lat':lat,'lon':lon,'rayon':100},headers)
            return {'status':'available','api_version':'v2','raw':j}
        except Exception as e: errors.append(str(e))
    return {'status':'error','api_version':'v2','errors':errors,'message':'Token présent mais endpoint V2 à valider/adapter avec la documentation Géorisques courante.'}

def enrich(address:str,surface:float, georisques_token:str|None=None)->dict:
    g=geocode(address); out={'geocoding':g,'sources':{},'warnings':[]}
    jobs=[('cadastre',lambda:cadastre(g['lon'],g['lat'])),('urbanism',lambda:urbanism(g['lon'],g['lat'])),('bdnb',lambda:bdnb(g['label'],g.get('ban_id'),g.get('citycode'))),('dpe',lambda:dpe_candidates(g['label'],g.get('postcode'),surface))]
    if g.get('citycode'): jobs.append(('dvf',lambda:dvf_comparables(g['citycode'],surface,g['lon'],g['lat'])))
    jobs.append(('georisques',lambda:georisques(g['lon'],g['lat'],georisques_token)))
    for name,fn in jobs:
        try: out['sources'][name]=fn()
        except Exception as e:
            out['sources'][name]={'status':'error','error':str(e)}; out['warnings'].append(f'{name}: indisponible')
    out['generated_at']=dt.datetime.now().isoformat(timespec='seconds')
    return out
