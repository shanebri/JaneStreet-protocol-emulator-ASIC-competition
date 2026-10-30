"""Explicit local dependency bridge for system Python embedded in Nix Icarus."""
import hashlib
from pathlib import Path

EXPAT=Path('/nix/store/d8927sznk6qnqln6hl9p4d42h8pq49vg-expat-2.8.0/lib')


def gate_environment(environment):
    library=EXPAT/'libexpat.so.1'
    if not library.is_file(): raise ValueError('Pinned gate-runtime expat library is unavailable')
    result=dict(environment)
    result['LD_LIBRARY_PATH']=':'.join(filter(None,(str(EXPAT),result.get('LD_LIBRARY_PATH',''))))
    return result


def provenance():
    library=(EXPAT/'libexpat.so.1').resolve()
    return dict(scope='Gate simulation runtime only; no RTL/PDK/timing constraints modified',
        expat_library=str(library),sha256=hashlib.sha256(library.read_bytes()).hexdigest())
