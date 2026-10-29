"""Preserve historical evidence; record exact final Phase 10 commands and exit codes."""
import argparse,ast,importlib,importlib.metadata,json,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    p=argparse.ArgumentParser();p.add_argument('--job',choices=['full','regression','smoke','environment','evaluation'],required=True);a=p.parse_args()
    out=ROOT/'reports';commands=[]
    if a.job=='full':commands=[('tests_full',['-m','unittest','discover','-s','tests','-v'])]
    if a.job=='smoke':commands=[('smoke',['scripts/smoke_app.py','--report',str(out/'phase_10_smoke.json')])]
    if a.job=='environment':commands=[('pip_check',['-m','pip','check'])]
    if a.job=='evaluation':commands=[('offline_evaluation',['scripts/evaluate_phase10.py']),('mock_evaluation',['scripts/evaluate_phase10.py','--mode','mock'])]
    if a.job=='regression':
        commands=[(name,[f'scripts/{script}.py',*extra,'--report',str(out/f'phase_10_{name}.json')]) for name,script,extra in [
          ('baseline','validate_db',[]),('phase1','validate_phase1',['--zip',r'C:\Users\Acer\Downloads\Cottonil_project\COTTONIL\COTTONIL_Data.zip']),
          ('executive','validate_phase3',[]),('sales','validate_phase4',[]),('profitability','validate_phase5',[]),('inventory','validate_phase6',[]),
          ('forecast','validate_phase7',[]),('customers','validate_phase8',[]),('assistant','validate_phase9',[])]]
    records=[]
    for tag,args in commands:
        argv=[sys.executable,'-X','utf8',*args];started=datetime.now(timezone.utc).isoformat();t=time.perf_counter()
        log=out/f'phase_10_{tag}_log.txt'
        with log.open('wb') as f:r=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        records.append(dict(command=subprocess.list2cmdline(argv),argv=argv,working_directory=str(ROOT),started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.perf_counter()-t,exit_code=r.returncode,log=log.name))
        (out/f'phase_10_execution_{a.job}.json').write_text(json.dumps(records,indent=2),encoding='utf-8');print(tag,'exit',r.returncode,flush=True)
    if a.job=='environment':
        files=[p for p in ROOT.rglob('*.py') if not {'.venv','.git','__pycache__'}&set(p.parts)]
        for path in files:ast.parse(path.read_text(encoding='utf-8-sig'))
        modules=['analytics','predictive','assistant_engine']+['.'.join(p.relative_to(ROOT).with_suffix('').parts) for d in ('services','ui','db') for p in (ROOT/d).rglob('*.py') if '__pycache__' not in p.parts]
        for name in modules:importlib.import_module(name)
        (out/'phase_10_environment.json').write_text(json.dumps(dict(syntax_files=len(files),import_modules=len(modules),versions={n:importlib.metadata.version(n) for n in ('groq','python-dotenv','streamlit','numpy','pandas','scikit-learn')}),indent=2),encoding='utf-8')
    return int(any(r['exit_code'] for r in records))
if __name__=='__main__':raise SystemExit(main())
