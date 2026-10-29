"""Shared bilingual semantic vocabulary. No example questions or business values."""
import re
from services.assistant_capabilities import CAPABILITIES

VOCABULARY={
 'compare':('compare','comparison','versus','vs','قارن','مقارنة'),
 'product':('product','products','منتج','منتجات'),
 'category':('category','categories','فئة','فئات'),
 'location':('branch','branches','location','locations','فرع','فروع','مواقع'),
 'time':('trend','monthly','daily','weekly','yearly','over time','اتجاه','شهري','يومي','أسبوعي','اسبوعي','سنوي','بمرور الوقت'),
 'model':('model','models','نموذج','نماذج'),
 'ranking':('highest','lowest','largest','smallest','biggest','ranking','top','أعلى','اعلى','أقل','اقل','أفضل','أكبر','اكبر','أصغر','اصغر'),
 'screening':('screening','high volume low margin','high-volume low-margin','فحص','حجم مرتفع وهامش منخفض'),
 'leaders':('leaders','leader','المنتجات الرائدة','قادة الربحية'),
 'decline':('declining','decline','انخفاض','تراجع'),
 'period_comparison':('previous period','prior period','الفترة السابقة'),
 'seasonality':('seasonality','seasonal pattern','موسمية','الموسمية'),
 'retention':('retention','cohort','cohorts','احتفاظ','أفواج'),
 'segments':('rfm','segment','segments','segmentation','شرائح','شريحة'),
 'activity':('purchase frequency','purchasing frequency','repeat purchase over time','customer activity','تكرار الشراء','نشاط العملاء'),
 'repeat_summary':('repeat customer rate','repeat purchase rate','more than once','أكتر من مرة','أكثر من مرة','اكثر من مرة'),
 'changes':('segment changes','segment change','segment migration','تغير الشرائح','تغيّر الشرائح'),
 'churn':('churn','roc','فقدان العملاء'),
 'value':('clv','customer revenue','customer value','قيمة العميل','إيراد العملاء'),
 'growth':('categories grow','expected to grow','category growth','نمو الفئات','المتوقع نموها'),
 'warehouse':('warehouse','warehouses','مستودع','مخازن'),
 'transfers':('transfer','transfers','تحويل'),
}

def signals(question):
    from services.assistant_language import ranking_syntax
    q=question.casefold();result=[];spans={}
    for name,aliases in VOCABULARY.items():
        spans[name]=[(m.start(),m.end()) for alias in aliases for m in re.finditer(r'(?<![A-Za-z])'+re.escape(alias)+r'(?![A-Za-z])',q)]
        if spans[name]:result.append(name)
    if 'changes' in result and 'segments' in result and all(any(a<=start and end<=b for a,b in spans['changes']) for start,end in spans['segments']):
        result.remove('segments')
    customer=bool(re.search(r'customers?|عملاء|عميل',q))
    if customer and re.search(r'revenue|spend|إيراد|ايراد',q) and re.search(r'next[- ]year|future|forecast|القادم|القادمة|الجاية|المستقبل',q):
        if 'value' not in result:result.append('value')
    if ranking_syntax(question)['ranked'] and 'ranking' not in result:result.append('ranking')
    return result

def mentions(question,label):
    if not label:return False
    q=question.casefold();prefix='' if label.isascii() else r'(?:وال|ال|و)?'
    return bool(re.search(r'(?<!\w)'+prefix+re.escape(label.casefold())+r'(?!\w)',q))

def entity_ids(question,identifiers):
    """Catalog identity and format validation; no fixture IDs or fixed prefix lengths."""
    question=question.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    identifiers=[str(v) for v in identifiers];known={v.upper() for v in identifiers}
    if not known:return [],[]
    pattern=r'(?<![A-Za-z0-9])(?:'+ '|'.join(re.escape(v) for v in sorted(known,key=len,reverse=True))+r')(?![A-Za-z0-9])'
    matched=list(dict.fromkeys(m.group().upper() for m in re.finditer(pattern,question,re.I)))
    prefixes={re.match(r'[A-Za-z]+',v)[0] for v in known if re.fullmatch(r'[A-Za-z]+\d+',v)}
    candidates=re.findall(r'(?<![A-Za-z0-9])(?:'+ '|'.join(map(re.escape,prefixes))+r')\d+(?![A-Za-z0-9])',question,re.I) if prefixes else []
    return matched,[v for v in candidates if v.upper() not in known]

def semantic_plan(request,resolved,fallback):
    """Refine by capability roles, not a specific example question or entity ID."""
    tags=set(request.get('signals',[]));domains=set(request.get('domains',[]));scope=resolved['scope']
    plan=list(fallback)
    if 'inventory' in domains and 'transfers' in tags and not resolved.get('pair'):
        plan=[item for item in plan if not item[0].startswith('inventory6_')]+[('inventory6_transfers',{})]
    if 'warehouse' in resolved.get('explicit_dimensions',[]) and not plan:
        plan=[('inventory6_warehouse',{})]
    if 'profitability' in domains and 'sales' not in domains and request.get('aggregation')=='time' and request.get('parameters',{}).get('grain','monthly')=='monthly':
        plan=[('profit5_trends',{}) if name=='sales4_trends' else (name,args) for name,args in plan]
    if 'customers' in domains:
        roles=tags&{'retention','segments','activity','changes','churn','value','repeat_summary'}
        if roles:
            plan=[item for item in plan if not item[0].startswith('customer8_')]
            if 'repeat_summary' in roles:roles=(roles-{'repeat_summary'})|{'summary'}
            plan.extend((name,{}) for name,c in CAPABILITIES.items() if c.domain=='customers' and c.role in roles)
    if request.get('forecast') and 'growth' in tags:
        plan=[item for item in plan if not item[0].startswith('forecast7_')]+[('forecast7_growth',{'horizon':resolved['horizon']})]
    if not request.get('forecast') and request.get('aggregation')!='location_pair':
        roles=tags&{'screening','leaders','period_comparison','seasonality','decline'}
        if roles:
            plan=[item for item in plan if item[0].startswith(('inventory6_','customer8_'))]
            plan.extend((name,{}) for name,c in CAPABILITIES.items() if c.role in roles and c.domain in ('sales','profitability'))
    return list({(name,tuple(sorted(args.items()))):(name,args) for name,args in plan}.values())

def advertised_operations(request,resolved,planned,compatible):
    """Offer compatible role alternatives, never arbitrary fallback execution."""
    roles={CAPABILITIES[name].role for name,_ in planned}
    domains={CAPABILITIES[name].domain for name,_ in planned}
    if domains&{'sales','profitability'}:domains|={'sales','profitability'}
    return {name for name,c in CAPABILITIES.items() if compatible(name,resolved) and
        (not planned or (c.role in roles and c.domain in domains))}
