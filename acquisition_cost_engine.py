from __future__ import annotations

def notary_emoluments_ht(base: float) -> float:
    brackets=[(6500,.03870),(10500,.01596),(43000,.01064),(float('inf'),.00799)]
    remaining=max(0.0,float(base)); total=0.0
    for width,rate in brackets:
        part=min(remaining,width); total += part*rate; remaining -= part
        if remaining<=0: break
    return total

def estimate_acquisition_costs(*,price:float,agency_fee:float=0,agency_paid_by_buyer:bool=False,
                               department_rate:float=.05,commune_rate:float=.012,
                               collection_rate_on_department:float=.0237,
                               security_contribution_rate:float=.001,
                               formalities_and_disbursements:float=1400,vat:float=.20,
                               dmto_exempt_surcharge:bool=False,new_property_or_full_vat:bool=False)->dict:
    if price<=0: raise ValueError('price must be > 0')
    taxable=max(0.0,price-(agency_fee if agency_paid_by_buyer else 0))
    if new_property_or_full_vat:
        transfer=0.0
    else:
        dept=taxable*department_rate
        commune=taxable*commune_rate
        collection=dept*collection_rate_on_department
        transfer=dept+commune+collection
    emol=notary_emoluments_ht(taxable)
    emol_ttc=emol*(1+vat)
    security=taxable*security_contribution_rate
    total=transfer+emol_ttc+security+formalities_and_disbursements
    return {'taxable_base':round(taxable),'transfer_taxes':round(transfer),'notary_emoluments_ttc':round(emol_ttc),
            'security_contribution':round(security),'formalities_and_disbursements':round(formalities_and_disbursements),
            'notary_and_tax_total':round(total),'notary_and_tax_pct_of_price':round(total/price*100,2)}
