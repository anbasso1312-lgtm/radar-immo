from purchase_market_database import con
def purchase_data_status():
    c=con(); total=c.execute("SELECT COUNT(*) FROM purchase_observations").fetchone()[0]
    by_kind=[dict(r) for r in c.execute("SELECT market_kind,COUNT(*) count,MIN(observed_date) first_date,MAX(observed_date) last_date,COUNT(DISTINCT source) sources FROM purchase_observations GROUP BY market_kind")]
    by_source=[dict(r) for r in c.execute("SELECT source,market_kind,COUNT(*) count,MAX(observed_date) last_date FROM purchase_observations GROUP BY source,market_kind ORDER BY count DESC")]
    dvf=c.execute("SELECT COUNT(*) FROM purchase_observations WHERE market_kind='TRANSACTION' AND (city_code='33063' OR lower(city)='bordeaux')").fetchone()[0]; c.close()
    return {'total':total,'by_kind':by_kind,'by_source':by_source,'dvf_bordeaux_count':dvf,'truth_rule':'Counts are physical rows in RADAR database; zero means not loaded, never inferred.'}
