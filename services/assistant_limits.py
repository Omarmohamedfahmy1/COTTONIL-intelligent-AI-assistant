"""Known capability prerequisites checked before asking for user parameters.

These are approved data-contract limitations, not computed business results.
Unknown intents still go through ordinary capability and evidence validation.
"""
import re
from services.assistant_language import normalized

LIMITS={
 'net_profit':dict(aliases=('net profit','net income','profit after operating expenses','profit after operating costs','صافي الربح','صافي ربح','صافي أرباح','صافي الارباح','صافي الأرباح','الربح الصافي','الأرباح الصافية','الارباح الصافية','الربح بعد مصاريف التشغيل','الربح بعد المصروفات التشغيلية'),
   kind='incomplete_financial_data',
   explanation=('Net profit is unavailable: the approved data lack a complete operating-expense basis and validated refund/return-cost adjustments. Recorded gross profit is a supported alternative before these adjustments, not net profit.',
                'صافي الربح غير متاح: البيانات المعتمدة لا توفر أساسًا مكتملًا للمصروفات التشغيلية وتسويات المرتجعات وتكلفتها. البديل المدعوم مجمل الربح المسجّل قبل هذه التسويات، وليس صافي ربح.')),
 'operating_expenses':dict(aliases=('operating expenses','operating costs','opex','المصروفات التشغيلية','مصروفات التشغيل','مصاريف التشغيل','المصاريف التشغيلية'),
   kind='incomplete_financial_data',
   explanation=('A complete approved operating-expense measure is unavailable; operating expenses cannot be inferred from gross profit.',
                'لا يتوفر مؤشر معتمد ومكتمل لمصروفات التشغيل؛ لا يمكن استنتاجها من مجمل الربح.')),
 'refund_adjusted':dict(aliases=('refund-adjusted','return-adjusted','net sales','sales after refunds','revenue after refunds','profit after refunds','صافي المبيعات','مبيعات بعد المرتجعات','المبيعات بعد المرتجعات','الربح بعد المرتجعات'),
   kind='incomplete_financial_data',
   explanation=('Refund-adjusted sales or profit are unavailable: recorded refunds have an unverified tax/discount basis and no validated returned-cost reversal. Recorded sales and gross profit are before refunds; recorded refunds alone do not establish net profit.',
                'المبيعات أو الأرباح المعدّلة بالمرتجعات غير متاحة: أساس الضريبة والخصم للمبالغ المستردة غير متحقق وتسوية تكلفة المرتجعات غير معتمدة. المبيعات ومجمل الربح المسجّلان قبل المرتجعات؛ المبالغ المستردة وحدها لا تثبت صافي الربح.')),
 'sku_stock':dict(aliases=('sku stock','sku inventory','product-level stock','مخزون الصنف','مخزون على مستوى الصنف'),
   kind='unsupported_metric',
   explanation=('SKU stock is unsupported: approved stock is monthly location/category data. A recorded location/category snapshot is a supported alternative.',
                'مخزون الصنف غير مدعوم: المخزون المعتمد شهري على مستوى الموقع والفئة. البديل لقطة مخزون مسجّلة للموقع والفئة.')),
 'live_stock':dict(aliases=(),kind='unsupported_metric',explanation=(
   'Exact live stock is unavailable: only dated monthly location/category snapshots are recorded.',
   'المخزون اللحظي الدقيق غير متاح؛ المسجّل لقطات شهرية مؤرخة على مستوى الموقع والفئة فقط.')),
 'certain_stockout':dict(aliases=(),kind='unsupported_metric',explanation=(
   'Guaranteed future stockouts are unsupported. Recorded category risk scores and heuristic cover are not certain predictions.',
   'لا يمكن تأكيد نفاد المخزون مستقبلًا؛ درجات المخاطر المسجّلة وتقديرات التغطية ليست تنبؤات مؤكدة.')),
}

def preflight(question):
    """Mask unsupported expressions so generic aliases cannot relabel them.

    Keep all other text intact for ordinary intent, entity and period resolution.
    """
    if not isinstance(question,str):return [],question
    text=question;issues=[]
    q=normalized(question)
    stock=bool(re.search(r'\bstock(?:outs?)?\b|\binventory\b|مخزون',q))
    if stock and re.search(r'\bskus?\b|على مستوى (?:ال)?صنف',q):issues.append(dict(metric='sku_stock',kind='unsupported_metric',blocking=True))
    live=bool(re.search(r'(?:exact|real.time|live).*current|current.*(?:exact|real.time|live)|مخزون لحظي|المخزون اللحظي',q))
    current=bool(re.search(r'\bcurrent\b|المخزون الحالي',q)) and not re.search(r'recorded|snapshot|monthly|مسجل|مسجّل|لقطة|شهري',q)
    if stock and (live or current):issues.append(dict(metric='live_stock',kind='unsupported_metric',blocking=True))
    if stock and re.search(r'\b(?:definitely|guaranteed|certainly)\b|(?<!\w)(?:[وفبكل])?(?:مؤكد|مضمون|حتما)(?!\w)',q):issues.append(dict(metric='certain_stockout',kind='unsupported_metric',blocking=True))
    for key,contract in LIMITS.items():
        if not contract['aliases']:continue
        alternatives=[('' if a.isascii() else r'(?:[وفبكل])?')+re.escape(a) for a in sorted(contract['aliases'],key=len,reverse=True)]
        pattern=r'(?<!\w)(?:'+ '|'.join(alternatives)+r')(?!\w)'
        if key=='refund_adjusted':pattern+=r'(?:\s+(?:sales|revenue|gross profit|profit))?'
        text,count=re.subn(pattern,lambda m:' '*len(m.group()),text,flags=re.I)
        if count and key not in {i['metric'] for i in issues}:issues.append(dict(metric=key,kind=contract['kind']))
    if any(i.get('blocking') for i in issues):
        # Remove the unsupported inventory measure, retaining independent
        # financial clauses and their explicit dates for a possible partial.
        text=re.sub(r'(?i)وحدات\s+(?:ال)?مخزون|\bskus?(?:[- ]level)?\b|(?:\bunits?\s+of\s+)?\b(?:stock(?:outs?)?|inventory)\b(?:\s+(?:units?|quantities))?|(?:ال)?مخزون|(?:ال)?صنف',lambda m:' '*len(m.group()),text)
    return issues,text

def explanations(issues,lang):
    keys=[i['metric'] for i in issues if i.get('metric') in LIMITS]
    # Net-profit explanation already contains the OPEX prerequisite.
    if 'net_profit' in keys:keys=[k for k in keys if k!='operating_expenses']
    return [LIMITS[k]['explanation'][0 if lang=='English' else 1] for k in dict.fromkeys(keys)]
