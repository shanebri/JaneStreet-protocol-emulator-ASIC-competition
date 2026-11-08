"""Run reproducible hardware profiles, preserving packets, expectations and captures."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from bringup.transport import SerialTransport
from bringup.scenarios import run as smoke
from bringup.capture import Recorder, save_json
from bringup.artifacts import asic_inputs, seal
from spi_hardware.peers import nano_peer

SUITES = ('smoke', 'uart', 'uart_rx', 'spi', 'i2c', 'dual_engine_stress', 'boundaries', 'recovery', 'pads', 'concurrent')
EXTENDED = ('uart_rx', 'dual_engine_stress', 'boundaries', 'recovery', 'pads', 'concurrent')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='fresh output directory')
    p.add_argument('--seed', type=int, default=2201)
    p.add_argument('--suite', choices=SUITES, default='smoke')
    p.add_argument('--repeat', type=int, default=1, help='smoke repetitions with successive seeds')
    p.add_argument('--rounds', type=int, default=64, help='minimum dual-engine echo rounds')
    p.add_argument('--duration-seconds', type=float, default=0, help='minimum stress duration in addition to --rounds')
    p.add_argument('--capture-mode', choices=('none', 'fpga'), help='explicit override recorded in the saved fixture')
    a = p.parse_args(argv)
    if a.repeat < 1 or (a.repeat != 1 and a.suite != 'smoke'):
        p.error('--repeat is positive and supported only for smoke')
    if a.rounds < 1 or not 0 <= a.duration_seconds <= 86400:
        p.error('positive --rounds and --duration-seconds in 0..86400 are required')
    fixture_path = a.fixture.resolve()
    fixture = json.loads(fixture_path.read_text())
    if a.capture_mode:
        fixture.setdefault('capture', {})['mode'] = a.capture_mode
    if fixture.get('bridge_protocol') not in (1, 2) or fixture.get('clock_hz') != 50_000_000:
        p.error('requires bridge_protocol 1/2 and clock_hz=50000000')
    if a.suite in EXTENDED and fixture['bridge_protocol'] != 2:
        p.error('extended suites require a new bridge v2 image and fixture')
    if a.suite == 'i2c' and fixture.get('capture', {}).get('mode', 'none') != 'none':
        p.error('use an external instrument for the full I2C transaction')
    image = Path(fixture['image'])
    image = (fixture_path.parent/image).resolve() if not image.is_absolute() else image.resolve()
    image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    if fixture.get('expected_image_sha256', image_hash) != image_hash:
        p.error('image file no longer matches the fixture hash')
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    save_json(out/'fixture.json', fixture)
    harness = [*sorted((ROOT/'tools/bringup').glob('*.py')), ROOT/'tools/pio_host.py', ROOT/'tools/pioasm.py',
               ROOT/'tools/spi_hardware/check_spi.py']
    if a.suite == 'i2c':
        harness.append(ROOT/'tools/i2c_driver.py')
    manifest = dict(schema=2, status='RUNNING', functional_status='RUNNING',
        evidence_kind='hardware_transport', fixture=fixture, image=str(image), image_sha256=image_hash,
        image_identity_scope='hash of operator-selected file; protocol handshake is not bitstream readback',
        suite=a.suite, seed=a.seed, repeat=a.repeat, rounds=a.rounds, duration_seconds=a.duration_seconds,
        python_version=sys.version, platform=sys.platform,
        started=datetime.now(timezone.utc).isoformat(),
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.PIPE).strip(),
        asic_inputs=asic_inputs(ROOT),
        dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, stderr=subprocess.PIPE)),
        harness_sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in harness},
        firmware_sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted((ROOT/'examples').glob('*.asm'))},
        verdict='functional profile; sampled digital captures are classified per channel; analog electrical qualification is separate')
    if a.suite in ('spi', 'concurrent'):
        manifest['peer_sketch_sha256'] = hashlib.sha256(
            nano_peer(fixture)['sketch'].read_bytes()).hexdigest()
        manifest['nano_board'] = fixture.get('nano_board', 'nano33ble')
    elif a.suite == 'i2c' and fixture['i2c'].get('target') == 'nano33iot':
        manifest['peer_sketch_sha256'] = hashlib.sha256(
            (ROOT/'tools/bringup/nano33iot_i2c_target/nano33iot_i2c_target.ino').read_bytes()).hexdigest()
        manifest['peer_sketch_identity_scope'] = 'fixture-selected source; target firmware is not read back'
    save_json(out/'manifest.json', manifest)
    code, recorder, records = 1, None, []
    with (out/'results.jsonl').open('w', encoding='utf-8') as results, (out/'transport.jsonl').open('w', encoding='utf-8') as raw:
        def emit(record):
            item = dict(seed=a.seed, monotonic_ns=time.monotonic_ns(), **{k:v for k,v in record.items() if k != 'seed'})
            if 'seed' in record:
                item['seed'] = record['seed']
            records.append(item)
            results.write(json.dumps(item)+'\n'); results.flush()
            print(json.dumps(item), flush=True)

        def trace(direction, data):
            raw.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),
                monotonic_ns=time.monotonic_ns(), direction=direction, data=data))+'\n')
            raw.flush()

        try:
            import serial
            manifest['pyserial_version'] = getattr(serial, '__version__', 'unknown')
            with serial.Serial(fixture['port'], fixture.get('baud', 115200), timeout=.05,
                               write_timeout=2, rtscts=False, dsrdtr=False) as port:
                io = SerialTransport(port, timeout=fixture.get('command_timeout', 2), trace=trace)

                async def execute():
                    nonlocal recorder
                    if fixture['bridge_protocol'] == 2:
                        manifest['bridge_version_observed'] = await io.require_v2()
                    recorder = Recorder(io, out, fixture, emit, image_sha256=image_hash)
                    if a.suite == 'smoke':
                        for iteration in range(a.repeat):
                            await smoke(io, a.seed+iteration,
                                lambda record: emit(dict(record, iteration=iteration, seed=a.seed+iteration)))
                    elif a.suite in ('uart', 'uart_rx', 'spi', 'i2c'):
                        from bringup import protocols
                        await getattr(protocols, a.suite)(io, fixture, emit, trace)
                    elif a.suite == 'concurrent':
                        from bringup.concurrent_protocols import concurrent
                        await concurrent(io, fixture, a.seed, emit, trace, recorder=recorder)
                    else:
                        from bringup import stress
                        await getattr(stress, a.suite)(io, a.seed, emit, fixture=fixture,
                            rounds=a.rounds, duration_seconds=a.duration_seconds, recorder=recorder)
                asyncio.run(execute())
            if any(record.get('status') == 'FAIL' for record in records):
                raise AssertionError('profile emitted a failed assertion')
            manifest.update(status='PASS', functional_status='PASS'); code = 0
        except BaseException as exc:
            manifest.update(status='FAIL', functional_status='FAIL', error=str(exc))
            (out/'exception.txt').write_text(traceback.format_exc(), encoding='utf-8')
            emit(dict(test='session', status='FAIL', error=str(exc),
                      recovery='preserve this bundle; reset bridge before a fresh run after indeterminate transport failure'))
            code = 130 if isinstance(exc, KeyboardInterrupt) else 1
            if recorder is not None and recorder.current is not None:
                directory, metadata = recorder.current
                metadata.update(status='FAIL', error='session ended before capture retrieval: '+str(exc))
                save_json(directory/'capture.json', metadata)
        finally:
            manifest['finished'] = datetime.now(timezone.utc).isoformat()
            manifest['assertions'] = dict(passed=sum(r.get('status') == 'PASS' and r.get('type') == 'assertion' for r in records),
                                          failed=sum(r.get('status') == 'FAIL' and r.get('type') == 'assertion' for r in records))
            manifest['digital_captures_complete'] = sum(
                json.loads(path.read_text()).get('status') == 'COMPLETE' for path in out.glob('captures/*/capture.json'))
            manifest['waveform_status'] = 'ACQUIRED_REQUIRES_ANALYSIS' if manifest['digital_captures_complete'] else 'NOT_ACQUIRED'
            save_json(out/'manifest.json', manifest)
    seal(out)
    print(f'Bundle: {out}\nFunctional status: {manifest["status"]}; waveform status: {manifest["waveform_status"]}')
    print('Analyze: '+subprocess.list2cmdline([sys.executable, str(ROOT/'tools/bringup/analyze.py'), '--run', str(out), '--out', str(out.parent/(out.name+'-analysis'))]))
    return code


if __name__ == '__main__':
    sys.exit(main())
