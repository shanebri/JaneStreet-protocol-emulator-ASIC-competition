"""Seal fresh run bundles and verify their files before offline analysis."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asic_inputs(root):
    root = Path(root)
    manifest = root/'info.yaml'
    sources = [root/'src'/line.split('"')[1] for line in manifest.read_text().splitlines()
               if line.startswith('    - "')]
    return dict(manifest_sha256=sha(manifest),
                sources_sha256={path.relative_to(root).as_posix(): sha(path) for path in sources})


def seal(root):
    root = Path(root)
    files = {path.relative_to(root).as_posix(): dict(sha256=sha(path), bytes=path.stat().st_size)
             for path in sorted(root.rglob('*')) if path.is_file() and path != root/'artifacts.json'}
    with (root/'artifacts.json').open('x', encoding='utf-8') as stream:
        json.dump(dict(schema=1, files=files), stream, indent=2); stream.write('\n')
    return files


def verify(root):
    root = Path(root).resolve()
    index = json.loads((root/'artifacts.json').read_text())
    if index.get('schema') != 1 or not index.get('files'):
        raise ValueError('missing/invalid artifact index')
    for name, entry in index['files'].items():
        if (root/name).is_symlink():
            raise ValueError('artifact symlinks are not accepted: '+name)
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            raise ValueError('invalid/missing artifact path: '+name)
        if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError('artifact changed: '+name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root/'artifacts.json'}
    if actual != set(index['files']):
        raise ValueError('unindexed or missing files in immutable run bundle')
    return index
