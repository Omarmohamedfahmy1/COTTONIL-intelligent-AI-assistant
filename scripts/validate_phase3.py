"""Reconcile executive presentation service against approved KPIs, no private rows."""
import argparse,json,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import analytics as api
from services.executive import dashboard,assistant_summary


def validate():
    checks={};observations=[]
    branches=api.branches()
    retail=branches.query("retail_location_type=='Retail branch'").branch_id.iloc[0]
    pos=branches.query("retail_location_type=='Point of sale / reseller'").branch_id.iloc[0]
    cases=[('company_complete',dict(start='2026-01-01',end='2026-09-30')),
           ('retail_category',dict(start='2026-08-01',end='2026-09-30',branch=retail,location_type='Retail branch',category='Socks')),
           ('pos_category',dict(start='2026-08-01',end='2026-09-30',branch=pos,location_type='Point of sale / reseller',category='Socks')),
           ('type_category',dict(start='2026-08-01',end='2026-09-30',location_type='Retail branch',category='Socks')),
           ('partial_month',dict(start='2026-09-15',end='2026-10-18',category='Socks')),
           ('empty_outside_coverage',dict(start='2010-01-01',end='2010-01-31'))]
    for name,scope in cases:
        start=time.perf_counter();result=dashboard(**scope);elapsed=time.perf_counter()-start
        base=api.overview(**scope);extra=assistant_summary(scope)['data'][0]
        residuals={}
        for key in ('sales','gross_profit','orders','customers','branches','units'):
            checks[f'{name}:base:{key}']=result['current'][key]==base[key]
        for key in ('sales','gross_profit','gross_margin_pct','orders','aov','customers','branches','growth_pct','stock_units','stock_value','high_risk_categories'):
            checks[f'{name}:assistant:{key}']=result['current'][key]==extra[key]
        for metric,frames in [('sales',('monthly','categories','channels','branches')),('gross_profit',('monthly','categories','branches'))]:
            for frame in frames:
                delta=float(result[frame][metric].sum()-base[metric])
                checks[f'{name}:{frame}:{metric}']=abs(delta)<.02
                residuals[f'{frame}:{metric}']=delta
        checks[f'{name}:growth']=result['current']['growth_pct']==api.sales_growth(**scope)['growth_pct']
        if not result['growth']['comparable_coverage']:
            checks[f'{name}:coverage_suppressed']=bool(result['comparison'].previous.isna().all() and result['comparison'].absolute_change.isna().all())
        observations.append({'case':name,'scope':scope,'dashboard_service_seconds':elapsed,
            'current':result['current'],'stock_month':result['stock_month'],'comparable_coverage':result['growth']['comparable_coverage'],
            'previous_period':result['previous_period'],'partial_month_count':result['partial_months'],'aggregate_residuals_EGP':residuals})
    return {'checks':checks,'passed':all(checks.values()),'observations':observations,
        'timing_method':'One uncached service invocation per case, perf_counter; existing local OS/SQLite cache, no cold-disk claim. UI caches separately.',
        'llm':'Not called; local verified executive report only'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'reports/phase_3_executive_validation.json')
    args=parser.parse_args();result=validate()
    args.report.write_text(json.dumps(result,indent=2,default=lambda v:v.item()),encoding='utf-8')
    print(f"Executive checks: {sum(result['checks'].values())}/{len(result['checks'])}")
    for item in result['observations']:print(item['case'],round(item['dashboard_service_seconds'],4),'seconds')
    raise SystemExit(0 if result['passed'] else 1)
