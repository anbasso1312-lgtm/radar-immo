def screen_land(*,parcel_known=False,urbanism_known=False,access_known=False,networks_known=False,private_rules_known=False,candidate_m2=None):
    checks={'parcel/unit_fonciere':parcel_known,'urbanism':urbanism_known,'access':access_known,'networks':networks_known,'private_rules':private_rules_known}; missing=[k for k,v in checks.items() if not v]
    stage='DETECTED' if not parcel_known else ('PLAUSIBLE' if not urbanism_known else ('DOCUMENTED' if missing else 'LEGALLY_SCREENED'))
    return {'stage':stage,'candidate_m2':candidate_m2,'prudent_valued_m2':candidate_m2 if not missing else 0,'checks':checks,'missing':missing,'warning':'Cadastre/PLU seuls ne prouvent ni divisibilité ni constructibilité opérationnelle.'}
