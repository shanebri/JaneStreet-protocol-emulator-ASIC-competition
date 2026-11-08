"""Verify immutable streaming receipts after moving them into this worktree."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'docs/streaming/20261104'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    packaging=json.loads((EVIDENCE/'packaging.json').read_text())
    prefix=packaging['original_root'].rstrip('/')+'/'
    inventory=json.loads((EVIDENCE/'evidence_sha256.json').read_text())
    failures=[]
    for name,expected in inventory.items():
        if not name.startswith(prefix):
            failures.append('Unexpected original root: '+name);continue
        relative=Path(name[len(prefix):])
        archived=EVIDENCE/'source_snapshot'/relative
        target=archived if archived.is_file() else ROOT/relative
        if not target.is_file() or sha(target)!=expected:failures.append(str(relative))
    delivery=json.loads((EVIDENCE/'delivery.json').read_text())
    for field,target in (
        ('report_sha256',EVIDENCE/'source_snapshot/docs/streaming_20261104.md'),
        ('packet_interface_sha256',ROOT/'docs/packet_stream_interface_20261104.md'),
        ('evidence_index_sha256',EVIDENCE/'evidence_sha256.json')):
        if sha(target)!=delivery[field]:failures.append(field)
    for name,expected in packaging['source_snapshot_sha256'].items():
        target=EVIDENCE/'source_snapshot'/name
        if sha(target)!=expected:failures.append('snapshot: '+name)
    if failures:raise RuntimeError('Evidence changed: '+repr(failures))
    print(f'PASS: {len(inventory)} original evidence hashes, delivery seal and measured source snapshots')


if __name__=='__main__':main()
