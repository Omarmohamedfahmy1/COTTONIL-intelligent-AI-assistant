"""Read-only preservation, syntax/import, environment and original screenshot checks."""
import ast,hashlib,importlib,importlib.metadata,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    snapshot=ROOT.parent/'Cottonil_Phase5_Review.zip'
    with zipfile.ZipFile(snapshot) as archive:
        names=[name for name in archive.namelist() if name.endswith('.py')]
        modified=[name for name in names if (ROOT/name).read_bytes()!=archive.read(name)]
        expected={'ui/assistant.py','ui/data.py','ui/i18n.py','ui/pages/inventory.py'}
        assert set(modified)==expected,modified
        unchanged={name:sha(ROOT/name) for name in names if name not in modified}
        prior=json.loads(archive.read('reports/phase_5_integrity.json'))
        private={name:sha(ROOT/name) for name in prior['private_file_hashes']}
        assert private==prior['private_file_hashes'],'Private data/database/model artifacts changed'
        old_images=[name for name in archive.namelist() if name.startswith('reports/screenshots/')]
        assert all((ROOT/name).read_bytes()==archive.read(name) for name in old_images)
    with zipfile.ZipFile(ROOT.parent/'Cottonil_Phase4_Review.zip') as archive:
        images=[name for name in archive.namelist() if name.startswith('reports/screenshots/')]
        assert all((ROOT/name).read_bytes()==archive.read(name) for name in images)
    dataset=Path(r'C:\Users\Acer\Downloads\Cottonil_project\COTTONIL\COTTONIL_Data.zip')
    dataset_sha=sha(dataset);assert dataset_sha==prior['original_dataset_zip_sha256']
    paths=list(ROOT.glob('*.py'))+[p for folder in ('db','services','ui','scripts','tests') for p in (ROOT/folder).rglob('*.py') if '__pycache__' not in p.parts]
    for p in paths:ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
    modules=['analytics','assistant_engine','predictive']+['.'.join(p.relative_to(ROOT).with_suffix('').parts) for folder in ('db','services','ui') for p in (ROOT/folder).rglob('*.py') if '__pycache__' not in p.parts]
    for module in modules:importlib.import_module(module)
    from PIL import Image
    screenshots=[]
    for p in sorted((ROOT/'reports/screenshots').glob('phase_6_*.jpg')):
        with Image.open(p) as picture:picture.verify()
        with Image.open(p) as picture:screenshots.append(dict(file=p.relative_to(ROOT).as_posix(),width=picture.width,height=picture.height,format=picture.format,sha256=sha(p)))
    assert len(screenshots)>=8,'Capture the eight requested real UI views first'
    result=dict(approved_snapshot=snapshot.name,modified_existing_python=modified,unchanged_python_sha256=unchanged,
        original_98_tests_unchanged=all(name in unchanged for name in names if name.startswith('tests/')),
        prior_screenshots_unchanged=len(old_images)+len(images),private_file_hashes=private,private_artifacts_unchanged=True,
        original_dataset_zip_sha256=dataset_sha,original_dataset_unchanged=True,syntax_passed_files=len(paths),imports_passed=modules,
        python=sys.version,dependencies={name:importlib.metadata.version(name) for name in ('streamlit','pandas','numpy','plotly','scikit-learn','openai')},screenshots=screenshots)
    (ROOT/'reports/phase_6_integrity_environment.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS preservation; syntax',len(paths),'imports',len(modules),'original screenshots',len(screenshots))
    return result


if __name__=='__main__':verify()
