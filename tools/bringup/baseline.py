"""Collect the fixed revision-0x21 8x4 board checklist before a baseline freeze."""
import argparse
import json
from pathlib import Path
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from bringup.analyze import i2c_expectation, verify_records
from bringup.artifacts import asic_inputs, seal, sha, verify
from bringup.capture import save_json
from bringup.traffic import summarize

CASES = dict(smoke='smoke', uart='uart', uart_rx='uart_rx', spi='spi',
             i2c100='i2c', stress='dual_engine_stress',
             boundaries='boundaries', recovery='recovery', pads='pads', concurrent='concurrent')
CAPTURES = {'stress', 'pads', 'concurrent'}


def check_revision(image_hash):
    manifest = (ROOT/'info.yaml').read_text()
    if 'tiles: "8x4"' not in manifest:
        raise ValueError('this baseline checklist requires the 8x4 allocation')
    receipt = json.loads((ROOT/'docs/fpga_bringup_v2_20261101_receipt.json').read_text())
    if image_hash != receipt['image_sha256']:
        raise ValueError('baseline checklist requires the qualified 20261101-v2-18 image')
    candidate = ROOT/receipt['candidate']
    if sha(candidate/'artifacts.json') != receipt['index_sha256']:
        raise ValueError('preserved FPGA candidate index differs from the qualification receipt')
    index = json.loads((candidate/'artifacts.json').read_text())
    qualification = candidate/'qualification.json'
    if sha(qualification) != index['files']['qualification.json']['sha256']:
        raise ValueError('preserved FPGA qualification metadata changed')
    sources = json.loads(qualification.read_text())['sources_sha256']
    sources = {name.replace('\\', '/'): digest for name, digest in sources.items()}
    current = asic_inputs(ROOT)['sources_sha256']
    qualified = {name: digest for name, digest in sources.items() if name.startswith('src/')}
    if current != qualified:
        raise ValueError('ASIC RTL differs from the selected qualified FPGA image')
    if any(sha(ROOT/name) != digest for name, digest in sources.items()):
        raise ValueError('FPGA build inputs differ from the selected qualified image')


def make_plan(out, image_hash):
    check_revision(image_hash)
    return dict(schema=1, status='PREPARED_NOT_RUN', revision=0x21, tiles='8x4',
                image_sha256=image_hash, asic_inputs=asic_inputs(ROOT),
                cases={name: dict(suite=suite, fixture=str(out/(name+'.json')),
                                 run=str(out/'runs'/name), analysis=str(out/'analysis'/name))
                       for name, suite in CASES.items()})


def read_records(run):
    return [json.loads(line) for line in (run/'results.jsonl').read_text().splitlines() if line]


def check_case(name, entry, plan):
    run = Path(entry['run'])
    verify(run)
    manifest = json.loads((run/'manifest.json').read_text())
    if (manifest['status'] != 'PASS' or manifest['suite'] != CASES[name]
            or manifest['evidence_kind'] != 'hardware_transport'
            or manifest['image_sha256'] != plan['image_sha256']
            or manifest.get('asic_inputs') != plan['asic_inputs']):
        raise ValueError('run must pass on the selected image and exact 8x4 ASIC inputs')
    records = read_records(run)
    if verify_records(manifest, records):
        raise ValueError('run contains failed records')
    packets = [json.loads(line) for line in (run/'transport.jsonl').read_text().splitlines() if line]
    if summarize(packets)['status'] != 'PASS':
        raise ValueError('host packet validation failed')
    passed = [r for r in records if r.get('status') == 'PASS']
    summary_name = dict(uart='uart_peer_256', uart_rx='uart_rx_engine',
                        spi='spi_peer_256', stress='dual_engine_stress').get(name, name)
    if name == 'smoke':
        from bringup.scenarios import SCENARIOS
        if not {case.__name__ for case in SCENARIOS} <= {r.get('test') for r in passed}:
            raise ValueError('smoke run is missing a scenario')
    elif name != 'i2c100' and not any(r.get('test') == summary_name for r in passed):
        raise ValueError('run is missing its completion record')
    if name in ('uart', 'spi') and not any(
            r.get('test') == summary_name and r.get('transfers') == 256 for r in passed):
        raise ValueError('standalone UART/SPI requires all 256 transfers')
    if name == 'uart_rx':
        engines = [r for r in passed if r.get('test') == 'uart_rx_engine']
        expected = bytes(range(256)).hex()
        if (manifest['fixture'].get('uart_rx', {}).get('baud', 115200) != 115200
                or sorted(r['engine'] for r in engines) != [0, 1]
                or any(r['expected_hex'] != expected or r['observed_hex'] != expected for r in engines)):
            raise ValueError('UART RX must verify all 256 values on both engines at 115200 baud')
    elif name == 'stress':
        summaries = [r for r in passed if r.get('test') == 'dual_engine_stress']
        if (len(summaries) != 1 or summaries[0]['rounds'] < 1000
                or summaries[0].get('elapsed_seconds', 0) < 600):
            raise ValueError('stress requires at least 1000 rounds and 600 seconds')
        progress = [r for r in passed if r.get('test') == 'continued_engine_progress']
        if any(sum(r.get('engine') == index for r in progress) < 8 for index in (0, 1)):
            raise ValueError('stress must observe both engines progressing during host traffic')
    elif name == 'concurrent':
        if manifest['fixture'].get('concurrent', {}).get('transfers', 256) != 256:
            raise ValueError('concurrent run requires all 256 SPI and 1024 UART bytes')
    elif name == 'i2c100':
        config = manifest['fixture']['i2c']
        if config.get('rate', 100000) != 100000:
            raise ValueError('functional I2C baseline requires the 100 kHz fixture')
        i2c_expectation(config, records, 0)
        i2c_expectation(config, records, 1)
    if name in CAPTURES:
        analysis = Path(entry['analysis'])
        verify(analysis)
        result = json.loads((analysis/'analysis.json').read_text())
        if (result['status'] != 'PASS' or result['source_index_sha256'] != sha(run/'artifacts.json')
                or result.get('physical_digital_captures_validated', 0) < 1):
            raise ValueError('passing physical waveform analysis must reference this exact run')
        if name == 'pads':
            releases = {(c.get('expectation', {}).get('owner'), c.get('expectation', {}).get('pad'))
                        for c in result['captures'] if c.get('kind') == 'open_drain' and c['status'] == 'PASS'}
            if releases != {(owner, pad) for owner in (0, 1) for pad in range(4)}:
                raise ValueError('pad captures must cover every pad and both owners')
            if not any(c.get('kind') == 'reset' and c['status'] == 'PASS' for c in result['captures']):
                raise ValueError('pad reset-release capture is missing')
        elif name == 'concurrent':
            sequences = {c.get('expectation', {}).get('sequence') for c in result['captures']
                         if c.get('kind') == 'uart_spi' and c['status'] == 'PASS'}
            if not {85, 170} <= sequences:
                raise ValueError('concurrent run requires captured rounds 85 and 170')
        elif name == 'stress' and not any(c.get('kind') == 'markers' for c in result['captures']):
            raise ValueError('continuous marker capture is missing')
    return dict(status='PASS', run=str(run), artifact_index_sha256=sha(run/'artifacts.json'))


