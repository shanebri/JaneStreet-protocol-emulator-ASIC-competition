"""Prepare separate wiring-specific fixtures and commands; never program a board."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from bringup.capture import save_json
from bringup.artifacts import sha
from bringup.concurrent_protocols import port_key
from spi_hardware.peers import NANO_PEERS


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path)
    p.add_argument('--bridge-port')
    p.add_argument('--nano-port')
    p.add_argument('--uart-peer-port')
    p.add_argument('--out', type=Path)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--i2c-only', action='store_true', help='prepare a Nano 33 IoT I2C fixture using only the Arty control port')
    mode.add_argument('--baseline', action='store_true', help='prepare the complete revision-0x21 8x4 board checklist')
    p.add_argument('--nano-board', choices=NANO_PEERS)
    p.add_argument('--list-ports', action='store_true')
    a = p.parse_args(argv)
    if a.list_ports:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(f'{port.device}: {port.description} [{port.hwid}]')
        return 0
    if not all((a.image, a.bridge_port, a.out)):
        p.error('provide image, bridge port and a fresh output directory')
    if not a.i2c_only and not all((a.nano_port, a.uart_peer_port)):
        p.error('provide image, three distinct ports and a fresh output directory')
    if not a.i2c_only and len(set(map(port_key, (a.bridge_port, a.nano_port, a.uart_peer_port)))) != 3:
        p.error('bridge, Nano and UART peer ports must differ')
    image = a.image.resolve()
    image_hash = sha(image)
    if a.baseline:
        from bringup.baseline import check_revision
        check_revision(image_hash)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    base = dict(bridge_protocol=2, clock_hz=50_000_000, port=a.bridge_port,
                baud=115200, image=str(image), expected_image_sha256=image_hash,
                capture=dict(mode='none'))
    if a.i2c_only:
        config = json.loads(Path(__file__).with_name('fixture.example.json').read_text())['i2c']
        fixture = out/'i2c.json'
        save_json(fixture, dict(base, i2c=dict(config, target='nano33iot')))
        print(f'Prepared {fixture}; confirm the actual control port and Nano wiring before running.')
        return 0
    board = a.nano_board or ('nano33iot' if a.baseline else 'nano33ble')
    base.update(nano_port=a.nano_port, uart_peer_port=a.uart_peer_port, nano_board=board)
    fixtures = {}
    names = ['stress', 'boundaries', 'recovery', 'pads', 'concurrent']
    if a.baseline:
        names += ['smoke', 'uart', 'uart_rx', 'spi', 'i2c100']
    for name in names:
        fixture = json.loads(json.dumps(base))
        fixture['profile'] = name
        if name == 'stress':
            fixture['capture'] = dict(mode='fpga', loopbacks={'pad2':'out0', 'pad3':'out4'}, loopbacks_confirmed=False)
        elif name == 'recovery':
            fixture['capture'] = dict(mode='fpga', loopbacks={})
        elif name == 'pads':
            fixture['capture'] = dict(mode='fpga', loopbacks={})
            fixture['pads'] = dict(pullups_confirmed=False, active_peers_disconnected=False,
                                   pullup_ohms=[4700]*4, supply_v=3.3)
        elif name == 'concurrent':
            fixture['capture'] = dict(mode='fpga', decimation='auto',
                loopbacks={'pad0':'out0', 'pad1':'out2', 'pad2':'out3', 'pad3':'out1'}, loopbacks_confirmed=False)
            fixture['concurrent'] = dict(transfers=256, uart_baud=1200, spi_divider=8192,
                                         capture_rounds=[85, 170], timeout_seconds=5)
        elif name == 'uart_rx':
            fixture['uart_rx'] = dict(baud=115200, wiring_confirmed=False)
        elif name == 'i2c100':
            fixture['i2c'] = dict(target='nano33iot', address=0x50, nack_address=0x51,
                                  write_hex='00', expected_hex='50494f', timeout=5,
                                  rate=100000)
        path = out/(name+'.json')
        save_json(path, fixture)
        fixtures[name] = str(path)
    # This index describes generated files, not an acquired physical result.
    if a.baseline:
        from bringup.baseline import make_plan
        plan = make_plan(out, image_hash)
    else:
        plan = dict(status='PREPARED_NOT_RUN', image_sha256=image_hash,
            fixtures=fixtures, source_commit_note='Each actual run records its own commit, dirty state and harness hashes')
    save_json(out/'campaign.json', plan)
    commands = []
    suites = {name: name for name in names}
    suites.update(stress='dual_engine_stress', i2c100='i2c')
    for name in names:
        run = out/'runs'/name if a.baseline else Path('.bringup/runs')/(name+'-001')
        command = f'py tools/bringup/run.py --fixture "{out/name}.json" --suite {suites[name]} --out "{run}"'
        if name == 'stress':
            command += ' --rounds 1000 --duration-seconds 600'
        commands.append(command)
    guide = ['# Prepared FPGA campaign', '', 'No hardware has been programmed or tested by this preparation step.', '',
        f'Image: `{image}`', f'SHA256: `{image_hash}`', '',
        'Program the v2 image, identify all three COM ports, then use a separate wiring setup for each profile.',
        'Stress captures: JA1 (out0) -> JC3 (pad2); JB2 (out4) -> JC4 (pad3). Disconnect protocol peers.',
        f'Concurrent: {board} SPI on JA1/2/3/4/7; connect Arty JA3 to Nano {NANO_PEERS[board]["cs_pin"]}. USB UART RX on JB1 (out3).',
        'Concurrent capture: JA1 -> JC1, JA3 -> JC2, JB1 -> JC3 and JA2 -> JC4. UART adapter TX and VCC stay disconnected.',
        'Pads: remove all output loopbacks and active protocol peers; fit four known 3.3 V pullups to JC1..4.',
        'Keep the Arty USB control connection and shared signal grounds. Do not connect board supply outputs together.', '',
        'Confirm the actual loopbacks/pullups in the corresponding fixture only after wiring.',
        'Use --capture-mode none for an explicitly functional-only stress/concurrent run.', '', '```powershell',
        *commands, '```', '',
        'After each run: py tools/bringup/analyze.py --run RUN --out NEW-ANALYSIS',
        'Add --require-physical-waveforms when physical-input capture evidence is required.',
        'Preserve failed runs and use a new run directory for every retry.', '']
    if a.baseline:
        guide.extend([
            'UART TX uses Arty JA1 to adapter RX. UART RX uses adapter TX to Arty JA4; disconnect Nano MISO from JA4.',
            'Set uart_rx.wiring_confirmed only after wiring the UART RX fixture.',
            'I2C uses Arty JC1 to Nano A4/SDA and JC2 to A5/SCL with 3.3 V pullups and shared ground.',
            'Upload the I2C target sketch for I2C, then restore the selected SPI sketch for SPI/concurrent runs.',
            'Analyze each run into the campaign analysis directory under its case name.',
            'The I2C baseline checks the response, unused-address NACK and idle bus at 100 kHz.',
            'For separate I2C waveform, rise-time and 400 kHz qualification, see docs/i2c.md.',
            'The complete wiring sequence and acceptance checks are in tools/bringup/BASELINE.md.', '',
            '```powershell',
            f'py tools/bringup/baseline.py --campaign "{out}" --rtl-results test/results.xml --bridge-run PATH_TO_COMPLETE_EXTENDED_RUN --out "{out}/report-001"',
            '```', ''])
    (out/'RUNBOOK.md').write_text('\n'.join(guide), encoding='utf-8')
    # Fixtures are operator-edited working inputs, so do not seal them as immutable evidence.
    print(f'Prepared fixtures and RUNBOOK.md in {out}; no physical tests performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
