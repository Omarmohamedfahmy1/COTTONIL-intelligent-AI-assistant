"""Start an isolated loopback browser-review process, optionally without a key.

Never edits .env. Only the child environment is changed. Prints PID/port, no values.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8520);p.add_argument('--no-key',action='store_true');a=p.parse_args()
    env=os.environ.copy()
    if a.no_key:env['GROQ_API_KEY']=''
    log=ROOT/'outputs'/f'phase9-browser-{a.port}.log'
    with log.open('w',encoding='utf-8') as f:
        proc=subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.address=127.0.0.1',f'--server.port={a.port}',
            '--server.headless=true','--browser.gatherUsageStats=false'],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    print(json.dumps(dict(pid=proc.pid,port=a.port,no_key_child=a.no_key)))
