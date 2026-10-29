"""Bilingual managerial narrative assembled only from approved evidence cells."""
import math,re
from decimal import Decimal,ROUND_HALF_UP
from ui.i18n import t,TEXT,ltr,category_name
from ui.components import money
from services.assistant_request import metrics_in,complete_requested_selection
from services.assistant_capabilities import CAPABILITIES
from services.assistant_findings import components,observations,comparison
from services.assistant_obligations import ranked_sets,forecast_evaluation,customer_evaluation,typed_support

DOMAINS={'sales':('sales and executive KPIs','المبيعات والمؤشرات التنفيذية'),
 'profitability':('gross profitability','مجمل الربحية'),'inventory':('recorded inventory','المخزون المسجّل'),
 'forecast':('evaluated forecasts','التوقعات المقيّمة'),'customers':('aggregate customer intelligence','مؤشرات العملاء المجمّعة')}
STATES={
 'full':('Complete verified answer','إجابة موثقة مكتملة'),
 'partial':('Partial answer — incomplete analysis','إجابة جزئية — تحليل غير مكتمل'),
 'unavailable':('Unavailable from these data','غير متاح من هذه البيانات'),
 'clarification':('Clarification needed','يلزم توضيح'),
 'provider_error':('Groq provider error — no complete answer','خطأ من Groq — لا توجد إجابة مكتملة'),
 'budget_exhausted':('Request budget reached — analysis stopped','بلغ الطلب حد الاستخدام — توقف التحليل'),
 'blocked':('Restricted request','طلب مقيّد'),'unsupported':('Unsupported question','سؤال غير مدعوم')}
def label(state,lang):return STATES.get(state,STATES['partial'])[0 if lang=='English' else 1]
def detailed_results(result,lang):
    english=lang=='English';state=result.get('answer_state','partial');code=result.get('code')
    if result.get('capability_limitations') and not result.get('reports') and state!='clarification':
        from services.assistant_limits import explanations
        return ' '.join(explanations(result['capability_limitations'],lang))
    if state=='blocked':return t('a9_blocked',lang)
    if state=='unsupported':return t('unsupported',lang)
    if state=='clarification':
        prompts={
            'dates':('Which historical period should be used (or which two ISO dates)?','ما الفترة التاريخية المطلوبة أو تاريخا البداية والنهاية؟'),
            'metrics':('Which metrics should be reused? The referenced metric bundle is not available in this context.','ما المؤشرات المطلوب تكرارها؟ مجموعة المؤشرات المشار إليها غير متاحة في هذا السياق.'),
            'locations':('Which two valid, distinct location IDs should be compared?','ما رمزا الموقعين المختلفين المطلوب مقارنتهما؟'),
            'categories':('Which supported category should be used, or all categories?','ما الفئة المطلوبة، أم تريد كل الفئات؟'),
            'products':('Which valid catalog product IDs should be analyzed?','ما رموز المنتجات الصحيحة من الكتالوج المطلوب تحليلها؟'),
            'warehouses':('Which valid warehouse ID should be used, or all warehouses?','ما رمز المستودع الصحيح المطلوب، أم تريد كل المستودعات؟'),
            'forecast_category':('Monthly unit forecasts require one category; which category should be forecast?','توقع الوحدات الشهري يحتاج فئة واحدة؛ ما الفئة المطلوب توقعها؟'),
            'horizon':('Which forecast horizon: 1, 3 or 6 months?','ما أفق التوقع المطلوب: شهر أم 3 أم 6 أشهر؟')}
        fields=result.get('clarification_fields',[])
        if fields:return next((prompts[f][0 if english else 1] for f in fields if f in prompts),t('a9_clarify',lang))
        if code=='no_compatible_tool':return 'No approved tool covers this combination of metrics and aggregation.' if english else 'لا توجد أداة معتمدة تغطي هذا الجمع بين المؤشرات ومستوى التجميع.'
        if result.get('resolved',{}).get('scope'):return 'The request scope is resolved, but no verified result was returned.' if english else 'تم تحديد نطاق الطلب، لكن لم تُرجع الأدوات نتيجة موثقة.'
        return t('a9_clarify',lang)
    if state=='unavailable':
        if code=='unavailable':return t('a9_unavailable',lang)
        return ('The requested period, target or observations are unavailable. Empty query results do not establish zero real business activity.' if english else
                'الفترة أو الهدف أو المشاهدات المطلوبة غير متاحة. النتيجة الفارغة لا تثبت انعدام النشاط الحقيقي.')
    lines=[]
    overview=next((r for r in result.get('reports',[]) if r['meta']['tool']=='company_overview' and r['data']),None)
    if overview:
        row=overview['data'][0]
        lines.append(t('answer_sales',lang,sales=money(row['sales'],lang,False),profit=money(row['gross_profit'],lang,False),orders=f"{row['orders']:,}"))
    resolved=result.get('resolved',{});scope=resolved.get('scope',{})
    names=[DOMAINS.get(d,(d,d))[0 if english else 1] for d in result.get('requested_domains',[])]
    if scope:
        location=' ↔ '.join(resolved.get('pair',[])) or scope.get('branch') or t('all_locations',lang)
        category=category_name(scope['category'],lang) if scope.get('category') else t('all_categories',lang)
        lines.append(('Interpreted request: ' if english else 'الطلب المفسّر: ')+', '.join(names or [('verified evidence' if english else 'الأدلة الموثقة')])+
            f". {ltr(scope['start'],lang)} → {ltr(scope['end'],lang)} · {ltr(location,lang)} · {category}.")
    for fact in result.get('facts',[]):
        if overview and fact['tool']=='company_overview':continue
        metric=t(fact['metric'],lang) if fact['metric'] in TEXT else fact['metric'].replace('_',' ')
        value=money(fact['value'],lang,False) if fact['unit']=='EGP' else ltr(f"{fact['value']:,.4f}" if fact['unit']=='ratio' else f"{fact['value']:,.2f}",lang)
        if fact['unit']=='percent':value+='%'
        entity=category_name(str(fact['entity']),lang) if fact['entity'] else ''
        lines.append(f"{entity} · {metric}: {value} [{fact['evidence_id']}].")
    classes=list(dict.fromkeys(r['meta'].get('classification','recorded') for r in result.get('reports',[])))
    for metric in ('sales','gross_profit'):
        compared=[f for f in result.get('facts',[]) if f['metric']==metric and f['entity'] in resolved.get('pair',[])]
        if len(compared)==2 and compared[0]['value']!=compared[1]['value']:
            leader=max(compared,key=lambda f:f['value'])
            lines.append((f"Recorded comparison: {leader['entity']} has the higher {metric.replace('_',' ')} in this scope; this does not establish a cause." if english else
                f"المقارنة المسجّلة: {leader['entity']} أعلى في {t(metric,lang)} ضمن هذا النطاق؛ ولا يثبت ذلك سببًا."))
    if any(f['tool']=='inventory6_pair' for f in result.get('facts',[])):
        lines.append('Inventory figures above are the first displayed category, not totals across categories; see the complete comparison table and snapshot.' if english else 'أرقام المخزون أعلاه تخص أول فئة معروضة وليست إجماليات الفئات؛ راجع جدول المقارنة واللقطة.')
    translations={'recorded':'حقائق مسجّلة','recorded + heuristic estimates':'سجلات وتقديرات تخطيطية تقريبية',
        'model forecast':'توقعات نموذج مقيّم، بنطاقات غير معايرة','experimental research':'بحث تجريبي غير موثوق لاتخاذ قرارات'}
    if classes:lines.append(('Evidence type: ' if english else 'نوع الأدلة: ')+', '.join(c if english else translations.get(c,c) for c in classes)+'.')
    if state in ('provider_error','partial') and code:
        lines.append(t('a9_error',lang,code=code))
    if state=='budget_exhausted':lines.append(t('a9_limit',lang))
    reasons=result.get('coverage_reasons',[])
    if 'missing_domains' in reasons:lines.append(('Missing requested analysis: ' if english else 'التحليل المطلوب غير المكتمل: ')+', '.join(result.get('missing_operations',[])))
    if 'unverified_intent' in reasons:lines.append('The evidence is verified, but full coverage of this open-ended request is not confirmed.' if english else 'الأدلة موثقة لكن اكتمال تغطية هذا الطلب المفتوح غير مؤكد.')
    if 'privacy_scope_override' in reasons:lines.append(t('a9_privacy',lang))
    if resolved.get('overrides'):lines.append(t('a9_scope',lang))
    tools=[r['meta']['tool'] for r in result.get('reports',[])]
    if any(n.startswith('inventory6_') or n in ('executive_stock','category_risk_sales') for n in tools):lines.append(t('a9_inventory',lang))
    if any(n.startswith(('forecast7_','customer8_churn','customer8_value')) for n in tools):lines.append(t('a9_models',lang))
    if tools:lines.append(t('a9_basis',lang));lines.append(t('a9_verified',lang))
    return '\n\n'.join(lines) or t('a9_clarify',lang)

