"""Local secret loading and bounded Groq-only settings. Never serialize Settings."""
from dataclasses import dataclass,field
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_MODEL='openai/gpt-oss-120b'
# Application identity metadata, shared with scope resolution (never branch IDs).
APPLICATION_IDENTITY=('Cottonil','قطنيل')

@dataclass(frozen=True)
class Settings:
    api_key:str=field(default='',repr=False,compare=False)
    model:str=DEFAULT_MODEL
    timeout:float=25
    max_rounds:int=4
    max_tools:int=8
    output_tokens:int=1000
    session_calls:int=40
    session_tokens:int=160000
    history_messages:int=8
    turn_seconds:int=100

def load_settings(secrets=None):
    load_dotenv(ROOT/'.env',override=False,interpolate=False)
    def value(name,default=''):
        return os.environ.get(name) or (secrets or {}).get(name) or default
    def bounded(name,default,lo,hi):
        try:v=int(value(name,str(default)))
        except (TypeError,ValueError):raise ValueError('Invalid bounded assistant setting') from None
        if not lo<=v<=hi:raise ValueError('Assistant setting outside allowed bounds')
        return v
    model=value('GROQ_MODEL',DEFAULT_MODEL)
    if not isinstance(model,str) or not model or len(model)>100 or any(c.isspace() for c in model) or '://' in model:
        raise ValueError('Invalid Groq model identifier')
    return Settings(api_key=value('GROQ_API_KEY'),model=model,
        timeout=bounded('GROQ_TIMEOUT_SECONDS',25,5,40),max_rounds=bounded('GROQ_MAX_ROUNDS',4,1,4),
        max_tools=bounded('GROQ_MAX_TOOLS',8,1,8),output_tokens=bounded('GROQ_OUTPUT_TOKENS',1000,128,2000),
        session_calls=bounded('GROQ_SESSION_CALLS',40,1,60),session_tokens=bounded('GROQ_SESSION_TOKENS',160000,1000,250000))
