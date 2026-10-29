"""Bounded authentication/catalog probe. Reports metadata only, never secrets."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.assistant_config import load_settings
from services.groq_provider import GroqProvider,ProviderError

def check():
    settings=load_settings();started=time.perf_counter()
    result=dict(provider='Groq',sdk=__import__('groq').__version__,configured=bool(settings.api_key),model=settings.model,
        inference_requests=0,secret_logged=False)
    if not settings.api_key:return dict(result,status='NOT RUN',reason='missing_key')
    provider=None
    try:
        provider=GroqProvider(settings);models=provider.models()
        result.update(status='authenticated',model_listed=settings.model in models,available_models=models,
            candidates={m:m in models for m in ('openai/gpt-oss-120b','qwen/qwen3.8-27b','openai/gpt-oss-20b')})
    except ProviderError as e:result.update(status='blocked',error=e.code)
    finally:
        if provider:provider.close()
    result['elapsed_seconds']=time.perf_counter()-started
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'reports/phase_9_groq_auth.json');a=p.parse_args()
    result=check();a.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='authenticated' else 1)
