"""Compositional bilingual request vocabulary; no business results or entities.

Company aliases come from application branding metadata. Analytics remains in
the approved services; this module only describes scope and answer obligations.
"""
import re,unicodedata

def normalized(text):
    text=unicodedata.normalize('NFKC',text).casefold().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    return re.sub(r'[\u064b-\u065f\u0670\u0640]','',text)

def private_intent(text):
    q=normalized(text)
    customers=bool(re.search(r'customers?|clients?|عملاء|عميل',q))
    contact=bool(re.search(r'phones?|mobile|telephone|contact (?:details|information)|تليفون|تلفون|تليفونات|هواتف|هاتف|ايميل|بريد',q))
    names=bool(re.search(r'\bnames?\b|اسماء|أسماء|اسم العميل',q))
    identifiers=bool(re.search(r'customer identifiers?|رقم العميل|أرقام العملاء|ارقام العملاء',q))
    segments=bool(re.search(r'segments?|cohorts?|شرائح|شريحة|أفواج',q))
    individual=bool(re.search(r'\b(?:individual|each customer|per customer)\b|لكل عميل|على مستوى العميل',q))
    # Asking whether a model is suitable for individual decisions is a public
    # methodology question; requesting individual scores/contacts is restricted.
    scoring=bool(re.search(r'give|show|list|rank|اعرض|اديني|رتب',q)) and bool(re.search(r'predict|probabilit|score|احتمال|متوقع',q))
    methodology=bool(re.search(r'model|نموذج',q) and re.search(r'churn|فقدان',q) and re.search(r'reliab|evaluat|metrics|roc|موثوق|تقييم|مؤشرات',q))
    individual_scores=bool(re.search(r'individual (?:customer |churn )?(?:predictions?|risk|scores?|probabilit)',q))
    direct=bool(re.search(r'(?:give|show|list|rank|export)\s+(?:me\s+)?(?:the\s+)?individual\b|(?:and|,)\s+individual (?:predictions?|scores?)',q))
    if individual_scores and (not methodology or direct):return True
    return customers and (contact or identifiers or (names and not segments) or (individual and scoring and not methodology) or direct)

def metric_reference_size(text):
    q=normalized(text)
    if not re.search(r'\bsame\b|نفس',q) or not re.search(r'metrics?|indicators?|مؤشر|مقياس|مقاييس',q):return None
    words={'two':2,'three':3,'four':4,'both':2,'اثنين':2,'ثلاثة':3,'ثلاث':3,'أربعة':4,'اربعة':4}
    if re.search(r'مؤشرين|المؤشرين|مقياسين',q):return 2
    for word,count in words.items():
        if re.search(r'(?<!\w)'+word+r'(?!\w)',q):return count
    found=re.search(r'(?<!\d)(\d+)\s*(?:metrics?|indicators?|مؤشر|مقاييس)',q)
    return int(found[1]) if found else 0

def explicit_global_reset(text):
    q=normalized(text)
    reset=bool(re.search(r'\b(?:ignore|forget|instead|discard)\b|do not compare|don.t compare|سيبك|انسى|اترك|بدلا|بدل',q))
    whole=bool(re.search(r'\b(?:overall|whole|entire|total|company[- ]wide)\b|كلها|إجمالي|اجمالي|كل الفروع|جميع الفروع',q))
    return reset and whole

def requested_grain(text):
    q=normalized(text)
    # A category of products remains category grain, independent of word order.
    if re.search(r'\bcategor(?:y|ies)\b|فئات|فئة',q):return 'category'
    if re.search(r'\bproducts?\b|منتج|منتجات',q):return 'product'
    if re.search(r'\b(?:monthly|daily|weekly|yearly|trends?)\b|شهري|يومي|أسبوعي|اسبوعي|سنوي|اتجاه',q):return 'time'
    if re.search(r'\b(?:branches|locations)\b|الفروع|فروع|المواقع',q):return 'locations'
    return None


