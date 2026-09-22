from __future__ import annotations
import csv,io,re,hashlib
from purchase_market_database import add_observations
UNKNOWN={'','na','n/a','null','none','inconnu','unknown'}
def _pick(row,*names):
    low={str(k).strip().lower():v for k,v in row.items()}
    for n in names:
        v=low.get(n.lower())
        if v is not None and str(v).strip().lower() not in UNKNOWN:return v
def _num(v):
    if v is None:return None
    s=re.sub(r'[^0-9.\-]','',str(v).strip().replace('\u202f','').replace(' ','').replace(',','.'))
    try:return float(s)
    except:return None
def _stable_id(row):
    raw='|'.join(str(_pick(row,k) or '') for k in ('idmutinvar','idopendata','idmutation','datemut','valeurfonc','sbati','codinsee','adresse'))
    return hashlib.sha256(raw.encode()).hexdigest()[:32] if raw.strip('|') else None
def import_dvfplus_csv(csv_text,city_filter=None):
    observations=[]; skipped=[]
    for i,row in enumerate(csv.DictReader(io.StringIO(csv_text)),start=2):
        city=_pick(row,'l_codinsee','nom_commune','commune','libcom','city')
        if city_filter and city and city_filter.lower() not in str(city).lower():continue
        price=_num(_pick(row,'valeurfonc','valeur_fonciere','valeur fonciere','valeur_fonciere_mutation','price')); surface=_num(_pick(row,'sbati','surface_reelle_bati','surface_bati','surface'))
        if not price or not surface or price<=0 or surface<=0: skipped.append({'line':i,'reason':'missing explicit transaction price or built surface'}); continue
        nature=str(_pick(row,'codtypbien','libtypbien','type_local','property_type') or '').lower()
        ptype='Appartement' if ('appart' in nature or nature in {'2','121'}) else ('Maison' if ('maison' in nature or nature in {'1','111'}) else None)
        if not ptype: skipped.append({'line':i,'reason':'property type not safely classifiable'}); continue
        dt=_pick(row,'datemut','date_mutation','observed_date')
        if not dt: skipped.append({'line':i,'reason':'missing explicit mutation date'}); continue
        rooms=_num(_pick(row,'nbpprinc','nb_pieces_principales','nombre pieces principales','rooms'))
        sid=_pick(row,'idmutinvar','idopendata','idmutation','id_mutation') or _stable_id(row)
        observations.append({'market_kind':'TRANSACTION','source':'DVF+ Cerema','source_type':'OFFICIAL_TRANSACTION','source_listing_id':str(sid) if sid else None,'observed_date':str(dt)[:10],'city':str(city) if city else None,'city_code':_pick(row,'codinsee','code_insee'),'postal_code':_pick(row,'codpost','code_postal'),'address':_pick(row,'adresse'),'property_type':ptype,'rooms':int(rooms) if rooms is not None else None,'surface':surface,'price':price,'status':'HISTORICAL','evidence_quality':'OFFICIAL_OBSERVED','sale_channel':'DVF','price_nature':'REALIZED_PRICE','source_access':'OPEN_DATA','notes':'DVF+ transaction; surface bâtie != Carrez; état non inféré.'})
    return {'parsed':len(observations),'skipped':skipped[:100],**add_observations(observations)}
def import_asking_csv(csv_text,source_name,source_type='AGENCY_OR_SPECIAL_SALE'):
    obs=[]; skipped=[]
    for i,row in enumerate(csv.DictReader(io.StringIO(csv_text)),start=2):
        price=_num(_pick(row,'price','prix','asking_price','prix_fai')); surface=_num(_pick(row,'surface','surface_m2','surface_habitable')); ptype=_pick(row,'property_type','type_bien','type'); dt=_pick(row,'observed_date','date')
        if not price or not surface: skipped.append({'line':i,'reason':'missing explicit price or surface'}); continue
        if not ptype: skipped.append({'line':i,'reason':'missing property type'}); continue
        if not dt: skipped.append({'line':i,'reason':'missing explicit observation date'}); continue
        obs.append({'market_kind':'ASKING','source':source_name,'source_type':source_type,'source_listing_id':_pick(row,'source_listing_id','reference','ref','id'),'url':_pick(row,'url','link'),'observed_date':str(dt)[:10],'city':_pick(row,'city','ville'),'postal_code':_pick(row,'postal_code','code_postal'),'neighborhood':_pick(row,'neighborhood','quartier'),'address':_pick(row,'address','adresse'),'property_type':ptype,'rooms':int(_num(_pick(row,'rooms','pieces')) or 0) or None,'surface':surface,'price':price,'state':_pick(row,'state','etat_travaux'),'dpe':_pick(row,'dpe'),'status':'ACTIVE','evidence_quality':'OBSERVED','notes':_pick(row,'notes')})
    return {'parsed':len(obs),'skipped':skipped[:100],**add_observations(obs)}
