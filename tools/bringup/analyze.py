"""Verify immutable run bundles and decode digital capture evidence offline."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from bringup.artifacts import sha, seal, verify
from bringup.capture import save_json
from bringup.waveforms import analyze_capture
from bringup.traffic import summarize


def verify_records(manifest, records):
    failures = [record for record in records if record.get('status') == 'FAIL']
    for record in records:
        if record.get('type') == 'assertion' and record.get('status') == 'PASS':
            if record['expected'] != record['observed']:
                raise ValueError('saved PASS assertion has mismatched expected/observed values')
    if manifest.get('suite') == 'packet_feeder' and manifest['status'] == 'PASS':
        from streaming.usb_ls import symbols
        completions=[r for r in records if r.get('test') == 'feeder_completion']
        if len(completions) != len(manifest['packets']):
            raise ValueError('missing packet feeder completion records')
        for slot,(record,packet) in enumerate(zip(completions,manifest['packets'])):
            _,spec=symbols(bytes.fromhex(packet['payload_hex']),data1=packet['data1'])
            wanted=dict(result=0,words_sent=1+(spec['symbols']+3)//4,terminal_levels=0,terminal_errors=0)
            completion=record['completion']
            if (record.get('status') != 'PASS' or record['slot'] != slot
                    or record['expected'] != wanted or record['observed'] != wanted
                    or any(completion[key] != value for key,value in wanted.items())
                    or completion['state'] != 4 or completion['engine'] != packet['engine']
                    or completion['sequence'] != packet['sequence']):
                raise ValueError('packet feeder completion differs from the submitted packet')
    if manifest.get('suite') == 'uart_rx' and manifest['status'] == 'PASS':
        payload = bytes.fromhex(manifest['fixture'].get('uart_rx', {}).get('payload_hex', bytes(range(256)).hex()))
        summaries = [r for r in records if r.get('test') == 'uart_rx_engine' and r.get('status') == 'PASS']
        if sorted(r['engine'] for r in summaries) != [0, 1]:
            raise ValueError('UART RX must complete on both engines')
        for index in (0, 1):
            received = [r for r in records if r.get('test') == 'uart_rx_byte' and r.get('engine') == index]
            if (len(received) != len(payload)
                    or any(r.get('status') != 'PASS' or r['sequence'] != n
                           or r['expected'] != byte or r['observed'] != byte
                           for n, (r, byte) in enumerate(zip(received, payload)))):
                raise ValueError('UART RX byte sequence differs from the fixture')
            summary = next(r for r in summaries if r['engine'] == index)
            if summary['expected_hex'] != payload.hex() or summary['observed_hex'] != payload.hex():
                raise ValueError('UART RX summary differs from the byte records')
    if manifest.get('suite') == 'dual_engine_stress' and manifest['status'] == 'PASS':
        from bringup.stress import tagged_word
        words = [r for r in records if r.get('test') == 'dual_word' and r.get('status') == 'PASS']
        rng = random.Random(manifest['seed'] ^ 0xd0a1e)
        for sequence, record in enumerate(words):
            expected = [tagged_word(rng, i, sequence) for i in (0, 1)]
            if record['sequence'] != sequence or record['expected'] != expected or record['observed'] != expected:
                raise ValueError('stress stream does not match its deterministic seed/order/bank tags')
        if len(words) < manifest['rounds']:
            raise ValueError('stress run has fewer scored rounds than requested')
    if manifest.get('suite') == 'concurrent' and manifest['status'] == 'PASS':
        rounds = [r for r in records if r.get('test') == 'concurrent_round' and r.get('status') == 'PASS']
        count = manifest['fixture'].get('concurrent', {}).get('transfers', 256)
        if len(rounds) != count:
            raise ValueError('missing concurrent protocol rounds')
        rng = random.Random(manifest['seed'])
        for sequence, record in enumerate(rounds):
            payload = bytes(rng.randrange(256) for _ in range(4)).hex()
            expected, observed = record['expected'], record['observed']
            nano = observed['nano'].split()
            if (record['sequence'] != sequence or expected != dict(uart_hex=payload, spi_mosi=sequence, spi_miso=sequence ^ 0xa5)
                    or observed['uart_hex'] != payload or observed['spi_miso'] != sequence ^ 0xa5
                    or nano != ['RX', str(sequence), str(sequence), str(sequence ^ 0xa5), '1', '1']):
                raise ValueError('concurrent peer data/order differs from the deterministic plan')
    return failures


def i2c_expectation(config, records, case):
    if case not in (0, 1) or (case == 1 and config.get('nack_address') is None):
        raise ValueError('I2C case 0 is the target read and case 1 is the optional address NACK')
    label = ('i2c_target', 'i2c_address_nack')[case]
    matches = [r for r in records if r.get('test') == label and r.get('status') == 'PASS']
    if len(matches) != 1:
        raise ValueError('external I2C capture must name one passing fixture case')
    if case == 1:
        address = config['nack_address']
        phases = [[dict(byte=address << 1, ack=False)]]
        expected = dict(status='address_nack', data='', completed=0, idle_high=True)
    else:
        address = config['address']
        payload = bytes.fromhex(config.get('write_hex', ''))
        data = bytes.fromhex(config['expected_hex'])
        if not data:
            raise ValueError('I2C capture expects a nonempty read')
        read = [dict(byte=(address << 1) | 1, ack=True)]
        read.extend(dict(byte=byte, ack=i < len(data)-1) for i, byte in enumerate(data))
        phases = [[dict(byte=address << 1, ack=True),
                   *[dict(byte=byte, ack=True) for byte in payload]], read] if payload else [read]
        expected = dict(status='success', data=data.hex(), completed=len(payload)+len(data), idle_high=True)
    record = matches[0]
    if case == 0 and 'observed' not in record:
        # The earlier positive-only runner recorded just the returned bytes.
        if record['received'] != expected['data']:
            raise ValueError('saved I2C response differs from the fixture')
    elif record.get('address') != address or record.get('observed') != expected:
        raise ValueError('saved I2C result differs from the fixture')
    return dict(kind='i2c', rate=config.get('rate', 100_000), phases=phases)


def import_external(out, run, manifest, source, mapping_path, case, rise_source=None):
    mapping = json.loads(mapping_path.read_text())
    if mapping.get('image_sha256') != manifest['image_sha256'] or not mapping.get('instrument'):
        raise ValueError('external capture mapping must identify its instrument and this exact image hash')
    records = [json.loads(line) for line in (run/'results.jsonl').read_text().splitlines() if line]
    if manifest['suite'] == 'i2c':
        expected = i2c_expectation(manifest['fixture']['i2c'], records, case)
        channels = mapping['channels']
        if not {'sda', 'scl'} <= channels.keys() or channels['sda'] == channels['scl']:
            raise ValueError('I2C mapping requires distinct sda and scl columns')
        if rise_source is not None and 'rise_supply_v' not in mapping:
            raise ValueError('I2C scope measurements require rise_supply_v in the mapping')
    else:
        if rise_source is not None:
            raise ValueError('scope rise-time CSV is supported only for the I2C suite')
        match = [r for r in records if r.get('test') == 'concurrent_round' and r.get('status') == 'PASS' and r['sequence'] == case]
        if len(match) != 1 or manifest['suite'] != 'concurrent':
            raise ValueError('external capture must name one scored concurrent round')
        config = manifest['fixture']['concurrent']
        baud = manifest['fixture']['clock_hz']/(14*round(manifest['fixture']['clock_hz']/(14*config.get('uart_baud', 1200))))
        expected = dict(kind='uart_spi', uart_hex=match[0]['expected']['uart_hex'],
            spi_mosi=case, spi_miso=case ^ 0xa5, uart_baud=baud,
            spi_clock_hz=manifest['fixture']['clock_hz']/(16*config.get('spi_divider', 8192)),
            uart_channel='uart', sclk_channel='sclk', mosi_channel='mosi', miso_channel='miso', cs_channel='cs')
    directory = out/'imported-capture'
    directory.mkdir()
    shutil.copy2(source, directory/'samples.csv')
    shutil.copy2(mapping_path, directory/'mapping.json')
    if rise_source is not None:
        shutil.copy2(rise_source, directory/'rise.csv')
    save_json(directory/'capture.json', dict(status='COMPLETE', evidence_kind=manifest['evidence_kind'],
        source='external_instrument', instrument=mapping['instrument'], expected=expected,
        image_sha256=manifest['image_sha256'], csv_mapping=mapping,
        signal_scope={name:'physical_input' for name in mapping['channels']},
        fixture_loopbacks={}, trigger=mapping.get('trigger', {})))
    return directory


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='new analysis directory; source run is never edited')
    p.add_argument('--require-physical-waveforms', action='store_true')
    p.add_argument('--import-csv', type=Path)
    p.add_argument('--mapping', type=Path)
    p.add_argument('--case', type=int, default=0, help='concurrent round or I2C case (0=target, 1=NACK)')
    p.add_argument('--rise-csv', type=Path, help='optional I2C scope voltage CSV (time_s,sda_v,scl_v)')
    a = p.parse_args(argv)
    if bool(a.import_csv) != bool(a.mapping):
        p.error('--import-csv and --mapping are used together')
    if a.rise_csv and not a.import_csv:
        p.error('--rise-csv requires the digital --import-csv and --mapping')
    run, out = a.run.resolve(), a.out.resolve()
    if out.is_relative_to(run):
        p.error('analysis output must be outside the immutable source run')
    out.mkdir(parents=True, exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    result = dict(status='FAIL', created_utc=datetime.now(timezone.utc).isoformat(),
                  source_run=str(run), captures=[], complete_electrical_qualification=False)
    code = 1
    try:
        index = verify(run)
        manifest = json.loads((run/'manifest.json').read_text())
        result.update(integrity='PASS', source_index_sha256=sha(run/'artifacts.json'),
                      image_sha256=manifest['image_sha256'], seed=manifest['seed'], suite=manifest['suite'],
                      evidence_kind=manifest['evidence_kind'],
                      functional_status=manifest['status'])
        result['host_traffic'] = summarize([json.loads(line) for line in (run/'transport.jsonl').read_text().splitlines() if line])
        records = [json.loads(line) for line in (run/'results.jsonl').read_text().splitlines() if line]
        failures = verify_records(manifest, records)
        if manifest['suite'] == 'i2c' and manifest['status'] == 'PASS':
            config = manifest['fixture']['i2c']
            i2c_expectation(config, records, 0)
            if config.get('nack_address') is not None:
                i2c_expectation(config, records, 1)
        result['failed_records'] = failures
        result['assertion_summary'] = {}
        for record in records:
            if record.get('type') == 'assertion':
                counts = result['assertion_summary'].setdefault(record.get('test', 'unnamed'), dict(passed=0, failed=0))
                counts['passed' if record.get('status') == 'PASS' else 'failed'] += 1
        directories = [path.parent for path in sorted(run.glob('captures/*/capture.json'))]
        if a.import_csv:
            directories.append(import_external(out, run, manifest, a.import_csv, a.mapping, a.case, a.rise_csv))
        for directory in directories:
            try:
                item = analyze_capture(directory)
                metadata = json.loads((directory/'capture.json').read_text())
                if metadata.get('source') == 'external_instrument':
                    item['physical_input_evidence'] = manifest['evidence_kind'] == 'hardware_transport'
                item['path'] = str(directory)
            except (OSError, ValueError, KeyError) as exc:
                item = dict(status='FAIL', path=str(directory), error=str(exc))
            result['captures'].append(item)
        physical = [c for c in result['captures'] if c['status'] == 'PASS' and c.get('physical_input_evidence')]
        result['physical_digital_captures_validated'] = len(physical)
        result['waveform_status'] = ('NOT_ACQUIRED' if not directories else
            ('FAIL' if any(c['status'] == 'FAIL' for c in result['captures']) else 'DIGITAL_DECODE_PASS'))
        if (manifest['status'] != 'PASS' or failures or result['waveform_status'] == 'FAIL'
                or result['host_traffic']['status'] != 'PASS'):
            raise ValueError('recorded functional/capture checks failed')
        if any(c.get('rise_time', {}).get('status') == 'FAIL' for c in result['captures']):
            raise ValueError('measured I2C rise time exceeds the selected mode limit')
        if a.require_physical_waveforms and not physical:
            result.update(status='INCOMPLETE', error='no validated physical-input waveform capture'); code = 2
        else:
            result['status'] = 'PASS'; code = 0
        result['scope'] = 'functional results, sampled digital evidence and any reported I2C rise measurements'
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status='FAIL', error=str(exc)); code = 1
    save_json(out/'analysis.json', result)
    lines = ['# Bring-up analysis', '', f'Verdict: **{result["status"]}**', '',
             f'Source run: `{run}`', '', '| Check | Result |', '| --- | --- |',
             f'| Artifact integrity | {result.get("integrity", "FAIL")} |',
             f'| Functional profile | {result.get("functional_status", "UNKNOWN")} |',
             f'| Raw host packets | {result.get("host_traffic", {}).get("status", "UNKNOWN")} |',
             f'| Digital waveforms | {result.get("waveform_status", "UNKNOWN")} |',
             f'| Physical digital captures validated | {result.get("physical_digital_captures_validated", 0)} |',
             '| Complete electrical qualification | NOT ESTABLISHED |', '']
    for capture in result['captures']:
        lines.append(f'- {capture["path"]}: {capture["status"]}; {capture.get("error", capture.get("scope", ""))}')
        rise = capture.get('rise_time', {})
        if rise.get('max_ns'):
            lines.append(f'  - I2C rise time {rise["status"]}, SDA {rise["max_ns"]["sda"]:.1f} ns, '
                         f'SCL {rise["max_ns"]["scl"]:.1f} ns, mode limit {rise["limit_ns"]} ns.')
    if result.get('assertion_summary'):
        lines.extend(['', '| Assertion | Passed | Failed |', '| --- | ---: | ---: |'])
        lines.extend(f'| {name} | {counts["passed"]} | {counts["failed"]} |'
                     for name, counts in result['assertion_summary'].items())
    if result.get('error'):
        lines.extend(['', result['error']])
    (out/'analysis.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    with (out/'decoded_transactions.jsonl').open('x', encoding='utf-8') as decoded:
        for capture in result['captures']:
            for protocol in ('uart', 'spi', 'i2c', 'usb_feeder'):
                for frame in capture.get(protocol, []):
                    decoded.write(json.dumps(dict(capture=capture['path'], protocol=protocol, **frame))+'\n')
    seal(out)
    print(json.dumps(result, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
