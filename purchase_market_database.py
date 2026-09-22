from __future__ import annotations
import os, sqlite3, statistics, math
from pathlib import Path
from datetime import date, timedelta
DB=Path(os.getenv('RADAR_DB_PATH', str(Path(__file__).resolve().parent/'radar.db')))
def con():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_purchase_db():
    c=con(); c.executescript("""CREATE TABLE IF NOT EXISTS purchase_observations(
      id INTEGER PRIMARY KEY, market_kind TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT,
      source_listing_id TEXT, url TEXT, observed_date TEXT NOT NULL, city TEXT, postal_code TEXT,
      neighborhood TEXT, address TEXT, city_code TEXT, property_type TEXT, rooms INTEGER, surface REAL,
      price REAL NOT NULL, price_m2 REAL NOT NULL, state TEXT, dpe TEXT, status TEXT DEFAULT 'ACTIVE',
      evidence_quality TEXT DEFAULT 'OBSERVED', sale_channel TEXT, price_nature TEXT, source_access TEXT,
      last_verified_at TEXT, notes TEXT, UNIQUE(source, source_listing_id));
      CREATE INDEX IF NOT EXISTS idx_purchase_market ON purchase_observations(city,neighborhood,property_type,rooms,observed_date);""")
    c.commit(); c.close()
init_purchase_db()
def add_observations(rows):
    c=con(); accepted=0; rejected=[]
    for i,x in enumerate(rows or []):
        try:
            kind=str(x.get('market_kind') or 'ASKING').upper()
            if kind not in {'ASKING','TRANSACTION'}: raise ValueError('market_kind must be ASKING or TRANSACTION')
            price=float(x['price']); surface=float(x['surface'])
            if price<=0 or surface<=0: raise ValueError('price/surface must be >0')
            if not x.get('observed_date'): raise ValueError('observed_date required; date is never invented')
            before=c.total_changes
            c.execute("""INSERT OR IGNORE INTO purchase_observations(market_kind,source,source_type,source_listing_id,url,observed_date,city,postal_code,neighborhood,address,city_code,property_type,rooms,surface,price,price_m2,state,dpe,status,evidence_quality,sale_channel,price_nature,source_access,last_verified_at,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(kind,x.get('source') or 'UNKNOWN',x.get('source_type'),x.get('source_listing_id'),x.get('url'),str(x['observed_date'])[:10],x.get('city'),x.get('postal_code'),x.get('neighborhood'),x.get('address'),x.get('city_code'),x.get('property_type'),x.get('rooms'),surface,price,price/surface,x.get('state'),x.get('dpe'),x.get('status') or 'ACTIVE',x.get('evidence_quality') or 'OBSERVED',x.get('sale_channel'),x.get('price_nature'),x.get('source_access'),x.get('last_verified_at'),x.get('notes')))
            accepted += int(c.total_changes>before)
        except Exception as e: rejected.append({'index':i,'reason':str(e)})
    c.commit(); c.close(); return {'accepted':accepted,'rejected':rejected}
def _pct(a,p):
    a=sorted(a); pos=(len(a)-1)*p; lo=math.floor(pos); hi=math.ceil(pos)
    return a[lo] if lo==hi else a[lo]*(hi-pos)+a[hi]*(pos-lo)
def market_band(*,city='Bordeaux',neighborhood=None,property_type=None,rooms=None,surface=None,market_kind='ASKING',max_age_days=540):
    c=con(); cutoff=(date.today()-timedelta(days=max_age_days)).isoformat()
    q='SELECT * FROM purchase_observations WHERE market_kind=? AND lower(city)=lower(?) AND observed_date>=?'
    if market_kind.upper()=='ASKING': q+=' AND status="ACTIVE"'
    rows=[dict(r) for r in c.execute(q,[market_kind.upper(),city,cutoff]).fetchall()]; c.close()
    def filt(n,rm,sf):
        return [r for r in rows if (not property_type or str(r.get('property_type') or '').lower()==property_type.lower()) and (not n or not neighborhood or str(r.get('neighborhood') or '').lower()==neighborhood.lower()) and (not rm or not rooms or r.get('rooms')==rooms) and (not sf or not surface or abs(float(r['surface'])-surface)/surface<=.30)]
    levels=[('MICRO_EXACT',(1,1,1)),('MICRO_WIDE_SURFACE',(1,1,0)),('CITY_EXACT',(0,1,1)),('CITY_TYPE',(0,0,0))]
    match='CITY_TYPE'; cand=[]
    for match,flags in levels:
        cand=filt(*flags)
        if len(cand)>=5: break
    if not cand:return {'status':'INSUFFICIENT','market_kind':market_kind.upper(),'match_level':match,'count':0,'confidence':'LOW','warning':'Aucune observation exploitable; aucune valeur inventée.'}
    vals=[float(r['price_m2']) for r in cand]; sources=len({r['source'] for r in cand}); q25,med,q75=_pct(vals,.25),statistics.median(vals),_pct(vals,.75)
    conf='HIGH' if len(vals)>=20 and sources>=5 and match.startswith('MICRO') else ('MEDIUM' if len(vals)>=8 and sources>=3 else 'LOW')
    return {'status':'VALUED','market_kind':market_kind.upper(),'match_level':match,'count':len(vals),'source_count':sources,'confidence':conf,'price_m2_q25':round(q25),'price_m2_median':round(med),'price_m2_q75':round(q75),'value_q25':round(q25*surface) if surface else None,'value_median':round(med*surface) if surface else None,'value_q75':round(q75*surface) if surface else None}
