"""Recorded final validation commands; no source/dataset/model mutation."""
import argparse,ast,importlib,json,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--job',choices=['full','regression','smoke','environment'],required=True);p.add_argument('--tag',choices=['','final'],default='');a=p.parse_args()
suffix='_'+a.tag if a.tag else ''
out=ROOT/'reports';python=str(ROOT/'.venv/Scripts/python.exe');commands=[]
if a.job=='full':commands=[('tests_full',['-m','unittest','discover','-s','tests','-v'])]
if a.job=='smoke':commands=[('smoke',['scripts/smoke_app.py','--report',str(out/'phase_9_smoke.json')])]
if a.job=='environment':commands=[('pip_check',['-m','pip','check'])]
if a.job=='regression':
    commands=[(name,[f'scripts/{script}.py',*extra,'--report',str(out/f'phase_9_{name}.json')]) for name,script,extra in [
      ('baseline','validate_db',[]),('phase1','validate_phase1',['--zip',r'C:\Users\Acer\Downloads\Cottonil_project\COTTONIL\COTTONIL_Data.zip']),
      ('executive','validate_phase3',[]),('sales','validate_phase4',[]),('profitability','validate_phase5',[]),('inventory','validate_phase6',[]),
      ('forecast','validate_phase7',[]),('customers','validate_phase8',[])]]
records=[]
for tag,arguments in commands:
    argv=[python,'-X','utf8',*arguments];started=datetime.now(timezone.utc).isoformat();t=time.perf_counter()
    with (out/f'phase_9_{tag}{suffix}_log.txt').open('wb') as log:result=subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    records.append(dict(command=subprocess.list2cmdline(argv),argv=argv,working_directory=str(ROOT),started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.perf_counter()-t,exit_code=result.returncode,log=f'phase_9_{tag}{suffix}_log.txt'))
    (out/f'phase_9_execution_{a.job}{suffix}.json').write_text(json.dumps(records,indent=2),encoding='utf-8');print(tag,'exit',result.returncode,flush=True)
if a.job=='environment':
    files=[p for p in ROOT.rglob('*.py') if '.venv' not in p.parts and '.git' not in p.parts]
    for path in files:ast.parse(path.read_text(encoding='utf-8-sig'))
    modules=['analytics','predictive','assistant_engine']+['.'.join(p.relative_to(ROOT).with_suffix('').parts) for d in ('services','ui','db') for p in (ROOT/d).rglob('*.py') if '__pycache__' not in p.parts]
    for name in modules:importlib.import_module(name)
    import importlib.metadata
    (out/'phase_9_environment.json').write_text(json.dumps(dict(syntax_files=len(files),import_modules=len(modules),versions={n:importlib.metadata.version(n) for n in ('groq','python-dotenv','streamlit','numpy','pandas','scikit-learn')}),indent=2),encoding='utf-8')
raise SystemExit(0 if all(r['exit_code']==0 for r in records) else 1)
