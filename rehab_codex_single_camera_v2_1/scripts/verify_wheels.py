"""Verify all cached installation wheels against the official PyPI JSON digests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import urllib.request

from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def verify(path):
    name, version, _, _ = parse_wheel_filename(path.name)
    api = f'https://pypi.org/pypi/{name}/{version}/json'
    with urllib.request.urlopen(api, timeout=30) as response:
        metadata = json.load(response)
    release = next(x for x in metadata['urls'] if x['filename'] == path.name)
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    if h != release['digests']['sha256']:
        raise RuntimeError('Wheel digest mismatch: '+path.name)
    info = metadata['info']
    return {'distribution': str(name), 'version': str(version), 'wheel': path.name, 'sha256': h,
            'official_pypi_metadata': api, 'official_download': release['url'],
            'license_expression': info.get('license_expression'),
            'license_metadata_excerpt': (info.get('license') or '')[:300], 'verified': True}


if __name__ == '__main__':
    paths = sorted((ROOT/'.runtime/verified-wheels').glob('*.whl'))
    if not paths:
        raise SystemExit('No wheels downloaded for verification')
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(verify, paths))
    output = {'platform': 'Windows x64 / Python 3.13.11', 'transport': 'Tsinghua PyPI mirror',
              'verification_source': 'official pypi.org JSON SHA256 values', 'wheels': results}
    (ROOT/'docs/DEPENDENCY_MANIFEST.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} wheels verified against official PyPI SHA256 digests.')
