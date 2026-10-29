"""Historical named-month windows/cutoffs; no forecasting or metric formulas."""
import re
from datetime import date
from calendar import monthrange
from services.assistant_forecast import MONTH_NAMES
from services.assistant_language import normalized

def named_period(question,context_year):
    q=normalized(question);hits=[]
    for number,aliases in enumerate(MONTH_NAMES,1):
        for alias in aliases:
            prefix='' if alias.isascii() else r'[ولب]?'
            # Arabic punctuation belongs to the Arabic Unicode block too; it
            # is a boundary, not part of a month word.
            pattern=r'(?<!\w)'+prefix+re.escape(normalized(alias))+r'(?!\w)'
            for match in re.finditer(pattern,q):hits.append((match.start(),match.end(),number))
    hits=sorted(set(hits))
    if not hits:return None
    if len(hits)==2:
        between=q[hits[0][1]:hits[1][0]]
        if re.search(r'\bor\b|\bأو\b|\bاو\b',between):raise ValueError('Alternative months are ambiguous')
        if not (re.search(r'[-–—]|\b(?:to|through|until)\b|إلى|الى|حتى',between) or q[hits[1][0]:].startswith('ل')):
            raise ValueError('Two months need an explicit range relationship')
    years=re.findall(r'(?<![\d-])(\d{4})(?![\d-])',q)
    if len(hits)>2 or len(set(years))>2:raise ValueError('Ambiguous named month window')
    selected=[]
    for _,end,month in hits:
        if len(set(years))==1:year=int(years[0])
        elif years:
            match=re.search(r'(?<!\d)(\d{4})(?!\d)',q[end:])
            if not match:raise ValueError('Each month needs a year')
            year=int(match[1])
        else:year=context_year
        selected.append((year,month))
    start=date(*selected[0],1);year,month=selected[-1];end=date(year,month,monthrange(year,month)[1])
    if start>end:raise ValueError('Named month range is reversed')
    cutoff=bool(re.search(r'\b(?:until|through|as of|up to)\b|حتى|حتي',q)) and len(hits)==1
    return dict(start=str(start),end=str(end),snapshot_as_of=str(end) if cutoff else None)
