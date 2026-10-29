"""Phase 4 aggregate/assistant reconciliation and timing; no private records."""
import argparse,json,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import analytics as api
from services import sales_branch as sb
from services.sales_branch_tools import answer_readonly


def validate():
    checks={};observations=[];master=api.branches()
    retail=master.query("retail_location_type=='Retail branch'").branch_id.iloc[0]
    pos=master.query("retail_location_type=='Point of sale / reseller'").branch_id.iloc[0]
    first,last=api.metadata()
    empty=api.read('SELECT branch_id FROM branches b WHERE NOT EXISTS (SELECT 1 FROM sales_orders o WHERE o.branch_id=b.branch_id AND o.order_date=?) LIMIT 1',(str(first),)).iloc[0,0]
    cases=[('company',dict(start='2026-01-01',end='2026-09-30')),
        ('retail_category',dict(start='2026-08-01',end='2026-09-30',branch=retail,location_type='Retail branch',category='Socks')),
        ('pos_category',dict(start='2026-08-01',end='2026-09-30',branch=pos,location_type='Point of sale / reseller',category='Socks')),
        ('type_category',dict(start='2026-08-01',end='2026-09-30',location_type='Retail branch',category='Socks')),
        ('partial_month',dict(start='2026-09-15',end='2026-10-18',category='Socks')),
        ('no_orders_location',dict(start=str(first),end=str(first),branch=empty)),
        ('empty_outside_coverage',dict(start='2010-01-01',end='2010-01-31'))]
    def check(name,actual,expected,tolerance=.02):
        passed=abs(float(actual)-float(expected))<=tolerance
        checks[name]={'actual':float(actual),'expected':float(expected),'passed':passed}
    for name,scope in cases:
        started=time.perf_counter();data=sb.sales_analysis(**scope);elapsed=time.perf_counter()-started
        base=api.overview(**scope);residuals={}
        for key in ('sales','gross_profit','orders','units','customers','branches'):
            check(name+':core:'+key,data['current'][key],base[key])
        for grain in sb.GRAINS:
            frame=sb.sales_trends(**scope,grain=grain)
            for key in ('sales','gross_profit','orders','units'):check(name+':'+grain+':'+key,frame[key].sum(),base[key])
        for frame in ('products','categories','category_monthly'):
            for key in ('sales','gross_profit','units'):
                residuals[frame+':'+key]=float(data[frame][key].sum()-base[key])
                check(name+':'+frame+':'+key,data[frame][key].sum(),base[key])
        for key in ('sales','orders'):check(name+':channels:'+key,data['channels'][key].sum(),base[key])
        started=time.perf_counter()
        roster=sb.location_roster(scope['start'],scope['end'],location_type=scope.get('location_type'),category=scope.get('category'))
        roster_seconds=time.perf_counter()-started
        selected=roster if not scope.get('branch') else roster.loc[roster.branch_id.eq(scope['branch'])]
        for key in ('sales','gross_profit','orders','units'):check(name+':roster:'+key,selected[key].sum(),base[key])
        expected=master if not scope.get('location_type') else master.loc[master.retail_location_type.eq(scope['location_type'])]
        check(name+':master_count',len(roster),len(expected),0)
        check(name+':recorded_partition',int(roster.recorded_orders.sum())+int((~roster.recorded_orders).sum()),len(roster),0)
        report=answer_readonly('sales4_trends',scope)
        for key in ('sales','orders','units','gross_profit'):check(name+':assistant_trends:'+key,sum(r[key] for r in report['data']),base[key])
        if not data['growth']['comparable_coverage']:
            check(name+':invalid_previous_suppressed',int(data['comparison'].previous.isna().all()),1,0)
        if not base['orders']:check(name+':empty_aov_unavailable',int(data['current']['aov'] is None),1,0)
        observations.append({'case':name,'scope':scope,'current':data['current'],'sales_analysis_seconds':elapsed,
            'location_roster_seconds':roster_seconds,'eligible_locations':len(roster),'no_recorded_order_locations':int((~roster.recorded_orders).sum()),
            'aggregate_residuals':residuals,'comparable_coverage':data['growth']['comparable_coverage']})
    for a,b in [(retail,pos),(pos,retail)]:
        started=time.perf_counter();pair=sb.compare_two('2026-01-01','2026-09-30',a,b,category='Socks');seconds=time.perf_counter()-started
        context=dict(start='2026-01-01',end='2026-09-30',branch=retail,location_type='Retail branch',category='Socks')
        report=answer_readonly('two_location_comparison',context,dict(branch_a=a,branch_b=b))
        for side,identifier,column in [('left',a,'location_a'),('right',b,'location_b')]:
            for key in ('sales','gross_profit','orders','units'):
                check(a+':'+b+':pair:'+side+':'+key,pair[side]['current'][key],api.overview('2026-01-01','2026-09-30',identifier,category='Socks')[key])
            check(a+':'+b+':pair_assistant:'+side,report['data'][0][column],pair[side]['current']['sales'])
            check(a+':'+b+':pair_trend:'+side,pair['monthly'].loc[pair['monthly'].branch_id.eq(identifier),'sales'].sum(),pair[side]['current']['sales'])
        observations.append({'pair':[a,b],'pair_seconds':seconds,'type_order':pair['locations'].retail_location_type.tolist()})
    return {'checks':checks,'passed':all(v['passed'] for v in checks.values()),'observations':observations,
        'timing_method':'perf_counter, one uncached service invocation per case; existing OS/SQLite cache, no cold-disk claim; UI caches by scope/grain and database mtime.',
        'llm':'Not called; local fixed read-only tools only'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'reports/phase_4_reconciliation.json');args=parser.parse_args()
    result=validate();args.report.write_text(json.dumps(result,indent=2,default=lambda x:x.item()),encoding='utf-8')
    print('Phase 4 checks:',sum(c['passed'] for c in result['checks'].values()),'/',len(result['checks']))
    for x in result['observations']:print(x.get('case',x.get('pair')),round(x.get('sales_analysis_seconds',x.get('pair_seconds')),4),'seconds')
    raise SystemExit(0 if result['passed'] else 1)