def answer_language(question,fallback):
    """Question script takes precedence over the dashboard language; IDs/digits don't."""
    if any('\u0600'<=c<='\u06ff' and c.isalpha() for c in question):return 'العربية'
    if re.search('[A-Za-z]',re.sub(r'\b(?:BR|WH)\d+\b','',question,flags=re.I)):return 'English'
    return fallback

def requested_metrics(question,reports,retained=None):
    if retained:return list(retained)
    metrics=metrics_in(question)
    if metrics:return metrics
    # No new intent or context resolution: infer only the evidence's own metric.
    for report in reports:
        meta=report['meta']
        if meta.get('metric') in ('sales','gross_profit','gross_margin_pct','aov','orders','units'):return [meta['metric']]
        if meta['tool'].startswith('profit5_'):return ['gross_profit']
        if meta['tool'] in ('company_overview','two_location_comparison'):return ['sales']
    return []

def _number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)):return None
    if not math.isfinite(value):return None
    return Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def _value(value,metric,lang,difference=False):
    english=lang=='English'
    if metric in ('sales','gross_profit','aov','avg_sales','stock_value'):unit='EGP' if english else 'جنيه'
    elif metric=='gross_margin_pct':unit=('percentage points' if english else 'نقطة مئوية') if difference else '%'
    elif metric=='orders':unit='orders' if english else 'طلب'
    elif metric in ('units','stock_units','forecast_units','recent_actual_units'):unit='units' if english else 'وحدة'
    elif metric=='growth_pct':unit='%' if not difference else ('percentage points' if english else 'نقطة مئوية')
    else:unit=''
    return f'{value:,.2f} {unit}' if metric!='orders' else f'{value:,.0f} {unit}'

def _comparison(report,metric,lang):
    meta=report['meta'];a,b=meta.get('branch_a'),meta.get('branch_b')
    product_pair=meta.get('product_ids',[]) if len(meta.get('product_ids',[]))==2 else []
    category_pair=meta.get('categories',[]) if len(meta.get('categories',[]))==2 and meta.get('tool')=='forecast7_categories' else []
    if product_pair:
        a,b=product_pair;by_id={r.get('product_id'):r for r in report['data']}
        row={'location_a':by_id.get(a,{}).get(metric),'location_b':by_id.get(b,{}).get(metric)}
    elif category_pair:
        a,b=category_pair;by_id={r.get('category'):r for r in report['data']}
        row={'location_a':by_id.get(a,{}).get(metric),'location_b':by_id.get(b,{}).get(metric)}
        a,b=category_name(a,lang),category_name(b,lang)
    else:row=next((r for r in report['data'] if r.get('metric')==metric),None)
    if not a or not b:return None
    if row is None:return None
    left,right=_number(row.get('location_a')),_number(row.get('location_b'))
    if left is None or right is None:return None
    name=t(metric,lang);english=lang=='English'
    noun=('Category' if english else 'فئة') if category_pair else ('Product' if english else 'منتج') if product_pair else ('Location' if english else 'موقع')
    if left==right:
        return (f'{"Products" if product_pair else "Locations"} {a} and {b} have equal {name.lower()} at {_value(left,metric,lang)} each (displayed precision).' if english else
            f'{"المنتجان" if product_pair else "الموقعان"} {a} و{b} متساويان في {name} عند {_value(left,metric,lang)} لكل منهما وفق الدقة المعروضة.')
    winner,loser,high,low=(a,b,left,right) if left>right else (b,a,right,left)
    # Display-only delta of verified cents/percentage values; no KPI redefinition or LLM math.
    delta=comparison_delta(high,low)
    return (f'{noun} {winner} has higher {name.lower()} by {_value(delta,metric,lang,True)}: {_value(high,metric,lang)} versus {_value(low,metric,lang)} for {loser}.' if english else
        f'{noun} {winner} حقق {name} أعلى بـ{_value(delta,metric,lang,True)}، حيث سجل {_value(high,metric,lang)} مقابل {_value(low,metric,lang)} لـ{loser}.')

def comparison_delta(left,right):
    left,right=_number(left),_number(right)
    return abs(left-right) if left is not None and right is not None else None

