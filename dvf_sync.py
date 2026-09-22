from __future__ import annotations
import argparse,json,os,time,urllib.parse,urllib.request,hashlib
from purchase_market_database import add_observations
BASE_URL=os.getenv('RADAR_DVF_API_BASE','https://apidf-preprod.cerema.fr/dvf_opendata/mutations/')
BORDEAUX_METROPOLE_CODES=['33003','33004','33013','33032','33039','33056','33063','33065','33069','33075','33096','33119','33122','33162','33167','33192','33200','33249','33273','33281','33312','33318','33376','33434','33449','33519','33522','33550']
def _f(v):
    try:return float(v) if v not in (None,'') else None
    except:return None
def _ptype(r):
    s=str(r.get('libtypbien') or r.get('codtypbien') or '').lower()
    if 'appart' in s or s in {'121','2'}:return 'Appartement'
    if 'maison' in s or s in {'111','1'}:return 'Maison'
def row_to_observation(r):
    price=_f(r.get('valeurfonc')); surface=_f(r.get('sbati')); ptype=_ptype(r); dt=r.get('datemut') or r.get('date_mutation')
    if not price or not surface or price<=0 or surface<=0 or not ptype or not dt:return None
    sid=r.get('idmutinvar') or r.get('idopendata') or r.get('idmutation')
    if not sid:
        sid=hashlib.sha256('|'.join(str(r.get(k) or '') for k in ('datemut','valeurfonc','sbati','codinsee','adresse')).encode()).hexdigest()[:32]
    rooms=_f(r.get('nbpprinc') or r.get('nb_pieces_principales'))
    return {'market_kind':'TRANSACTION','source':'DVF+ Cerema','source_type':'OFFICIAL_TRANSACTION','source_listing_id':str(sid),'observed_date':str(dt)[:10],'city':r.get('libcom') or r.get('nom_commune'),'city_code':r.get('codinsee') or r.get('l_codinsee'),'postal_code':r.get('codpost'),'address':r.get('adresse'),'property_type':ptype,'rooms':int(rooms) if rooms is not None else None,'surface':surface,'price':price,'status':'HISTORICAL','evidence_quality':'OFFICIAL_OBSERVED','sale_channel':'DVF','price_nature':'REALIZED_PRICE','source_access':'OPEN_DATA','notes':'DVF+ officiel. Surface bâtie; Carrez/état non inférés.'}
def _get_json(url,retries=4):
    err=None
    for n in range(retries):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'RADAR-IMMO/2.4 open-data sync'})
            with urllib.request.urlopen(req,timeout=60) as resp:return json.load(resp)
        except Exception as e:err=e; time.sleep(min(2**n,8))
    raise err
def fetch_commune(code_insee,anneemut_min='2021',anneemut_max=None,page_size=500,sleep_s=.08):
    page=1; imported=rejected=fetched=0
    while True:
        params={'code_insee':code_insee,'anneemut_min':anneemut_min,'page_size':page_size,'page':page,'fields':'all'}
        if anneemut_max:params['anneemut_max']=anneemut_max
        payload=_get_json(BASE_URL+'?'+urllib.parse.urlencode(params)); rows=payload.get('results',payload if isinstance(payload,list) else [])
        fetched+=len(rows); obs=[]
        for r in rows:
            o=row_to_observation(r)
            if o:obs.append(o)
            else:rejected+=1
        imported+=add_observations(obs)['accepted']
        if not rows or not (payload.get('next') if isinstance(payload,dict) else False):break
        page+=1; time.sleep(sleep_s)
    return {'code_insee':code_insee,'fetched':fetched,'imported':imported,'rejected_unusable':rejected,'pages':page}
def sync_codes(codes,anneemut_min='2021',anneemut_max=None):
    out=[]
    for code in codes:
        try:out.append(fetch_commune(str(code),anneemut_min,anneemut_max))
        except Exception as e:out.append({'code_insee':str(code),'error':str(e),'fetched':0,'imported':0})
    return {'communes':out,'fetched':sum(x.get('fetched',0) for x in out),'imported':sum(x.get('imported',0) for x in out),'errors':[x for x in out if x.get('error')]}
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--scope',choices=['bordeaux','metropole'],default='metropole'); ap.add_argument('--from-year',default='2021'); ap.add_argument('--to-year'); a=ap.parse_args()
    print(json.dumps(sync_codes(['33063'] if a.scope=='bordeaux' else BORDEAUX_METROPOLE_CODES,a.from_year,a.to_year),ensure_ascii=False,indent=2))
