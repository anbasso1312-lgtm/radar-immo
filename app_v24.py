from __future__ import annotations
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field
from connectors import enrich
from financial_engine import quick_metrics, price_curve
from acquisition_cost_engine import estimate_acquisition_costs
from resale_engine import analyze_resale
from property_condition_engine import classify_condition
from opportunity_analysis_engine import analyze_opportunity

app=FastAPI(title="RADAR IMMO",version="2.4.0")

class ResaleIn(BaseModel):
    purchase_price:float=Field(gt=0)
    prudent_exit_value:float=Field(gt=0)
    works:float=Field(0,ge=0)
    resale_agency_fee:float=Field(0,ge=0)
    financing_cost:float=Field(0,ge=0)
    holding_cost:float=Field(0,ge=0)
    technical_costs:float=Field(0,ge=0)
    contingency:float=Field(0,ge=0)
    taxes_on_resale:Optional[float]=Field(None,ge=0)
    target_margin_rate:float=Field(.12,ge=0,le=.8)

class ConditionIn(BaseModel):
    observations:list[dict]=Field(default_factory=list)

class OpportunityIn(BaseModel):
    purchase_price:float=Field(gt=0)
    direct_exit_value:Optional[float]=None
    renovated_exit_value:Optional[float]=None
    renovation_cost:Optional[float]=Field(None,ge=0)
    created_m2:Optional[float]=Field(None,ge=0)
    created_m2_value:Optional[float]=Field(None,ge=0)
    created_m2_cost:Optional[float]=Field(None,ge=0)
    created_m2_validated:bool=False

@app.get("/api/health")
def health(): return {"status":"ok","version":"2.4.0"}

@app.post("/api/resale/analyze")
def resale(x:ResaleIn): return analyze_resale(**x.model_dump())

@app.post("/api/evidence/condition")
def condition(x:ConditionIn): return classify_condition(x.observations)

@app.post("/api/opportunity/analyze")
def opportunity(x:OpportunityIn): return analyze_opportunity(**x.model_dump())

@app.get("/")
def root():
    return {"product":"RADAR IMMO","version":"2.4.0","mission":"Détecter les opportunités achat-revente, rénovation/transformation et création de m²","rules":["NO EVIDENCE -> NO FACT","UNKNOWN != ZERO","3D IMAGE != PROPERTY CONDITION"]}