def failure_explanation(result,lang):
    english=lang=='English'
    if result.get('code')=='warehouse_pair':return 'The approved warehouse tool supports one warehouse or their aggregate, not a two-warehouse comparison.' if english else 'أداة المستودعات المعتمدة تدعم مستودعًا واحدًا أو الإجمالي؛ لا تدعم مقارنة مستودعين.'
    if result.get('code')=='row_limit':return 'Public tool rankings support 1 to 20 rows per request.' if english else 'ترتيبات الأدوات المعلنة تدعم من صف واحد إلى 20 صفًا في الطلب.'
    if result.get('code')=='forecast_metric':return 'The approved forecasts support revenue in EGP or category demand in units, not the requested target metric.' if english else 'التوقعات المعتمدة تدعم الإيراد بالجنيه أو طلب الفئة بالوحدات؛ لا تدعم مؤشر الهدف المطلوب.'
    if result.get('code') in ('forecast_dates','forecast_horizon'):
        origin=result.get('forecast_origin')
        return (f'This service forecasts the next 1, 3 or 6 complete months after source origin {origin}; the requested dates or horizon do not match that window.' if english else
                f'هذه الخدمة تتوقع الشهر التالي أو 3 أو 6 أشهر كاملة بعد أصل البيانات {origin}؛ الأشهر أو الأفق المطلوب لا يطابق هذه النافذة.')
    messages={
        'inventory_warehouse_mapping':('No approved branch-to-warehouse allocation supports this comparison; warehouse balances cannot be attributed to these branches.','لا يوجد توزيع معتمد يربط الفروع بالمستودعات لهذه المقارنة؛ لا يمكن نسبة أرصدة المستودع للفروع.'),
        'inventory_snapshot_unavailable':('The locations have no common completed inventory snapshot under the selected filters.','لا توجد لقطة مخزون شهرية مكتملة مشتركة للموقعين ضمن الفلاتر المحددة.'),
        'inventory_pair_coverage':('Recorded inventory is missing for one or both locations in the requested categories; missing balances are unknown, not zero.','بيانات المخزون المسجّلة مفقودة لأحد الموقعين أو كليهما في الفئات المطلوبة؛ المفقود غير معلوم وليس صفرًا.'),
        'inventory_risk_metric_unavailable':('Recorded risk scores are missing for one or both locations; stock quantities cannot substitute for risk scores.','درجات المخاطر المسجّلة غير متاحة لأحد الموقعين أو كليهما؛ كميات المخزون لا تحل محل درجات المخاطر.'),
        'wrong_tool':('The assistant selected an incompatible tool; no comparison for the requested locations and categories was verified.','اختار المساعد أداة غير متوافقة؛ لم تُوثّق مقارنة للمواقع والفئات المطلوبة.'),
        'scope_mismatch':('Returned evidence does not match the requested locations, dates or metric; it was withheld.','الأدلة المسترجعة لا تطابق المواقع أو التواريخ أو المؤشر المطلوب؛ تم حجبها.'),
        'tool_execution_failed':('The comparison tool failed to return valid evidence; this is not a missing user parameter.','تعذّر تنفيذ أداة المقارنة بأدلة صالحة؛ لا يرجع ذلك إلى معلومة ناقصة من المستخدم.')}
    failures=result.get('tool_failures',[])
    if failures and failures[0]['reason'] in messages:return messages[failures[0]['reason']][0 if english else 1]
    if result.get('code')=='no_compatible_tool':return 'No approved tool supports the requested metric and aggregation.' if english else 'لا توجد أداة معتمدة تدعم المؤشر ومستوى التجميع المطلوبين.'
    if result.get('answer_state')=='provider_error':return 'Groq could not complete the request; no comparison was verified.' if english else 'تعذّر إكمال الطلب لدى Groq؛ لم تُوثّق مقارنة.'
    if result.get('code')=='no_evidence':return 'The request scope is resolved, but the assistant returned no verified tool evidence.' if english else 'تم تحديد نطاق الطلب، لكن المساعد لم يُرجع أدلة موثقة من الأدوات.'
    return None

def forecast_summary(result,lang):
    reports=[r for r in result.get('reports',[]) if r['meta']['tool'] in ('forecast7_values','forecast7_accuracy')]
    if not reports:return None
    english=lang=='English';sentences=[]
    unavailable=next((r for r in reports if r['meta'].get('state')=='unavailable'),None)
    if unavailable and not any(r['data'] and r['meta'].get('state')!='unavailable' for r in reports):
        reason=unavailable['meta'].get('reason')
        reasons={
            'f7_missing':('Historical observations contain missing months.','المشاهدات التاريخية تتضمن أشهرًا مفقودة.'),
            'f7_insufficient':('The history is shorter than the approved minimum training history.','السجل أقصر من الحد الأدنى المعتمد لتاريخ التدريب.'),
            'f7_zero':('The training history has no positive target observations.','لا توجد مشاهدات موجبة للهدف في تاريخ التدريب.')}
        text=reasons.get(reason,('The forecasting service reported unavailable results.','أبلغت خدمة التوقع أن النتائج غير متاحة.'))[0 if english else 1]
        return ('Forecast unavailable: ' if english else 'التوقع غير متاح: ')+text
    values=next((r for r in reports if r['meta']['tool']=='forecast7_values' and r['meta'].get('state')!='unavailable'),None)
    if values:
        metric='sales' if values['meta'].get('unit')=='EGP' else 'units'
        rows=[row for row in values['data'] if row.get('month') and _number(row.get('central')) is not None]
        wanted=result.get('resolved',{}).get('forecast_months',[])
        if wanted:rows=[row for row in rows if row['month'] in wanted]
        items=[f"{row['month']}: {_value(_number(row['central']),metric,lang)}" for row in rows]
        if items:sentences.append(('Revenue forecast — ' if english and metric=='sales' else 'Unit demand forecast — ' if english else 'توقع الإيراد — ' if metric=='sales' else 'توقع الطلب بالوحدات — ')+('؛ ' if not english else '; ').join(items)+'.')
    accuracy=next((r for r in reports if r['meta']['tool']=='forecast7_accuracy' and r['meta'].get('state')!='unavailable'),None)
    if accuracy:
        meta=accuracy['meta'];model=_number(meta.get('test_wape_pct'));baseline=_number(meta.get('baseline_test_wape_pct'))
        if model is not None and baseline is not None:
            sentences.append((f"Historical test WAPE: {meta.get('model')} {model:,.2f}% versus baseline {meta.get('baseline')} {baseline:,.2f}% ({meta.get('test_start')} to {meta.get('test_end')}, horizon {meta.get('horizon')} months, n={meta.get('test_observations')})." if english else
                f"WAPE في الاختبار التاريخي: {meta.get('model')} {model:,.2f}% مقابل خط الأساس {meta.get('baseline')} {baseline:,.2f}% (من {meta.get('test_start')} إلى {meta.get('test_end')}، أفق {meta.get('horizon')} أشهر، عدد المشاهدات {meta.get('test_observations')})."))
    return ' '.join(sentences) or None

