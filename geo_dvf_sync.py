from __future__ import annotations
import csv,gzip,io,os,urllib.request,threading
from collections import defaultdict
from purchase_market_database import add_observations

BASE='https://files.data.gouv.fr/geo-dvf/latest/csv'
YEARS=tuple(str(y) for y in range(2021,2026))
METROPOLE={'33003','33004','33013','33032','33039','33056','33063','33065','33069','33075','33096','33119','33122','33162','33167','33192','33200','33249','33273','33281','33312','33318','33376','33434','33449','33519','33522','33550'}
STATE={'running':False,'last_report':None}

def _f(v):
    try:return float(v) if v not in (None,'') else None
    except:return None

def _download(year):
    url=f'{BASE}/{year}/departements/33.csv.gz'
    req=urllib.request.Request(url,headers={'User-Agent':'RADAR-IMMO/2.4 (+open-data DVF)'})
    with urllib.request.urlopen(req,timeout=120) as r:return gzip.decompress(r.read()).decode('utf-8-sig')

def _classify_group(rows):
    residential=[r for r in rows if r.get('type_local') in {'Maison','Appartement'} and _f(r.get('surface_reelle_bati'))]
    other_built=[r for r in rows if r.get('type_local') and r.get('type_local') not in {'Maison','Appartement'}]
    land=any((_f(r.get('surface_terrain')) or 0)>0 for r in rows)
    if len(residential)!=1:return 'MULTI_LOCAL' if len(residential)>1 else 'UNUSABLE',None
    if other_built:return 'MIXED_USE',None
    # A house with land is normal; land is only a blocker for apartment mutations.
    if land and residential[0].get('type_local')=='Appartement':return 'LAND_INCLUDED',None
    return 'SIMPLE_RESIDENTIAL',residential[0]

def sync_gironde(years=YEARS,metropole_only=True):
    report={'years':{},'fetched_rows':0,'eligible':0,'complex_excluded':0,'unusable':0,'inserted':0,'duplicates':0}
    for year in years:
        text=_download(str(year)); rows=list(csv.DictReader(io.StringIO(text)))
        if metropole_only: rows=[r for r in rows if r.get('code_commune') in METROPOLE]
        groups=defaultdict(list)
        for r in rows:
            if r.get('nature_mutation')!='Vente':continue
            groups[r.get('id_mutation') or ''].append(r)
        yr={'rows':len(rows),'mutations':len(groups),'eligible':0,'complex_excluded':0,'unusable':0,'inserted':0}
        for mid,g in groups.items():
            kind,r=_classify_group(g)
            if kind!='SIMPLE_RESIDENTIAL':
                if kind=='UNUSABLE':yr['unusable']+=1
                else:yr['complex_excluded']+=1
                continue
            price=_f(r.get('valeur_fonciere')); surface=_f(r.get('surface_reelle_bati')); dt=r.get('date_mutation')
            if not mid or not price or price<=0 or not surface or surface<=0 or not dt:
                yr['unusable']+=1; continue
            rooms=_f(r.get('nombre_pieces_principales'))
            address=' '.join(x for x in [r.get('adresse_numero'),r.get('adresse_suffixe'),r.get('adresse_nom_voie')] if x)
            o={'market_kind':'TRANSACTION','source':'DVF geolocalise data.gouv.fr','source_type':'OFFICIAL_TRANSACTION',
               'source_listing_id':f'{year}:{mid}','observed_date':dt,'city':r.get('nom_commune'),'city_code':r.get('code_commune'),
               'postal_code':r.get('code_postal'),'address':address or None,'property_type':r.get('type_local'),
               'rooms':int(rooms) if rooms is not None else None,'surface':surface,'price':price,'status':'HISTORICAL',
               'evidence_quality':'OFFICIAL_OBSERVED','sale_channel':'DVF','price_nature':'REALIZED_PRICE','source_access':'OPEN_DATA',
               'notes':'Mutation Vente simple résidentielle; mutations multi-locaux/mixte exclues; surface réelle bâtie != Carrez.'}
            res=add_observations([o]); yr['eligible']+=1; yr['inserted']+=res['accepted']
        yr['duplicates']=yr['eligible']-yr['inserted']; report['years'][str(year)]=yr
        report['fetched_rows']+=yr['rows']; report['eligible']+=yr['eligible']; report['complex_excluded']+=yr['complex_excluded']; report['unusable']+=yr['unusable']; report['inserted']+=yr['inserted']; report['duplicates']+=yr['duplicates']
    STATE['last_report']=report; return report

def _worker():
    STATE['running']=True
    try: STATE['last_report']=sync_gironde()
    except Exception as e: STATE['last_report']={'error':str(e)}
    finally: STATE['running']=False

def start_background_sync():
    if STATE['running']:return False
    threading.Thread(target=_worker,daemon=True).start(); return True

def sync_status():return STATE
