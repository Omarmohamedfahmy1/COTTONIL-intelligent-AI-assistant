"""Final image/source/privacy verification. Writes aggregate metadata only."""
import hashlib,json,re,sqlite3,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.assistant_config import load_settings
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def finalize():
    browser=json.loads((ROOT/'reports/phase_9_browser_review.json').read_text())
    photos=[]
    for path in sorted((ROOT/'reports/screenshots').glob('phase_9_*.jpg')):
        with Image.open(path) as im:im.verify()
        with Image.open(path) as im:width,height=im.size
        photos.append(dict(file=path.relative_to(ROOT).as_posix(),width=width,height=height,bytes=path.stat().st_size,sha256=digest(path)))
    browser['screenshots']='16 original JPEG API captures; no pixel edits/recompression. 14/15 are extra stock views before scrolling to the new block; 16 shows the visible block. 09 is a desktop inventory extra, not narrow. 10 is the actual390px offline Arabic capture. 02 is the default1280x720 missing-key capture. Other principal desktop captures are1440x1100.'
    browser['images']=photos
    browser['narrow_capture_note']='Requested/measured viewport390x844; original API JPEG may be390x843; exact dimensions listed per file.'
    (ROOT/'reports/phase_9_browser_review.json').write_text(json.dumps(browser,indent=2,ensure_ascii=False),encoding='utf-8')
    prior=json.loads((ROOT/'reports/phase_8_integrity_environment.json').read_text())
    old_photos=[dict(file=p['file'],passed=digest(ROOT/p['file'])==p['sha256']) for p in prior['screenshots']]
    earlier=json.loads((ROOT/'reports/phase_8_start_preservation.json').read_text())['screenshots']
    old_photos += [dict(file=name,passed=digest(ROOT/name)==expected) for name,expected in earlier.items()]
    key=load_settings().api_key
    roots=[p for p in ROOT.iterdir() if p.is_file() and p.name!='.env' and p.suffix in ('.py','.md','.txt','.bat','.toml','.example')]
    files=roots+[p for folder in ('services','ui','scripts','tests','docs','reports','.streamlit') for p in (ROOT/folder).rglob('*') if p.is_file() and p.name!='secrets.toml' and '__pycache__' not in p.parts and p.suffix in ('.py','.md','.json','.txt','.toml','.log')]
    files += [p for p in (ROOT/'outputs').glob('phase9-browser*.log')]
    key_hits=[];record_hits=[]
    with sqlite3.connect((ROOT/'data/cottonil.db').as_uri()+'?mode=ro',uri=True) as db:ids={r[0] for r in db.execute('SELECT customer_id FROM customers')}
    for path in files:
        raw=path.read_bytes();text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig',errors='replace')
        if key and key in text:key_hits.append(path.relative_to(ROOT).as_posix())
        matches=ids.intersection(re.findall(r'\b[A-Za-z0-9_-]{8}\b',text))
        if matches:record_hits.append(dict(file=path.relative_to(ROOT).as_posix(),count=len(matches)))
    result=dict(passed=not key_hits and not record_hits and all(p['passed'] for p in old_photos) and len(photos)==16,
        original_approved_screenshots=old_photos,approved_screenshot_count=len(old_photos),new_phase9_original_images=len(photos),public_text_and_test_logs_scanned=len(files),
        actual_secret_findings=key_hits,actual_customer_identifier_findings=record_hits,
        note='Curated aggregate outputs, exact actual-key/customer-ID membership checks and source preservation; not a formal DLP/security audit or OCR of image pixels. Screenshots were inspected in actual browser and no secret was entered into the UI.',
        provider_compliance='Active UI/new services only official Groq SDK/fixed host. Frozen historical OpenAI function retained but not imported into active connected UI.')
    (ROOT/'reports/phase_9_security_images.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Security/image checks:',result['passed'],'; files scanned',len(files),'; all original approved images',len(old_photos),'; Phase9 captures',len(photos))
    return result
if __name__=='__main__':raise SystemExit(0 if finalize()['passed'] else 1)