def risk_comparison(result,lang):
    """Describe predicates over verified category score cells; no new risk KPI/model."""
    if 'recorded_risk' not in result.get('resolved',{}).get('request',{}).get('metrics',[]):return None
    report=next((r for r in result.get('reports',[]) if r['meta']['tool']=='inventory6_pair' and r['data']),None)
    if not report:return None
    rows=[]
    for row in report['data']:
        values=[row.get(k) for k in ('recorded_risk_a','recorded_risk_b')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):continue
        a,b=[Decimal(str(v)).quantize(Decimal('.001'),rounding=ROUND_HALF_UP) for v in values]
        rows.append((row['category'],a,b))
    if not rows:return None
    meta=report['meta'];a,b=meta['branch_a'],meta['branch_b'];english=lang=='English'
    left=sum(x>y for _,x,y in rows);right=sum(y>x for _,x,y in rows);ties=len(rows)-left-right
    prefix=('Among the returned categories' if meta.get('truncated') or meta.get('partial_coverage') else 'Across the compared categories')
    text=(f'{prefix}, {a} has the higher recorded risk score in {left}, {b} in {right}, and {ties} are tied (snapshot {meta.get("snapshot")}).' if english else
          f'ضمن الفئات المعروضة، {a} أعلى في درجة المخاطر المسجّلة في {left} فئات، و{b} في {right}، والتساوي في {ties} (لقطة {meta.get("snapshot")}).')
    category,x,y=max(rows,key=lambda row:abs(row[1]-row[2]));category=category_name(category,lang)
    example=(f'For example, {category}: {a} {x:.3f} versus {b} {y:.3f}.' if english else f'مثال: {category}، {a} سجّل {x:.3f} مقابل {y:.3f} لـ{b}.')
    return text+' '+example

def _finding_label(entity,lang):
    if entity in TEXT:return t(entity,lang)
    text=category_name(str(entity),lang)
    return ltr(re.sub(r'([\\`*_<>\[\]])',r'\\\1',text),lang)

def _finding_value(cell,lang):
    metric=cell['metric'];value=_number(cell['value'])
    if metric in ('c8_customers','c8_orders','c8_registered','c8_identified','c8_active','c8_cohort_size'):
        return f'{value:,.0f}'
    return _value(value,metric,lang).strip()

def _customer_facts(result,lang):
    request=result.get('resolved',{}).get('request',{})
    reports=[r for r in result.get('reports',[]) if r['meta']['tool'].startswith('customer8_') and r['meta']['tool'] not in ('customer8_churn','customer8_value')]
    cells=observations(reports,request)
    if not cells:return None
    metric=cells[0]['metric'];group=[c for c in cells if c['metric']==metric and c['period']==cells[0]['period']]
    name=t(metric,lang) if metric in TEXT else metric.replace('_',' ')
    values=[(_finding_label(c['entity'],lang)+': ' if c['entity'] is not None else '')+_finding_value(c,lang) for c in group[:5]]
    qualifier=(' (shown groups)' if lang=='English' else ' (المجموعات المعروضة)') if len(group)>5 else ''
    return ('Verified facts — ' if lang=='English' else 'حقائق موثقة — ')+name+qualifier+': '+('; ' if lang=='English' else '؛ ').join(values)+'.'

def assemble(result,lang,question=''):
    """Facts first; optional comparisons are predicates over public service cells."""
    lang=answer_language(question,lang)
    text=_direct_answer(result,lang,question)
    if result.get('answer_state')=='blocked' or 'outside_source' in result.get('coverage_reasons',[]):return text
    request=dict(result.get('resolved',{}).get('request',{}))
    if request.get('answer_shape')=='series' or set(request.get('answer_components',[]))&{'ranking_membership','group_extreme','inference_limit','forecast_evaluation','forecast_uncertainty','forecast_reliability','customer_reliability','noncausal_description'}:return text
    asked=request.get('answer_components',components(question))
    if not set(asked)&{'description','investigation'}:return text
    pair=comparison(observations(result.get('reports',[]),request))
    if not pair:return text
    ascending=request.get('parameters',{}).get('ascending',False)
    high=pair['low'] if ascending else pair['high'];name=t(high['metric'],lang) if high['metric'] in TEXT else high['metric'].replace('_',' ')
    if pair['tied']:
        note='Descriptive observation: the comparable values in this group are equal; this measure gives no unique review priority within this group.' if lang=='English' else 'ملاحظة وصفية: القيم المتوافقة داخل هذه المجموعة متساوية؛ لا يحدد هذا المؤشر أولوية مراجعة منفردة داخل المجموعة.'
    else:
        entity=_finding_label(high['entity'],lang)
        note=(f'Descriptive observation: {entity} has the {"lowest" if ascending else "highest"} shown {name}'+(' estimate' if high['estimated'] else '') if lang=='English' else f'ملاحظة وصفية: {entity} {"أقل" if ascending else "أعلى"} في {name} بين القيم المعروضة'+(' التقديرية' if high['estimated'] else ''))
        note+=(' within the same comparison group' if lang=='English' else ' ضمن مجموعة المقارنة المتوافقة نفسها')
        note+=('; possible investigation priority by this measure only, not evidence of cause or future outcomes.' if lang=='English' else '؛ أولوية فحص محتملة وفق هذا المؤشر فقط، وليست دليلًا على السبب أو النتائج المستقبلية.') if 'investigation' in asked else ('.' if lang=='English' else '.')
    return text+'\n\n'+note

