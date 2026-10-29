"""Aggregate Phase 5 reconciliation, parameterized line checks and timings."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pandas as pd
import analytics as api
from services import profitability as p, sales_branch as sb
from services.profitability_tools import answer_readonly
from services.filters import filters,predicate


def validate():
    checks={};observations=[];master=api.branches();first,last=api.metadata()
    retail=master.query("retail_location_type=='Retail branch'").branch_id.iloc[0]
    pos=master.query("retail_location_type=='Point of sale / reseller'").branch_id.iloc[0]
    empty=api.read('SELECT branch_id FROM branches b WHERE NOT EXISTS (SELECT 1 FROM sales_orders o WHERE o.branch_id=b.branch_id AND o.order_date=?) LIMIT 1',(str(first),)).iloc[0,0]
    cases=[('company',dict(start='2026-01-01',end='2026-09-30')),
        ('retail_category',dict(start='2026-08-01',end='2026-09-30',branch=retail,location_type='Retail branch',category='Socks')),
        ('pos_category',dict(start='2026-08-01',end='2026-09-30',branch=pos,location_type='Point of sale / reseller',category='Socks')),
        ('type_category',dict(start='2026-08-01',end='2026-09-30',location_type='Retail branch',category='Socks')),
        ('partial_month',dict(start='2026-09-15',end='2026-10-18',category='Socks')),
        ('no_orders_location',dict(start=str(first),end=str(first),branch=empty)),
        ('empty_outside_coverage',dict(start='2010-01-01',end='2010-01-31'))]
    def check(name,actual,expected,tolerance=.02):
        checks[name]=dict(actual=float(actual),expected=float(expected),passed=abs(float(actual)-float(expected))<=tolerance)
    for name,scope in cases:
        started=time.perf_counter();data=p.dashboard(**scope);elapsed=time.perf_counter()-started
        base=api.overview(**scope);residuals={}
        for key in ('sales','gross_profit','orders','units','customers','branches','refunds'):
            check(name+':core:'+key,data['current'][key],base[key])
        condition,params=predicate(filters(**scope),'i',include_category=True)
        raw=api.read(f'SELECT SUM(net_line_EGP) sales,SUM(margin_EGP) gross_profit,SUM(quantity) units FROM sales_order_items i WHERE {condition}',params).apply(pd.to_numeric).fillna(0).iloc[0]
        for key in ('sales','gross_profit','units'):check(name+':line_items:'+key,raw[key],base[key])
        for tag in ('products','categories','locations','monthly','category_monthly'):
            frame=data[tag]
            for key in ('sales','gross_profit','units'):
                residuals[tag+':'+key]=float(frame[key].sum()-base[key]);check(name+':'+tag+':'+key,frame[key].sum(),base[key])
            # Independent arithmetic audit; production ratio lives only in KPI services.
            for row in frame.loc[frame.sales.ne(0)].itertuples():
                check(name+':weighted:'+tag+':'+str(row.Index),row.gross_margin_pct,row.gross_profit/row.sales*100,1e-7)
        company=api.overview(scope['start'],scope['end'])['gross_profit']
        check(name+':company_denominator',data['company_gross_profit'],company)
        if company:
            check(name+':contribution',data['current']['company_gp_share_pct'],base['gross_profit']/company*100,1e-7)
        if not base['sales']:check(name+':undefined_margin',data['current']['gross_margin_pct'] is None,True,0)
        check(name+':no_net_profit',data['net_profit'] is None,True,0)
        check(name+':no_adjusted_gp',data['return_adjusted_gross_profit'] is None,True,0)
        if not data['growth']['comparable_coverage']:
            check(name+':previous_suppressed',data['category_changes'].gp_change.isna().all(),True,0)
        started=time.perf_counter();report=answer_readonly('profit5_products',scope,dict(limit=20));tool_seconds=time.perf_counter()-started
        expected=p.rank_products(data['products']).head(20)
        for i,row in enumerate(report['data']):
            check(name+':assistant:'+str(i),row['gross_profit'],expected.iloc[i].gross_profit,1e-7)
        report=answer_readonly('profit5_trends',scope)
        for key in ('sales','gross_profit','units'):check(name+':assistant_trends:'+key,sum(r[key] for r in report['data']),base[key])
        observations.append(dict(case=name,scope=scope,current=data['current'],dashboard_seconds=elapsed,
            products_tool_seconds=tool_seconds,residuals=residuals,product_count=len(data['products']),
            comparable_coverage=data['growth']['comparable_coverage'],partial_months=data['monthly'].loc[~data['monthly'].is_complete_period,'period'].tolist()))
    pair=answer_readonly('profit5_pair',cases[0][1],dict(branch_a=retail,branch_b=pos))
    for key in ('sales','gross_profit','units','orders'):
        row=next(r for r in pair['data'] if r['metric']==key)
        for identifier,side in ((retail,'location_a'),(pos,'location_b')):
            check('pair:'+side+':'+key,row[side],api.overview('2026-01-01','2026-09-30',identifier)[key])
    return dict(passed=all(c['passed'] for c in checks.values()),checks=checks,observations=observations,
        timing_method='perf_counter; one uncached Python service call per case, OS/SQLite caches may be warm; no cold-disk or concurrency claim. UI scope/database-mtime cache TTL 1200 seconds.',
        llm='Not called; fixed read-only local tools only')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,default=ROOT/'reports/phase_5_reconciliation.json');args=parser.parse_args()
    result=validate();args.report.write_text(json.dumps(result,indent=2,default=lambda x:x.item()),encoding='utf-8')
    print('Phase 5 checks:',sum(c['passed'] for c in result['checks'].values()),'/',len(result['checks']))
    for row in result['observations']:print(row['case'],round(row['dashboard_seconds'],4),'seconds')
    raise SystemExit(0 if result['passed'] else 1)
