from __future__ import annotations

def classify_condition(observations=None):
    observations=observations or []; usable=[]; excluded=[]
    for o in observations:
        vt=str(o.get('visual_type') or 'INDETERMINE').upper()
        if vt=='PHOTO_PROBABLE' and o.get('condition_signal') in {'NO_WORKS','MEDIUM_WORKS','HEAVY_WORKS'}: usable.append(o)
        else: excluded.append(o)
    signals=[o['condition_signal'] for o in usable]
    if not signals: condition='INCONNU'; confidence='FAIBLE'
    elif 'HEAVY_WORKS' in signals: condition='3_TOUT_A_REFAIRE_APPARENT'; confidence='MOYENNE'
    elif 'MEDIUM_WORKS' in signals: condition='2_TRAVAUX_MOYENS_APPARENTS'; confidence='MOYENNE'
    else: condition='1_PAS_DE_TRAVAUX_APPARENTS'; confidence='MOYENNE'
    return {'condition':condition,'confidence':confidence,'works_cost':None,'usable_observations':len(usable),
      'excluded_visuals':len(excluded),'rule':'3D/plan/indéterminé != état réel; coût travaux inconnu avant visite/devis.'}