def _typed_answer(result,lang):
    reports=result.get('reports',[]);request=result.get('resolved',{}).get('request',{});asked=set(request.get('answer_components',[]));english=lang=='English'
    if request.get('answer_shape')=='series':
        from services.assistant_shape import series_rows,extrema
        rows,issues=series_rows(reports,request);peaks,_=extrema(reports,request)
        parts=[]
        for item in peaks:
            label=('Highest' if item['direction']=='highest' else 'Lowest') if english else ('أعلى' if item['direction']=='highest' else 'أقل')
            parts.append(label+' · '+t(item['metric'],lang)+': '+', '.join(item['periods'])+' ('+_value(item['value'],item['metric'],lang).strip()+')')
        values=[period+': '+', '.join(t(m,lang)+' '+_value(row[m],m,lang).strip() for m in request['metrics'] if _number(row.get(m)) is not None) for period,row in rows]
        if not values:return None
        prefix=('Verified monthly series' if request.get('parameters',{}).get('grain','monthly')=='monthly' else 'Verified series') if english else 'السلسلة الزمنية الموثقة'
        if issues:prefix=('Available periods only; requested coverage is incomplete' if english else 'الفترات المتاحة فقط؛ تغطية الطلب غير مكتملة')
        # The extrema and every returned period are essential to this answer.
        return ('; ' if english else '؛ ').join(parts)+('.\n\n' if parts else '')+prefix+':\n\n'+'\n'.join('- '+v for v in values)
    if 'ranking_membership' in asked and (ranks:=ranked_sets(reports,request)):
        sets=[set(r['ids']) for r in ranks];shared=set.intersection(*sets);same=all(s==sets[0] for s in sets)
        labels=' / '.join(t(r['metric'],lang) if r['metric'] in TEXT else r['metric'] for r in ranks)
        text=(f'The returned {labels} product sets are {"identical" if same else "different"}, with {len(shared)} shared product IDs.' if english else f'قوائم المنتجات المسترجعة حسب {labels} {"متطابقة" if same else "مختلفة"}، وتشترك في {len(shared)} رموز منتجات.')
        return text+(' Different ranking metrics do not necessarily select the same products.' if english else ' اختلاف مؤشر الترتيب لا يضمن اختيار المنتجات نفسها.')
    if len(request.get('ranking_metrics',[]))==1:
        report=next((r for r in reports if complete_requested_selection(r,result.get('resolved',{}))),None)
        if report:
            metric=request['ranking_metrics'][0];rows=report['data'];kind=request.get('aggregation')
            key={'product':'product_id','category':'category','locations':'branch_id'}[kind]
            label=t(metric,lang) if metric in TEXT else metric
            items=[_finding_label(row[key],lang)+' ('+_value(row[metric],metric,lang).strip()+')' for row in rows]
            descending=not request.get('parameters',{}).get('ascending',False)
            text=((f'{"Top" if descending else "Bottom"} {len(rows)} by {label}: ' if english else f'{"أعلى" if descending else "أقل"} {len(rows)} حسب {label}: '))+'\n\n'+'\n'.join(f'{i}. '+item for i,item in enumerate(items,1))
            if len(rows)<request['parameters']['limit']:text+=('\nOnly these eligible entities are recorded.' if english else '\nهذه فقط الكيانات المؤهلة المسجّلة.')
            return text
        # Incomplete rankings still retain all verified available identities;
        # never pretend their first row answers a multi-item question.
        metric=request['ranking_metrics'][0];key={'product':'product_id','category':'category','locations':'branch_id'}.get(request.get('aggregation'))
        for report in reports:
            if report['meta'].get('metric')!=metric or not key:continue
            seen=set();items=[]
            for row in report['data']:
                identity=row.get(key)
                if identity is None or identity in seen or _number(row.get(metric)) is None:continue
                seen.add(identity);items.append(_finding_label(identity,lang)+' ('+_value(row[metric],metric,lang).strip()+')')
            if items:return ('Available verified ranking; requested coverage is incomplete:' if english else 'الترتيب الموثق المتاح؛ تغطية الطلب غير مكتملة:')+'\n\n'+'\n'.join(f'{i}. '+v for i,v in enumerate(items,1))
    if 'customer_reliability' in asked and (evaluation:=customer_evaluation(reports)):
        row=evaluation['row'];unreliable=evaluation['meta'].get('state')=='c8_unreliable'
        lead=('No—this research failed the approved reliability gate; it is unsuitable for individual decisions.' if unreliable else 'Only aggregate research evaluation is published; individual decisions are not validated here.') if english else ('لا، لم يجتز هذا البحث بوابة الموثوقية المعتمدة ولا يصلح لقرارات فردية.' if unreliable else 'المتاح تقييم بحثي مجمّع فقط؛ لا توجد مصادقة على قرارات فردية هنا.')
        values=f"ROC-AUC {row['c8_roc_auc']:.3f}, AP {row['c8_average_precision']:.3f}, Brier {row['c8_brier']:.3f}, ECE {row['c8_ece']:.3f}"
        repeat=next((row.get('c8_repeat_rate') for r in reports if r['meta'].get('tool')=='customer8_summary' for row in r['data'] if _number(row.get('c8_repeat_rate')) is not None),None)
        prefix=('Repeat purchase rate: ' if english else 'نسبة الشراء المتكرر: ')+f'{repeat:.2f}%. ' if repeat is not None and 'c8_repeat_rate' in request.get('metrics',[]) else ''
        return prefix+lead.rstrip('.')+'; '+(('published pooled evaluation: ' if english else 'التقييم المجمّع المنشور: ')+values+f" (n={row['c8_samples']:,.0f}).")
    if asked&{'forecast_evaluation','forecast_uncertainty','forecast_reliability'} and not result.get('resolved',{}).get('forecast_months') and (m:=forecast_evaluation(reports)):
        lead=('No—forecasts are estimates, not certain outcomes. ' if english else 'لا، التوقعات تقديرية وليست نتائج مؤكدة. ') if asked&{'forecast_reliability','forecast_uncertainty'} else ''
        text=(f"Historical test WAPE: {m['model']} {m['test_wape_pct']:.2f}% versus {m['baseline']} {m['baseline_test_wape_pct']:.2f}% (n={m['test_observations']:,.0f}, horizon {m['horizon']})." if english else f"WAPE للاختبار التاريخي: {m['model']} {m['test_wape_pct']:.2f}% مقابل {m['baseline']} {m['baseline_test_wape_pct']:.2f}% (عدد المشاهدات {m['test_observations']:,.0f}، الأفق {m['horizon']}).")
        return lead+text
    if 'group_extreme' in asked:
        cells=observations(reports,request);pair=comparison(cells)
        if pair and 'group_extreme' in typed_support(reports,request,cells,pair):
            smallest=any(w in str(request.get('extreme_direction','')) for w in ('smallest','low'))
            cell=pair['low'] if smallest else pair['high'];name=t(cell['metric'],lang) if cell['metric'] in TEXT else cell['metric']
            text=(f"{'Smallest' if smallest else 'Largest'} shown group: {_finding_label(cell['entity'],lang)}, {name} {_finding_value(cell,lang)}." if english else f"{'أصغر' if smallest else 'أكبر'} مجموعة معروضة: {_finding_label(cell['entity'],lang)}، {name} {_finding_value(cell,lang)}.")
            if pair['tied']:text+=(' Comparable groups tie on this measure.' if english else ' توجد مجموعات متساوية على هذا المؤشر.')
            if 'inference_limit' in asked:text+=(' Size alone does not establish churn probability or individual risk.' if english else ' العدد وحده لا يثبت احتمال فقدان العملاء أو مخاطر فردية.')
            return text
    if 'noncausal_description' in asked and not result.get('resolved',{}).get('pair'):
        cells=observations(reports,request);items=[]
        for metric in request.get('metrics',[]):
            pair=comparison([c for c in cells if c['metric']==metric])
            if not pair:continue
            cell=pair['high'];field=cell.get('measure',metric)
            label=t(field,lang) if field in TEXT else t(metric,lang) if metric in TEXT else metric
            items.append(_finding_label(cell['entity'],lang)+' · '+label+' '+_finding_value(cell,lang))
        if items:return ('Among the returned comparable groups, highest observed values: ' if english else 'ضمن المجموعات المعروضة القابلة للمقارنة، أعلى القيم المرصودة: ')+('; ' if english else '؛ ').join(items[:2])+('. This is descriptive evidence, not proof of causes.' if english else '. هذه مشاهدات وصفية وليست إثباتًا للأسباب.')
    # Plain multirow facts follow, never precede, requested analytical obligations.
    if request.get('aggregation') in ('product','category','locations') and not request.get('ranking_metrics'):
        key={'product':'product_id','category':'category','locations':'branch_id'}[request['aggregation']]
        for report in reports:
            if len(report['data'])<2 or any(key not in row for row in report['data']):continue
            items=[]
            for row in report['data']:
                values=[]
                for metric in request.get('metrics',[]):
                    field='max_recorded_risk' if metric=='recorded_risk' and metric not in row and 'max_recorded_risk' in row else metric
                    if _number(row.get(field)) is not None:values.append(t(field,lang)+' '+_value(row[field],metric,lang).strip())
                if values:items.append(_finding_label(row[key],lang)+': '+', '.join(values))
            if items:return ('Verified returned results:' if english else 'النتائج الموثقة المعروضة:')+'\n\n'+'\n'.join('- '+v for v in items)
    return None

