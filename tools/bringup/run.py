"""Run from repo root: python tools/bringup/run.py --fixture fixture.json --out run-dir."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from bringup.transport import SerialTransport
from bringup.scenarios import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--seed', type=int, default=2201)
    p.add_argument('--suite', choices=('smoke','uart','spi','i2c'), default='smoke')
    p.add_argument('--repeat',type=int,default=1,help='repeat smoke with successive seeds')
    a = p.parse_args()
    if a.repeat<1 or (a.repeat!=1 and a.suite!='smoke'):
        p.error('--repeat must be positive and is supported only for smoke')
    fixture = json.loads(a.fixture.read_text())
    if fixture.get('bridge_protocol') != 1 or fixture.get('clock_hz') != 50_000_000:
        p.error('requires bridge_protocol=1 and clock_hz=50000000')
    image = Path(fixture['image']).resolve()
    image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'.gitignore').write_text('*\n')
    manifest = dict(status='RUNNING', fixture=fixture, image_sha256=image_hash,
                    suite=a.suite, seed=a.seed, repeat=a.repeat, started=datetime.now(timezone.utc).isoformat(),
                    commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                    dirty=bool(subprocess.check_output(['git','status','--porcelain'], cwd=ROOT)),
                    verdict='functional suite only; no electrical or waveform qualification')
    manifest['firmware_sha256']={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted((ROOT/'examples').glob('*.asm'))}
    code = 1
    with (a.out/'results.jsonl').open('w') as results, (a.out/'transport.jsonl').open('w') as raw:
        def emit(record):
            results.write(json.dumps(record)+'\n'); results.flush()
            print(json.dumps(record))
        def trace(direction, data):
            raw.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), direction=direction, data=data))+'\n')
            raw.flush()
        try:
            import serial
            with serial.Serial(fixture['port'], fixture.get('baud',115200), timeout=0.05,
                               write_timeout=2, rtscts=False, dsrdtr=False) as port:
                io=SerialTransport(port, trace=trace)
                if a.suite=='smoke':
                    async def repeated():
                        for iteration in range(a.repeat):
                            await run(io,a.seed+iteration,
                                      lambda record: emit(dict(record,iteration=iteration,seed=a.seed+iteration)))
                    asyncio.run(repeated())
                else:
                    from bringup import protocols
                    asyncio.run(getattr(protocols,a.suite)(io,fixture,emit,trace))
            manifest['status'] = 'PASS'; code = 0
        except Exception as exc:
            manifest.update(status='FAIL', error=str(exc))
            emit(dict(test='session', status='FAIL', error=str(exc)))
        finally:
            manifest['finished'] = datetime.now(timezone.utc).isoformat()
            (a.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return code


if __name__ == '__main__':
    sys.exit(main())
