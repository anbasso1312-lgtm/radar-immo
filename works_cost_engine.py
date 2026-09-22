def estimate_scope(items):
    lines=[]; low=high=0.0; missing=[]
    for x in items or []:
        name=x.get('name') or 'poste'; qty=x.get('qty'); ulo=x.get('unit_low'); uhi=x.get('unit_high')
        if qty is None or ulo is None or uhi is None: missing.append(name); continue
        a=float(qty)*float(ulo); b=float(qty)*float(uhi); low+=a; high+=b
        lines.append({'name':name,'qty':qty,'unit':x.get('unit'),'low':round(a),'high':round(b),'source':x.get('source'),'date':x.get('date'),'confidence':x.get('confidence','UNKNOWN')})
    return {'status':'COSTED' if lines else 'INSUFFICIENT','low':round(low) if lines else None,'high':round(high) if lines else None,'central':round((low+high)/2) if lines else None,'lines':lines,'missing':missing,'method':'ITEMIZED_ONLY','note':'Prix unitaires uniquement documentés ou saisis.'}