def _direct_answer(result,lang,question=''):
    """One or two direct sentences, using only validated local report cells."""
    lang=answer_language(question,lang);state=result.get('answer_state','partial')
    if state=='blocked':
        if result.get('code')=='privacy':return 'I cannot provide private customer identifiers, contacts or individual predictions; approved aggregate customer analysis is available.' if lang=='English' else 'لا يمكن عرض أسماء العملاء أو بيانات الاتصال أو التنبؤات الفردية؛ يمكنني تقديم تحليل عملاء مجمّع معتمد.'
        return 'This request is restricted; only aggregate read-only analytics are available.' if lang=='English' else 'هذا الطلب مقيّد؛ المتاح تحليلات مجمعة للقراءة فقط.'
    if not result.get('reports') and (reason:=failure_explanation(result,lang)):return reason
    if typed:=_typed_answer(result,lang):return typed
    forecast_reports=[r for r in result.get('reports',[]) if r['meta']['tool'].startswith('forecast7_')]
    if (forecast_reports and (len(forecast_reports)==len(result.get('reports',[])) or any(r['data'] and r['meta'].get('state')!='unavailable' for r in forecast_reports))):
        if summary:=forecast_summary(result,lang):return summary
    if result.get('reports') and all(not r['data'] for r in result['reports']):
        roles={CAPABILITIES[r['meta']['tool']].role for r in result['reports']}
        if roles<={'screening','cover','replenishment','decline'}:
            return 'The approved attention screen returned no matching rows under these filters; this does not establish zero business activity.' if lang=='English' else 'لم يُرجع فحص الانتباه المعتمد صفوفًا مطابقة لهذه الفلاتر؛ لا يثبت ذلك انعدام النشاط التجاري.'
    research=[r for r in result.get('reports',[]) if r['meta']['tool'] in ('customer8_churn','customer8_value')]
    if research and len(research)==len(result.get('reports',[])) and all(not r['data'] for r in research):
        return 'The customer-model service reported unavailable research; no verified model results were returned.' if lang=='English' else 'أبلغت خدمة نماذج العملاء أن البحث غير متاح؛ لم تُرجع نتائج نموذج موثقة.'
    if research and len(research)==len(result.get('reports',[])):
        return 'This customer-model research is unreliable for business decisions; measured aggregate evidence is available below.' if lang=='English' else 'بحث نموذج العملاء غير موثوق لاتخاذ قرارات تجارية؛ الأدلة المجمّعة المقاسة متاحة أدناه.'
    usable=observations(result.get('reports',[]),result.get('resolved',{}).get('request',{}))
    if 'outside_source' in result.get('coverage_reasons',[]) or (state=='unavailable' and not usable):return 'A verified answer is unavailable from these data.' if lang=='English' else 'لا تتوفر إجابة موثقة عن هذا السؤال من البيانات المتاحة.'
    if state in ('unsupported','clarification') and not usable:return detailed_results(result,lang)
    customer_summary=_customer_facts(result,lang)
    if customer_summary and all(r['meta']['tool'].startswith('customer8_') for r in result.get('reports',[])):return customer_summary
    reports=result.get('reports',[]);sentences=[]
    risk=risk_comparison(result,lang)
    if risk:return risk
    for metric in requested_metrics(question,reports,result.get('resolved',{}).get('request',{}).get('metrics')):
        period=next((r for r in reports if r['meta']['tool']=='executive_comparison'),None)
        if period:
            row=next((r for r in period['data'] if r.get('metric')==('sales' if metric=='growth_pct' else metric)),{})
            current,previous,pct=(_number(row.get(k)) for k in ('current','previous','percentage_change'))
            if current is not None and previous is not None and pct is not None:
                base='sales' if metric=='growth_pct' else metric;name=t(base,lang)
                sentences.append(f'{name}: {_value(current,base,lang)} versus {_value(previous,base,lang)} in the previous period; change {pct:,.2f}%.' if lang=='English' else f'{name}: {_value(current,base,lang)} مقابل {_value(previous,base,lang)} في الفترة السابقة؛ التغير {pct:,.2f}%.')
                continue
        comparison=next((text for r in reports if (text:=_comparison(r,metric,lang))),None)
        if comparison:sentences.append(comparison);continue
        # A missing pair must never become an unrelated company total or one-sided answer.
        if result.get('resolved',{}).get('pair') or any(r['meta'].get('branch_a') for r in reports):continue
        for report in reports:
            if not report['data']:continue
            row=report['data'][0];value=_number(row.get(metric))
            displayed_metric=metric
            if value is None and metric=='recorded_risk' and 'max_recorded_risk' in row:
                value=_number(row['max_recorded_risk']);displayed_metric='max_recorded_risk'
            if value is None:continue
            entity=row.get('product_id') or row.get('branch_id') or row.get('category') or row.get('period') or row.get('month') or row.get('calendar_month')
            if len(report['data'])>1 and not entity:continue
            entity=category_name(str(entity),lang) if entity else ''
            title=t(displayed_metric,lang)
            sentences.append(f'{entity+" · " if entity else ""}{title}: {_value(value,metric,lang)}.')
            break
    if sentences:
        if customer_summary and len(sentences)<2:sentences.append(customer_summary)
        inventory=next((r for r in reports if r['meta'].get('tool','').startswith('inventory6_') and r['data']),None)
        if inventory and len(sentences)<2:
            snapshot=inventory['meta'].get('snapshot')
            sentences.append(('Inventory is shown by category at recorded snapshot '+str(snapshot)+'.') if lang=='English' else 'المخزون معروض حسب الفئة في اللقطة المسجّلة '+str(snapshot)+'.')
        return ' '.join(sentences)
    for report in reports:
        rows=report.get('data',[]);meta=report['meta']
        forecast=[r for r in rows if r.get('month') and _number(r.get('central')) is not None]
        if forecast:
            first,last=forecast[0],forecast[-1];metric='sales' if meta.get('unit')=='EGP' else 'units'
            a=_value(_number(first['central']),metric,lang);b=_value(_number(last['central']),metric,lang)
            if len(forecast)==1:return f"Forecast for {first['month']}: {a}." if lang=='English' else f"التوقع لشهر {first['month']}: {a}."
            return (f"Forecast: {a} in {first['month']}, reaching {b} in {last['month']}." if lang=='English' else f"التوقع: {a} في {first['month']}، ويصل إلى {b} في {last['month']}.")
        if meta.get('tool','').startswith('inventory6_') and rows:
            return ('Recorded inventory is shown by category for snapshot '+str(meta.get('snapshot'))+'.' if lang=='English' else 'المخزون المسجّل معروض حسب الفئة للقطة '+str(meta.get('snapshot'))+'.')
        if meta.get('tool') in ('customer8_churn','customer8_value'):
            return 'This model research is unreliable for business decisions; its measured results are available below.' if lang=='English' else 'بحث النموذج غير موثوق لاتخاذ قرارات تجارية؛ نتائج تقييمه متاحة أدناه.'
    if not reports:
        return ('The request could not be completed; no verified answer is available.' if lang=='English' else 'تعذّر إكمال الطلب؛ لا تتوفر إجابة موثقة.')
    return ('The exact answer is not available in the verified evidence; review Detailed results.' if lang=='English' else 'الإجابة المحددة غير متاحة في الأدلة الموثقة؛ راجع النتائج التفصيلية.')