def ranking_syntax(text):
    """Compositional rank/cardinality grammar, independent of dates/entities."""
    q=normalized(text)
    bestselling=bool(re.search(r'\bbest[- ]?selling\b|\bmost (?:sold|popular)\b|(?:أكتر|اكتر|أكثر|اكثر).*مبيع',q))
    ranked=bestselling or bool(re.search(r'\b(?:top|bottom|highest|lowest|best|leading|ranking)\b|أعلى|اعلى|أقل|اقل|أفضل',q))
    words={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
           'واحد':1,'اثنين':2,'ثلاثة':3,'ثلاث':3,'أربعة':4,'اربعة':4,'خمسة':5,'خمس':5,'ستة':6,'سبعة':7,'ثمانية':8,'تسعة':9,'عشرة':10}
    number=r'(?:\d+|'+ '|'.join(map(re.escape,words))+r')'
    entity=r'(?:branches|locations|products|categories|فروع|منتجات|فئات)'
    hits=[]
    if ranked:
        for pattern in (r'(?:\btop|\bhighest|\blowest|\bbottom|أعلى|اعلى|أقل|اقل|أفضل|أكتر|اكتر|أكثر|اكثر)\s+('+number+r')(?![\w.])',
                        r'(?<!\w)('+number+r')\s+'+entity+r'(?!\w)'):
            for m in re.finditer(pattern,q):hits.append(words.get(m[1],int(m[1]) if m[1].isdigit() else None))
    return dict(ranked=ranked,bestselling=bestselling,count=hits[0] if hits and len(set(hits))==1 else None,
                ambiguous_count=len(set(hits))>1)


def temporal_extrema(text):
    q=normalized(text);result=[]
    if re.search(r'\b(?:highest|maximum|peak|largest)\b|أعلى|اعلى|أكبر|اكبر',q):result.append('highest')
    if re.search(r'\b(?:lowest|minimum|smallest)\b|أقل|اقل|أصغر|اصغر|أدنى|ادنى',q):result.append('lowest')
    return result

def obligations(text,forecast=False):
    q=normalized(text);result=[]
    negative_cause=bool(re.search(r'without (?:assuming |inferring )?(?:unproven |unsupported )?(?:caus|reasons)|من غير.*(?:سبب|اسباب|أسباب)|بدون.*(?:سبب|اسباب|أسباب)',q))
    if negative_cause:result.append('noncausal_description')
    if re.search(r'\b(?:largest|smallest|biggest)\b|أكبر|اكبر|أصغر|اصغر',q):result.append('group_extreme')
    if re.search(r'\b(?:same products|same items|overlap|membership|identical sets)\b|نفس المنتجات|تطابق.*(?:قائم|منتج)|المنتجات نفسها',q):result.append('ranking_membership')
    model=bool(re.search(r'\bmodel\b|نموذج',q))
    if re.search(r'baseline|wape|model evaluation|model performance|تقييم النموذج|أداء النموذج|اداء النموذج',q):result.append('forecast_evaluation')
    if re.search(r'uncertainty|confidence (?:bands?|intervals?)|عدم اليقين|حدود الثقة',q):result.append('forecast_uncertainty')
    if re.search(r'\b(?:certainty|certain|guaranteed|rely)\b|مؤكد|مضمون|أعتمد|اعتمد',q) and (forecast or re.search(r'forecast|توقع',q)):result.append('forecast_reliability')
    if model and re.search(r'churn|فقدان العملاء',q) and re.search(r'reliab|trust|decisions?|موثوق|قرارات|اعتماد',q):result.append('customer_reliability')
    if re.search(r'\balone\b|لوحده|وحده',q) and re.search(r'churn|risk|فقدان|عرضة|مخاطر',q):result.append('inference_limit')
    return result

def dual_ranking(text):
    q=normalized(text)
    return len(re.findall(r'\b(?:top|bottom|highest|lowest)\b|أعلى|اعلى|أقل|اقل',q))>1 or bool(re.search(r'two rankings|both rankings|قائمتين|ترتيبين',q))
