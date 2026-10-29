"""Phase 6 real-data stock, heuristic and transfer reconciliation/performance."""
import argparse,json,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services import inventory as inv,metrics as kpi
from services.filters import filters
from services.inventory_tools import answer_readonly
from db.connection import read


def validate():
    checks={};observations=[]
    def check(name,actual,expected,tol=1e-6):
        checks[name]=dict(actual=float(actual),expected=float(expected),passed=abs(float(actual)-float(expected))<=tol)
    master=kpi.branches();retail=master.query("retail_location_type=='Retail branch'").branch_id.iloc[0];pos=master.query("retail_location_type=='Point of sale / reseller'").branch_id.iloc[0]
    cases=[('company',dict(start='2026-01-01',end='2026-09-30')),
        ('retail_category',dict(start='2026-08-01',end='2026-09-30',branch=retail,location_type='Retail branch',category='Socks')),
        ('pos_category',dict(start='2026-08-01',end='2026-09-30',branch=pos,location_type='Point of sale / reseller',category='Socks')),
        ('type_category',dict(start='2026-08-01',end='2026-09-30',location_type='Retail branch',category='Socks')),
        ('partial_end',dict(start='2026-09-15',end='2026-10-18',category='Socks')),
        ('early_coverage',dict(start='2018-10-19',end='2018-11-30')),
        ('empty',dict(start='2010-01-01',end='2010-01-31'))]
    for name,scope in cases:
        for kind in ('Branch','Warehouse'):
            key=name+':'+kind;started=time.perf_counter();data=inv.dashboard(**scope,kind=kind);elapsed=time.perf_counter()-started
            frame=data['rows'];month=data['month'];s=filters(**scope)
            if month:
                check(key+':cutoff',month<=inv.month_cutoff(scope['end']),True,0)
                condition,params=inv._stock_predicate(s,kind)
                direct=read(f'''SELECT SUM(closing_units) stock_units,SUM(closing_stock_value_EGP) stock_value,COUNT(*) combinations,
                    SUM(CASE WHEN stockout_risk_score>=.7 THEN 1 ELSE 0 END) high FROM monthly_stock s WHERE {condition} AND year_month=?''',[*params,month]).iloc[0]
                for metric in ('stock_units','stock_value'):
                    check(key+':recorded:'+metric,data['summary'][metric],direct[metric])
                    check(key+':category:'+metric,data['categories'][metric].sum(),direct[metric])
                check(key+':high_risk',data['summary']['high_risk_combinations'],direct['high'],0)
                check(key+':row_count',len(frame),direct['combinations'],0)
                check(key+':category_partition',data['categories'].high_risk_combinations.sum(),direct['high'],0)
                if kind=='Branch' and data['window']['complete']:
                    for row in frame.itertuples():
                        prefix=key+':'+row.location_id+':'+row.category
                        check(prefix+':rate',row.daily_units,row.sold_units/data['window']['days'])
                        if row.daily_units>0:check(prefix+':cover',row.cover_days,row.stock_units/row.daily_units)
                        else:check(prefix+':undefined_cover',pd.isna(row.cover_days),True,0)
                        import math
                        check(prefix+':replenishment',row.estimated_replenishment,max(0,math.ceil(row.daily_units*30-row.stock_units)),0)
                    w=data['window'];sales=kpi.overview(w['start'],w['end'],scope.get('branch'),location_type=scope.get('location_type'),category=scope.get('category'))
                    # Available audited real snapshots cover every catalog category/location.
                    check(key+':sales_velocity_units',frame.sold_units.sum(),sales['units'],0)
                else:
                    check(key+':unavailable_estimates',frame.estimated_replenishment.isna().all(),True,0)
                if kind=='Branch':
                    legacy_month,legacy=kpi.inventory_snapshot(scope['end'],scope.get('branch'),location_type=scope.get('location_type'),category=scope.get('category'))
                    if legacy_month==month:check(key+':approved_stock',legacy.stock_units.sum(),data['summary']['stock_units'],0)
                report=answer_readonly('inventory6_stock' if kind=='Branch' else 'inventory6_warehouse',scope)
                check(key+':assistant_total',report['meta']['totals']['stock_units'],data['summary']['stock_units'],0)
                if name=='partial_end':check(key+':partial_end_uses_september',month=='2026-09',True,0)
            else:
                check(key+':no_fabricated_balance',data['summary']['stock_units'] is None,True,0)
                check(key+':empty_rows',frame.empty,True,0)
            observations.append(dict(case=name,kind=kind,snapshot=month,summary=data['summary'],sales_window=data['window'],dashboard_seconds=elapsed))
        for status in (None,*inv.STATUSES):
            key=name+':transfers:'+str(status);started=time.perf_counter();data=inv.transfer_analysis(**scope,status=status);elapsed=time.perf_counter()-started
            conditions=['t.transfer_date BETWEEN ? AND ?'];params=[scope['start'],scope['end']]
            if status:conditions.append('t.transfer_status=?');params.append(status)
            if scope.get('branch'):conditions.append('t.destination_branch_id=?');params.append(scope['branch'])
            if scope.get('location_type'):conditions.append('t.destination_branch_id IN (SELECT branch_id FROM branches WHERE retail_location_type=?)');params.append(scope['location_type'])
            if scope.get('category'):conditions.append('EXISTS (SELECT 1 FROM inventory_transfer_items x JOIN sku_variants v ON v.sku_id=x.sku_id JOIN products_catalog p ON p.product_id=v.product_id WHERE x.transfer_id=t.transfer_id AND p.category_en=?)');params.append(scope['category'])
            where=' AND '.join(conditions)
            header=read(f'SELECT COUNT(*) transfers,COALESCE(SUM(transport_cost_EGP),0) cost FROM inventory_transfers t WHERE {where}',params).iloc[0]
            quantity=read(f'''SELECT COALESCE(SUM(l.quantity_units),0) units FROM inventory_transfers t
                JOIN inventory_transfer_items l ON l.transfer_id=t.transfer_id JOIN sku_variants v ON v.sku_id=l.sku_id
                JOIN products_catalog p ON p.product_id=v.product_id WHERE {where}'''+(' AND p.category_en=?' if scope.get('category') else ''),[*params,*([scope['category']] if scope.get('category') else [])]).iloc[0,0]
            check(key+':headers',data['summary']['transfer_count'],header['transfers'],0)
            check(key+':transport_once',data['summary']['transport_cost'],header['cost'])
            check(key+':units',data['summary']['transfer_units'],quantity,0)
            for tag in ('monthly','statuses','sources','destinations','categories'):
                check(key+':'+tag,data[tag].transfer_units.sum(),quantity,0)
            observations.append(dict(case=name,status=status,transfer_seconds=elapsed,transfer_summary=data['summary']))
    pair=answer_readonly('inventory6_pair',cases[0][1],dict(branch_a=retail,branch_b=pos))
    for identifier,side in ((retail,'a'),(pos,'b')):
        expected=inv.dashboard(**cases[0][1],branch=identifier)
        check('pair:'+identifier,sum(row['stock_units_'+side] for row in pair['data']),expected['summary']['stock_units'],0)
    branch_data=inv.dashboard(**cases[0][1]);warehouse_data=inv.dashboard(**cases[0][1],kind='Warehouse')
    network=inv.network_distribution(branch_data,warehouse_data)
    check('network:sales_units',network.sales_location_stock_units.sum(),branch_data['summary']['stock_units'],0)
    check('network:warehouse_units',network.warehouse_stock_units.sum(),warehouse_data['summary']['stock_units'],0)
    for row in network.itertuples():
        check('network:warehouse_share:'+row.category,row.displayed_warehouse_share_pct,row.warehouse_stock_units/(row.warehouse_stock_units+row.sales_location_stock_units)*100)
    return dict(passed=all(v['passed'] for v in checks.values()),checks=checks,observations=observations,
        timing_method='perf_counter, uncached service calls; OS/SQLite caches may be warm. No cold-disk or production concurrency claim.',
        limitations='Monthly category balances only; conservative completed-month cutoff; no warehouse demand, SKU on-hand or complete movement ledger; no external LLM calls')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=ROOT/'reports/phase_6_reconciliation.json');args=parser.parse_args()
    result=validate()
    # Strict JSON: undefined estimates are represented by null, not nonstandard NaN.
    text=json.dumps(result,default=lambda x:x.item());text=text.replace('NaN','null')
    args.report.write_text(json.dumps(json.loads(text),indent=2),encoding='utf-8')
    print('Phase 6 checks:',sum(c['passed'] for c in result['checks'].values()),'/',len(result['checks']))
    for row in result['observations']:
        if 'dashboard_seconds' in row:print(row['case'],row['kind'],round(row['dashboard_seconds'],4),'seconds')
    raise SystemExit(0 if result['passed'] else 1)