def critical_warnings(result,lang):
    """Material qualification stays outside collapsed provenance, without extra KPIs."""
    warnings=[];tools=[r['meta']['tool'] for r in result.get('reports',[])]
    from services.assistant_limits import explanations
    if result.get('reports') or result.get('answer_state')=='clarification':warnings.extend(explanations(result.get('capability_limitations',[]),lang))
    coverage=result.get('resolved',{}).get('calendar_coverage')
    if coverage and not coverage['complete']:
        available=(f"{coverage['available_start']} → {coverage['available_end']}" if coverage['available_start'] else ('none' if lang=='English' else 'لا توجد'))
        warnings.append(f"The full calendar year was requested; available historical coverage: {available}. These results are not a complete annual total." if lang=='English' else f'المطلوب سنة تقويمية كاملة؛ التغطية التاريخية المتاحة: {available}. النتائج ليست إجمالي سنة مكتملة.')
    if 'incomplete_source_window' in result.get('coverage_reasons',[]) and not coverage:
        resolved=result.get('resolved',{});bounds=f"{resolved.get('source_start')} → {resolved.get('source_end')}"
        warnings.append(f'The requested financial window extends beyond recorded source coverage ({bounds}); available observations are not a complete period total.' if lang=='English' else f'الفترة المالية المطلوبة تتجاوز تغطية المصدر المسجّلة ({bounds})؛ المشاهدات المتاحة ليست إجمالي الفترة المكتملة.')
    missing=result.get('missing_answer_components',[])
    if 'ranking_membership' in missing:warnings.append('Both requested ranking sets are not verified; no membership conclusion is asserted.' if lang=='English' else 'لم يتم التحقق من قائمتي الترتيب المطلوبتين؛ لا يمكن تأكيد تطابق المنتجات.')
    if 'group_extreme' in missing:warnings.append('Complete comparable group values are unavailable; no overall largest/smallest group is asserted.' if lang=='English' else 'قيم المجموعات الكاملة القابلة للمقارنة غير متاحة؛ لا يمكن تأكيد أكبر أو أصغر مجموعة إجمالًا.')
    if set(missing)&{'forecast_evaluation','forecast_uncertainty','customer_reliability'}:warnings.append('Some requested evaluation or uncertainty evidence is missing; available measurements are retained.' if lang=='English' else 'بعض أدلة التقييم أو عدم اليقين المطلوبة مفقودة؛ تُعرض القياسات المتاحة فقط.')
    if 'truncated_rows' in result.get('coverage_reasons',[]):warnings.append('Only a bounded subset of the requested population was returned.' if lang=='English' else 'المسترجع جزء محدود من المجموعة المطلوبة؛ لا يغطي النطاق كاملًا.')
    if result.get('shape_issues'):warnings.append('Verified results do not cover every requested entity, period or measure; shown extrema describe available periods only.' if lang=='English' else 'النتائج الموثقة لا تغطي كل الكيانات أو الفترات أو المؤشرات المطلوبة؛ القيم القصوى المعروضة تخص الفترات المتاحة فقط.')
    if 'facts' in missing:warnings.append('Some requested group values are missing or suppressed; they are not zero.' if lang=='English' else 'بعض قيم المجموعات المطلوبة مفقودة أو محجوبة؛ ليست صفرًا.')
    if 'cause' in missing:warnings.append('Unsupported conclusion: aggregate observations do not establish why the outcome occurred.' if lang=='English' else 'استنتاج غير مدعوم: المشاهدات المجمعة لا تثبت سبب حدوث النتيجة.')
    if 'predictive_conclusion' in missing:warnings.append('Unsupported conclusion: these observations do not establish guaranteed outcomes or customer churn probabilities.' if lang=='English' else 'استنتاج غير مدعوم: هذه المشاهدات لا تثبت نتائج مضمونة أو احتمالات فقدان العملاء.')
    if set(missing)&{'description','investigation'}:warnings.append('The requested interpretation lacks sufficient comparable verified evidence; available facts are retained.' if lang=='English' else 'لا تتوفر أدلة موثقة قابلة للمقارنة تكفي للتفسير المطلوب؛ الحقائق المتاحة محفوظة.')
    if result.get('unavailable_operations') and any(r['data'] and r['meta'].get('state')!='unavailable' for r in result.get('reports',[])):
        warnings.append('Part of the requested evidence is unavailable; the supported results are shown.' if lang=='English' else 'جزء من الأدلة المطلوبة غير متاح؛ تُعرض النتائج المدعومة المتاحة.')
    if 'unsupported_parameters' in result.get('coverage_reasons',[]):warnings.append('Requested numeric predicates were not applied; these are results under the approved default filters.' if lang=='English' else 'لم تُطبق الشروط الرقمية المطلوبة؛ هذه نتائج الفلاتر الافتراضية المعتمدة فقط.')
    if 'incomplete_metric_coverage' in result.get('coverage_reasons',[]):warnings.append('Some requested metric cells are missing; available verified values are retained and unknown values are not zero.' if lang=='English' else 'بعض خلايا المؤشرات المطلوبة مفقودة؛ القيم الموثقة المتاحة محفوظة، والمفقود ليس صفرًا.')
    reasons={
        'inventory_warehouse_mapping':('Warehouse inventory cannot be attributed to these branches: no approved branch-to-warehouse allocation is available. Select an explicit warehouse for a separate warehouse view.','لا يمكن نسبة مخزون المستودع لهذه الفروع: لا يوجد توزيع معتمد بين الفروع والمستودعات. حدد مستودعًا صراحةً لعرض مخزونه بشكل مستقل.'),
        'inventory_snapshot_unavailable':('No common completed inventory snapshot is available for both locations under these filters. Sales still use the requested transaction dates.','لا توجد لقطة مخزون شهرية مكتملة مشتركة للموقعين ضمن هذه الفلاتر. تظل المبيعات محسوبة بتواريخ المعاملات المطلوبة.'),
        'inventory_pair_coverage':('Recorded inventory does not cover both locations in every requested category. Missing balances are unknown, not zero.','المخزون المسجّل لا يغطي الموقعين في كل الفئات المطلوبة. الأرصدة المفقودة غير معلومة وليست صفرًا.')}
    for failure in result.get('tool_failures',[]):
        if failure['reason']=='wrong_tool':
            warnings.append('A proposed tool was rejected for incompatible scope; unrelated evidence is not shown.' if lang=='English' else 'رُفضت أداة مقترحة لعدم توافق نطاقها؛ لا تُعرض أدلة غير مرتبطة.')
            continue
        pair=reasons.get(failure['reason'])
        if pair:warnings.append(pair[0 if lang=='English' else 1])
        else:warnings.append('One requested analysis has no verified evidence; available results are retained.' if lang=='English' else 'لا تتوفر أدلة موثقة لأحد التحليلات المطلوبة؛ النتائج المتاحة محفوظة.')
    if result.get('rejected_evidence'):
        warnings.append('Evidence outside the requested scope was rejected. No unrelated figures are shown.' if lang=='English' else 'تم رفض أدلة لا تطابق نطاق السؤال؛ لا تُعرض أرقام تخص نطاقًا آخر.')
    if result.get('missing_metrics'):
        names=', '.join(t(m,lang) if m in TEXT else m.replace('_',' ') for m in result['missing_metrics'])
        warnings.append(('Missing verified metrics: ' if lang=='English' else 'مؤشرات موثقة غير متاحة: ')+names)
    if 'unsupported_aggregation' in result.get('coverage_reasons',[]):
        warnings.append('No verified location-wide comparison is available; stock evidence is recorded by category and location.' if lang=='English' else 'لا تتوفر مقارنة موثقة لإجمالي الموقع؛ أدلة المخزون مسجّلة حسب الفئة والموقع.')
    if 'recorded_risk' in result.get('resolved',{}).get('request',{}).get('metrics',[]) and result.get('reports'):
        warnings.append('Recorded risk scores describe categories, not stockout probabilities or causes.' if lang=='English' else 'درجات المخاطر مسجّلة للفئات؛ ليست احتمالات نفاد ولا تفسّر الأسباب.')
    if 'unsupported_risk_metric' in result.get('coverage_reasons',[]):
        warnings.append('The requested predicted/probability risk metric is unsupported; only recorded scores are available.' if lang=='English' else 'مؤشر المخاطر التنبؤي أو الاحتمالي المطلوب غير مدعوم؛ المتاح درجات مسجّلة فقط.')
    if 'incomplete_category_coverage' in result.get('coverage_reasons',[]):
        warnings.append('Some categories have missing scores for a location and were excluded. The comparison covers only categories with scores for both locations.' if lang=='English' else 'استُبعدت فئات تنقصها درجات لأحد الموقعين؛ المقارنة تخص فقط الفئات التي لها درجات للموقعين.')
    if any(n in ('customer8_churn','customer8_value') for n in tools):
        warnings.append('Customer model research is unreliable and unsuitable for individual decisions.' if lang=='English' else 'أبحاث نماذج العملاء غير موثوقة ولا تصلح لاتخاذ قرارات فردية.')
        if 'customer_reliability' in result.get('resolved',{}).get('request',{}).get('answer_components',[]):warnings.append('Pooled cohort observations may overlap; sample counts are not independent unique customers.' if lang=='English' else 'قد تتداخل مشاهدات الأفواج المجمّعة؛ حجم العينة ليس عدد عملاء مستقلين وفريدين.')
    if any(n.startswith('forecast7_') for n in tools):
        warnings.append('Forecasts are estimates; uncertainty ranges are uncalibrated.' if lang=='English' else 'التوقعات تقديرية ونطاقات عدم اليقين غير معايرة.')
        warnings.append('WAPE measures historical error; lower is better. It is not guaranteed future accuracy.' if lang=='English' else 'WAPE مقياس للخطأ التاريخي؛ الأقل أفضل. لا يمثل دقة مستقبلية مضمونة.')
        if any(r['meta'].get('state')=='experimental' or any(row.get('state')=='experimental' for row in r['data']) for r in result.get('reports',[]) if r['meta']['tool'].startswith('forecast7_')):
            warnings.append('The service marks this forecast experimental: its reliability gate was not satisfied.' if lang=='English' else 'تُصنّف الخدمة هذا التوقع تجريبيًا: لم تتحقق بوابة الموثوقية المعتمدة.')
        if 'category_evaluation_scope' in result.get('coverage_reasons',[]):
            warnings.append('Detailed model/baseline evaluation supports one category target at a time; company revenue WAPE is not category demand accuracy.' if lang=='English' else 'تقييم النموذج وخط الأساس التفصيلي يدعم فئة واحدة في كل طلب؛ WAPE إيراد الشركة ليس دقة طلب الفئات.')
        if 'unavailable_category_forecasts' in result.get('coverage_reasons',[]):warnings.append('The service reports some category forecasts unavailable; missing predictions are not zero.' if lang=='English' else 'أبلغت الخدمة أن توقعات بعض الفئات غير متاحة؛ التوقعات المفقودة ليست صفرًا.')
    if 'privacy_scope_override' in result.get('coverage_reasons',[]):
        warnings.append('Customer figures use a fixed company-wide period instead of the requested filters.' if lang=='English' else 'أرقام العملاء تخص فترة ثابتة على مستوى الشركة بدلًا من الفلاتر المطلوبة.')
    return warnings
