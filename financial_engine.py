from __future__ import annotations
from typing import Optional


def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    n = years * 12
    m = annual_rate / 12
    if m == 0:
        return principal / n
    return principal * m / (1 - (1 + m) ** (-n))


def quick_metrics(*, price: float, rent: float, works: float = 0, acquisition_cost_rate: float = .08,
                  down_payment: float = 0, annual_rate: float = .035, loan_years: int = 25,
                  insurance_rate: float = .003, property_tax: Optional[float] = None,
                  annual_charges: Optional[float] = None, maintenance_rate: float = .0075,
                  vacancy_rate: float = .05, management_rate: float = 0) -> dict:
    # Unknown expenses are estimated for QUICK RADAR, never silently presented as documented.
    tax = property_tax if property_tax is not None else max(450.0, price * .0045)
    charges = annual_charges if annual_charges is not None else max(480.0, price * .004)
    acq = price * acquisition_cost_rate
    total = price + acq + works
    debt = max(0.0, total - down_payment)
    payment = monthly_payment(debt, annual_rate, loan_years)
    insurance = debt * insurance_rate / 12
    effective_rent = rent * (1 - vacancy_rate)
    management = effective_rent * management_rate
    maintenance = price * maintenance_rate / 12
    fixed = tax / 12 + charges / 12
    operating_before_debt = effective_rent - management - maintenance - fixed
    cashflow = operating_before_debt - payment - insurance
    noi = operating_before_debt * 12
    debt_service = (payment + insurance) * 12
    return {
        'price': round(price), 'acquisition_costs': round(acq), 'total_project': round(total),
        'debt': round(debt), 'monthly_payment': round(payment), 'insurance_monthly': round(insurance),
        'gross_yield_pct': round((rent * 12 / price * 100) if price else 0, 2),
        'net_yield_before_financing_pct': round((noi / total * 100) if total else 0, 2),
        'monthly_cashflow': round(cashflow),
        'annual_noi': round(noi), 'dscr': round(noi / debt_service, 2) if debt_service else None,
        'capital_required': round(down_payment),
        'assumptions': {
            'property_tax': {'value': round(tax), 'status': 'DOCUMENTED' if property_tax is not None else 'ESTIMATED'},
            'annual_charges': {'value': round(charges), 'status': 'DOCUMENTED' if annual_charges is not None else 'ESTIMATED'},
            'vacancy_rate_pct': round(vacancy_rate * 100, 1),
            'maintenance_rate_pct': round(maintenance_rate * 100, 2),
        }
    }


def price_curve(*, asking_price: float, rent: float, works: float, kwargs: dict) -> list[dict]:
    # Useful negotiation ladder: asking price then -5/-10/-15/-20%.
    rows = []
    for discount in (0, .05, .10, .15, .20):
        p = asking_price * (1 - discount)
        m = quick_metrics(price=p, rent=rent, works=works, **kwargs)
        rows.append({'discount_pct': round(discount * 100), **m})
    return rows
