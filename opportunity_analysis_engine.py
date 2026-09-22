from __future__ import annotations
from resale_engine import analyze_resale

def _scenario(name,purchase_price,exit_value,works):
    missing=[]
    if exit_value is None: missing.append('Valeur de sortie prudente')
    if works is None: missing.append('Coût travaux')
    if missing: return {'scenario':name,'status':'INSUFFICIENT','missing':missing,'prudent_margin':None}
    r=analyze_resale(purchase_price=purchase_price,prudent_exit_value=exit_value,works=works)
    return {'scenario':name,'status':r['status'],'prudent_margin':r['prudent_margin'],
      'margin_on_cost_pct':r['margin_on_cost_pct'],'max_purchase_price':r['max_purchase_price_for_target_margin'],
      'stress_tests':r['stress_tests'],'missing':r['missing']}

def analyze_opportunity(*,purchase_price,direct_exit_value=None,renovated_exit_value=None,renovation_cost=None,
                        created_m2=None,created_m2_value=None,created_m2_cost=None,created_m2_validated=False):
    direct=_scenario('DIRECT_RESALE',purchase_price,direct_exit_value,0)
    renovation=_scenario('RENOVATION',purchase_price,renovated_exit_value,renovation_cost)
    created_value=(created_m2*created_m2_value) if created_m2_validated and created_m2 is not None and created_m2_value is not None else None
    creation=_scenario('CREATED_M2',purchase_price,(direct_exit_value+created_value) if direct_exit_value is not None and created_value is not None else None,created_m2_cost)
    if not created_m2_validated:
        creation.update({'status':'UNVALIDATED_POTENTIAL','prudent_created_value':0,
          'note':'Potentiel visible, contribution prudente 0 € jusqu’à validation juridique/urbanisme/technique.'})
    return {'purchase_price':purchase_price,'scenarios':[direct,renovation,creation],
      'rules':['UNKNOWN != ZERO','NO EVIDENCE -> NO FACT','3D IMAGE != PROPERTY CONDITION']}
