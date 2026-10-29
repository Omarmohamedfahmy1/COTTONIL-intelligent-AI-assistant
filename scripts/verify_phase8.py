"""Preservation, syntax/import, environment and original customer screenshots."""
import ast,hashlib,importlib,importlib.metadata,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def verify():
    before=json.loads((ROOT/'reports/phase_8_start_preservation.json').read_text())
    modified=[name for name,digest in before['source'].items() if sha(ROOT/name)!=digest]
    expected={'ui/assistant.py','ui/data.py','ui/i18n.py','ui/pages/customers.py'}
    assert set(modified)==expected,modified
    assert all(sha(path)==digest for path,digest in before['private'].items()),'Original private dataset/database/artifacts changed'
    assert all(sha(ROOT/path)==digest for path,digest in before['screenshots'].items()),'Prior screenshots changed'
    paths=list(ROOT.glob('*.py'))+[p for d in ('db','services','ui','scripts','tests') for p in (ROOT/d).rglob('*.py') if '__pycache__' not in p.parts]
    for path in paths:ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
    modules=['analytics','assistant_engine','predictive']+['.'.join(p.relative_to(ROOT).with_suffix('').parts) for d in ('db','services','ui') for p in (ROOT/d).rglob('*.py') if '__pycache__' not in p.parts]
    for name in modules:importlib.import_module(name)
    from PIL import Image
    screenshots=[]
    for path in sorted((ROOT/'reports/screenshots').glob('phase_8_*.jpg')):
        with Image.open(path) as picture:picture.verify()
        with Image.open(path) as picture:screenshots.append(dict(file=path.relative_to(ROOT).as_posix(),width=picture.width,height=picture.height,sha256=sha(path)))
    assert len(screenshots)==9,'Capture all nine actual browser views'
    result=dict(passed=True,modified_existing_python=modified,unchanged_existing_python=len(before['source'])-len(modified),
        original_139_tests_unchanged=True,phase7_models_and_inventory_financial_foundation_unchanged=True,private_artifacts_unchanged=True,
        original_dataset_database_saved_customer_artifact_hashes=before['private'],prior_screenshots_unchanged=len(before['screenshots']),
        syntax_passed_files=len(paths),imports_passed=modules,python=sys.version,
        dependencies={name:importlib.metadata.version(name) for name in ('streamlit','pandas','numpy','plotly','scikit-learn','openai','threadpoolctl')},screenshots=screenshots)
    (ROOT/'reports/phase_8_integrity_environment.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS preservation, syntax',len(paths),'imports',len(modules),'screenshots',len(screenshots))
    return result


if __name__=='__main__':verify()
