"""Forecast request grammar and source-origin validation; no model calculations."""
import re
from datetime import date
from services.forecasting import HORIZONS

MONTH_NAMES=(('january','jan','يناير'),('february','feb','فبراير'),('march','mar','مارس'),
    ('april','apr','أبريل','ابريل'),('may','مايو'),('june','jun','يونيو'),('july','jul','يوليو'),
    ('august','aug','أغسطس','اغسطس'),('september','sep','sept','سبتمبر'),
    ('october','oct','أكتوبر','اكتوبر'),('november','nov','نوفمبر'),('december','dec','ديسمبر'))

def forecast_intent(question,previous=None):
    q=question.casefold()
    return any(w in q for w in ('forecast','expected','predict','توقع','متوقع')) or bool(previous and previous.get('forecast') and wants_accuracy(q))

def wants_accuracy(question):
    return any(w in question.casefold() for w in ('accuracy','accurate','quality','wape','baseline','evaluation','uncertainty','rely','certainty','دقة','دقته','دقّة','النموذج','خطأ النموذج','عدم اليقين','أعتمد','اعتمد'))

def company_wide(question):
    q=question.casefold()
    from services.assistant_config import APPLICATION_IDENTITY
    branded=any(re.search(r'(?<!\w)'+re.escape(name.casefold())+r'(?!\w)',q) for name in APPLICATION_IDENTITY)
    return bool(re.search(r'\bcompany(?:-wide| wide)?\b|\b(?:all locations|all branches|whole business|entire business)\b',q) or
        any(w in q for w in ('الشركة','كل الفروع','جميع الفروع','كامل الشركة')) or branded)

def month_after(origin,lead):
    index=origin.year*12+origin.month-1+lead
    return f'{index//12:04}-{index%12+1:02}'

class ForecastRequestError(ValueError):
    def __init__(self,code,origin):self.code=code;self.origin=origin;super().__init__(code)

def requested_months(question,origin,horizon):
    """Cover named months with the smallest approved horizon from source, never today."""
    q=question.casefold().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    origin=date.fromisoformat(str(origin)[:7]+'-01')
    if re.search(r'\b(today|tomorrow|yesterday|last\s+(?:\d+\s+)?(?:months?|years?))\b',q) or any(w in q for w in ('بكرة','غدًا','غدا','أمس','امبارح','الماضي')):
        raise ForecastRequestError('forecast_dates',str(origin)[:7])
    if re.search(r'\d{4}-\d{2}-\d{2}',q):raise ForecastRequestError('forecast_dates',str(origin)[:7])
    explicit=re.findall(r'(?<!\d)(\d{4}-\d{2})(?!\d)',q)
    named=[]
    for number,aliases in enumerate(MONTH_NAMES,1):
        for alias in aliases:
            pattern=r'(?<![A-Za-z\u0600-\u06ff])'+re.escape(alias)+r'(?![A-Za-z\u0600-\u06ff])'
            # Arabic conjunction wa is a prefix, not part of the month name.
            if not alias.isascii():pattern=r'(?<![A-Za-z\u0600-\u06ff])و?'+re.escape(alias)+r'(?![A-Za-z\u0600-\u06ff])'
            named.extend((m.start(),m.end(),number) for m in re.finditer(pattern,q))
    named=sorted(set(named))
    if named and explicit:raise ForecastRequestError('forecast_dates',str(origin)[:7])
    if named:
        years=re.findall(r'(?<!\d)(\d{4})(?!\d)',q)
        selected=[]
        for _,end,number in named:
            if len(set(years))==1:year=int(years[0])
            elif years:
                following=q[end:]
                match=re.search(r'(?<!\d)(\d{4})(?!\d)',following)
                if not match:raise ForecastRequestError('forecast_dates',str(origin)[:7])
                year=int(match[1])
            else:year=origin.year+(number<=origin.month)
            selected.append(f'{year:04}-{number:02}')
        explicit=selected
    if not explicit:
        if re.search(r'(?<!\d)\d{4}(?!\d)',q):raise ForecastRequestError('forecast_dates',str(origin)[:7])
        return horizon,[]
    months=sorted(set(explicit))
    window={month_after(origin,i):i for i in range(1,max(HORIZONS)+1)}
    if len(months)!=len(explicit) or any(month not in window for month in months):
        raise ForecastRequestError('forecast_dates',str(origin)[:7])
    covering=next(value for value in HORIZONS if value>=max(window[month] for month in months))
    counts=re.findall(r'(?<!\d)(\d+)\s*(?:months?|شهور|أشهر|شهر)',q)
    if counts and (len(counts)!=1 or int(counts[0])!=len(months) or horizon!=covering):raise ForecastRequestError('forecast_horizon',str(origin)[:7])
    return covering,months
