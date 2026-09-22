from __future__ import annotations
from acquisition_cost_engine import estimate_acquisition_costs

def analyze_resale(*,purchase_price:float,prudent_exit_value:float,works:float=0,agency_fee_buy:float=0,
                   agency_paid_by_buyer:bool=False,resale_agency_fee:float=0,financing_cost:float=0,
                   holding_cost:float=0,technical_costs:float=0,contingency:float=0,taxes_on_resale:float|None=None,
                   target_margin_rate:float=.12,department_rate:float=.05,formalities_and_disbursements:float=1400)->dict:
    acq=estimate_acquisition_costs(price=purchase_price,agency_fee=agency_fee_buy,agency_paid_by_buyer=agency_paid_by_buyer,
        department_rate=department_rate,formalities_and_disbursements=formalities_and_disbursements)
    known_tax=taxes_on_resale is not None
    tax=float(taxes_on_resale or 0)
    fixed=works+financing_cost+holding_cost+technical_costs+contingency+resale_agency_fee+tax
    total=purchase_price+acq['notary_and_tax_total']+fixed
    margin=prudent_exit_value-total
    def cost(p):
        a=estimate_acquisition_costs(price=p,agency_fee=agency_fee_buy,agency_paid_by_buyer=agency_paid_by_buyer,
          department_rate=department_rate,formalities_and_disbursements=formalities_and_disbursements)
        return p+a['notary_and_tax_total']+fixed
    lo,hi=0.0,prudent_exit_value
    for _ in range(60):
        mid=(lo+hi)/2; c=cost(mid)
        if prudent_exit_value-c >= c*target_margin_rate: lo=mid
        else: hi=mid
    stress=[]
    for drop,up in [(0,0),(.05,.10),(.10,.20)]:
        sc=purchase_price+acq['notary_and_tax_total']+works*(1+up)+financing_cost+holding_cost+technical_costs+contingency+resale_agency_fee+tax
        ex=prudent_exit_value*(1-drop); m=ex-sc
        stress.append({'exit_drop_pct':round(drop*100),'works_increase_pct':round(up*100),'margin':round(m),
                       'margin_on_cost_pct':round(m/sc*100,2) if sc else None})
    return {'status':'COSTED' if known_tax else 'PARTIAL','strategy':'RESALE','purchase_price':round(purchase_price),
      'prudent_exit_value':round(prudent_exit_value),'acquisition_costs':acq,'total_project_cost':round(total),
      'prudent_margin':round(margin),'margin_on_cost_pct':round(margin/total*100,2) if total else None,
      'max_purchase_price_for_target_margin':round(lo),'stress_tests':stress,
      'missing':[] if known_tax else ['Fiscalité de revente non documentée : marge affichée avant fiscalité inconnue.']}