def check_xml(path, count):
    tree = ElementTree.parse(path)
    if (len(tree.findall('.//testcase')) != count or tree.findall('.//failure')
            or tree.findall('.//error') or tree.findall('.//skipped')):
        raise ValueError(f'regression requires {count} passing cases with no skips')
    return dict(status='PASS', results=str(path), sha256=sha(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rtl-results', type=Path)
    parser.add_argument('--bridge-run', type=Path)
    args = parser.parse_args(argv)
    plan_path = args.campaign/'campaign.json'
    plan = json.loads(plan_path.read_text())
    out = args.out.resolve()
    protected = [Path(entry[key]).resolve() for entry in plan['cases'].values() for key in ('run', 'analysis')]
    if args.bridge_run:
        protected.append(args.bridge_run.resolve())
    if any(out.is_relative_to(path) for path in protected):
        parser.error('report output must be outside the source runs and analyses')
    out.mkdir(parents=True, exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    result = dict(status='INCOMPLETE', revision=0x21, tiles='8x4',
                  plan_sha256=sha(plan_path), checks={})

    def record(name, operation):
        try:
            result['checks'][name] = operation()
        except FileNotFoundError as exc:
            result['checks'][name] = dict(status='PENDING', error=str(exc))
        except (OSError, ValueError, KeyError, TypeError, IndexError, ElementTree.ParseError) as exc:
            result['checks'][name] = dict(status='FAIL', error=str(exc))

    def identity():
        check_revision(plan['image_sha256'])
        if plan.get('schema') != 1 or plan.get('revision') != 0x21 or plan.get('tiles') != '8x4':
            raise ValueError('campaign does not identify revision 0x21 on 8x4')
        if plan['asic_inputs'] != asic_inputs(ROOT):
            raise ValueError('ASIC inputs changed since campaign preparation')
        return dict(status='PASS', asic_inputs=plan['asic_inputs'], image_sha256=plan['image_sha256'])

    def bridge():
        if args.bridge_run is None:
            raise ValueError('supply --bridge-run for the complete extended simulation')
        metadata = json.loads((args.bridge_run/'run.json').read_text())
        if metadata['status'] != 'PASS' or metadata.get('test_filter') or metadata['kind'] != 'extended':
            raise ValueError('extended simulation must pass its complete suite')
        sources = {path.replace('\\', '/'): value for path, value in metadata['source_sha256'].items()}
        for name, digest in plan['asic_inputs']['sources_sha256'].items():
            matches = [value for path, value in sources.items() if path.endswith('/'+name)]
            if matches != [digest]:
                raise ValueError('bridge simulation used different ASIC RTL')
        return check_xml(args.bridge_run/'results.xml', 7)

    def rtl():
        if args.rtl_results is None:
            raise ValueError('supply --rtl-results for the 39-test regression')
        return check_xml(args.rtl_results, 39)

    record('identity', identity)
    record('rtl_regression', rtl)
    record('bridge_regression', bridge)
    for name in CASES:
        record(name, lambda name=name: check_case(name, plan['cases'][name], plan))
    if all(check['status'] == 'PASS' for check in result['checks'].values()):
        result['status'] = 'READY_FOR_FREEZE'
    save_json(out/'baseline.json', result)
    lines = ['# Revision 0x21 8x4 functional baseline checklist', '', result['status'], '',
             'I2C covers functional operation at 100 kHz. Physical waveform and rise-time',
             'qualification and the 400 kHz board test are separate.', '',
             '| Check | Result |', '| --- | --- |']
    lines.extend(f'| {name} | {check["status"]} |' for name, check in result['checks'].items())
    for name, check in result['checks'].items():
        if check.get('error'):
            lines.extend(['', f'{name} — {check["error"]}'])
    (out/'baseline.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    seal(out)
    print(f'{result["status"]} — {out/"baseline.md"}')
    return 0 if result['status'] == 'READY_FOR_FREEZE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
