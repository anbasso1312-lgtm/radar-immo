def compare_states(current,target,works,extra_costs=0):
    cur=current.get('value_median'); tar=target.get('value_median'); cost=works.get('central')
    if None in (cur,tar,cost): return {'status':'INSUFFICIENT','net_created_value':None,'missing':['valeur actuelle','valeur cible','coût travaux']}
    net=float(tar)-float(cur)-float(cost)-float(extra_costs)
    return {'status':'COSTED_SCENARIO','current_value':cur,'target_value':tar,'works':cost,'extra_costs':extra_costs,'net_created_value':round(net),'marginal_works_return':round(net/cost,2) if cost else None}
