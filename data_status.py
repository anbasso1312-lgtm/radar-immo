from purchase_market_database import con
from geo_dvf_sync import METROPOLE

def purchase_data_status():
    c=con()
    total=c.execute("SELECT COUNT(*) FROM purchase_observations").fetchone()[0]
    by_kind=[dict(r) for r in c.execute("SELECT market_kind,COUNT(*) count,MIN(observed_date) first_date,MAX(observed_date) last_date,COUNT(DISTINCT source) sources FROM purchase_observations GROUP BY market_kind")]
    by_source=[dict(r) for r in c.execute("SELECT source,market_kind,COUNT(*) count,MAX(observed_date) last_date FROM purchase_observations GROUP BY source,market_kind ORDER BY count DESC")]
    qmarks=','.join('?' for _ in METROPOLE)
    metro=c.execute(f"SELECT COUNT(*) FROM purchase_observations WHERE market_kind='TRANSACTION' AND city_code IN ({qmarks})",tuple(METROPOLE)).fetchone()[0]
    bordeaux=c.execute("SELECT COUNT(*) FROM purchase_observations WHERE market_kind='TRANSACTION' AND city_code='33063'").fetchone()[0]
    by_year=[dict(r) for r in c.execute("SELECT substr(observed_date,1,4) year,COUNT(*) count FROM purchase_observations WHERE market_kind='TRANSACTION' GROUP BY year ORDER BY year DESC")]
    by_city=[dict(r) for r in c.execute("SELECT city,city_code,COUNT(*) count FROM purchase_observations WHERE market_kind='TRANSACTION' GROUP BY city,city_code ORDER BY count DESC LIMIT 40")]
    c.close()
    return {'total':total,'by_kind':by_kind,'by_source':by_source,'dvf_bordeaux_count':bordeaux,'dvf_metropole_count':metro,'dvf_by_year':by_year,'dvf_by_city':by_city,'truth_rule':'Counts are physical rows in RADAR database; zero means not loaded, never inferred.'}
