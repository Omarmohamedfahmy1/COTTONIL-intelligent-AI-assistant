"""Read-only Phase 7 preservation, syntax/import and screenshot verification."""
import ast
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify():
    snapshot = ROOT.parent / 'Cottonil_Phase6_Review.zip'
    with zipfile.ZipFile(snapshot) as archive:
        names = [name for name in archive.namelist() if name.endswith('.py')]
        modified = [name for name in names if (ROOT / name).read_bytes() != archive.read(name)]
        expected = {'ui/assistant.py', 'ui/data.py', 'ui/i18n.py', 'ui/pages/forecasting.py'}
        assert set(modified) == expected, modified
        unchanged = {name: sha(ROOT / name) for name in names if name not in modified}
        prior = json.loads(archive.read('reports/phase_6_integrity_environment.json'))
        private = {name: sha(ROOT / name) for name in prior['private_file_hashes']}
        assert private == prior['private_file_hashes'], 'Private artifacts changed'
    old_images = set()
    for phase in (4, 5, 6):
        with zipfile.ZipFile(ROOT.parent / f'Cottonil_Phase{phase}_Review.zip') as archive:
            for name in archive.namelist():
                if name.startswith('reports/screenshots/') and not name.endswith('/'):
                    assert (ROOT / name).read_bytes() == archive.read(name), name
                    old_images.add(name)
    dataset = Path(r'C:\Users\Acer\Downloads\Cottonil_project\COTTONIL\COTTONIL_Data.zip')
    dataset_sha = sha(dataset)
    assert dataset_sha == prior['original_dataset_zip_sha256'], 'Original dataset changed'
    paths = list(ROOT.glob('*.py')) + [p for folder in ('db', 'services', 'ui', 'scripts', 'tests')
        for p in (ROOT / folder).rglob('*.py') if '__pycache__' not in p.parts]
    for path in paths:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    modules = ['analytics', 'assistant_engine', 'predictive'] + [
        '.'.join(p.relative_to(ROOT).with_suffix('').parts)
        for folder in ('db', 'services', 'ui') for p in (ROOT / folder).rglob('*.py')
        if '__pycache__' not in p.parts]
    for module in modules:
        importlib.import_module(module)
    from PIL import Image
    screenshots = []
    for path in sorted((ROOT / 'reports/screenshots').glob('phase_7_*.jpg')):
        with Image.open(path) as picture:
            picture.verify()
        with Image.open(path) as picture:
            screenshots.append(dict(file=path.relative_to(ROOT).as_posix(), width=picture.width,
                height=picture.height, format=picture.format, sha256=sha(path)))
    assert len(screenshots) == 9, 'Nine actual browser screenshots required'
    result = dict(approved_snapshot=snapshot.name, approved_snapshot_sha256=sha(snapshot),
        modified_existing_python=modified, unchanged_python_sha256=unchanged,
        original_119_tests_unchanged=all(name in unchanged for name in names if name.startswith('tests/')),
        prior_screenshots_unchanged=len(old_images), private_file_hashes=private,
        private_artifacts_unchanged=True, original_dataset_zip_sha256=dataset_sha,
        original_dataset_unchanged=True, syntax_passed_files=len(paths), imports_passed=modules,
        python=sys.version, dependencies={name: importlib.metadata.version(name) for name in
            ('streamlit', 'pandas', 'numpy', 'plotly', 'scikit-learn', 'openai')}, screenshots=screenshots)
    (ROOT / 'reports/phase_7_integrity_environment.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('PASS preservation; syntax', len(paths), 'imports', len(modules), 'screenshots', len(screenshots))
    return result


if __name__ == '__main__':
    verify()
