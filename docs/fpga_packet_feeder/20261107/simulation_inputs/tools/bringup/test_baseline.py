"""Check baseline evidence rejection and the Nano variant's shared protocol."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bringup import baseline, prepare
from bringup.artifacts import asic_inputs, seal
from bringup.capture import save_json
from bringup.concurrent_protocols import HardwarePeers
from bringup.test_evidence import traffic
from spi_hardware.peers import nano_peer


class BaselineTests(unittest.TestCase):
    def test_prepared_8x4_checklist_and_missing_runs(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            root = Path(temp)
            image = root/'image.bit'
            image.write_bytes(b'image')
            campaign = root/'campaign'
            with patch.object(baseline, 'check_revision'):
                prepare.main(['--baseline', '--image', str(image), '--bridge-port', 'COM3',
                              '--nano-port', 'COM4', '--uart-peer-port', 'COM5', '--out', str(campaign)])
                plan = json.loads((campaign/'campaign.json').read_text())
                self.assertEqual(set(plan['cases']), set(baseline.CASES))
                for name in ('i2c100', 'i2c400'):
                    fixture = json.loads((campaign/(name+'.json')).read_text())
                    self.assertEqual(fixture['i2c']['rate'], 100000 if name == 'i2c100' else 400000)
                    self.assertEqual(fixture['i2c']['nack_address'], 0x51)
                fixture = json.loads((campaign/'concurrent.json').read_text())
                self.assertEqual(fixture['nano_board'], 'nano33iot')
                self.assertFalse(fixture['capture']['loopbacks_confirmed'])
                self.assertFalse(json.loads((campaign/'uart_rx.json').read_text())['uart_rx']['wiring_confirmed'])
                self.assertIn('Nano D8', (campaign/'RUNBOOK.md').read_text())
                self.assertEqual(baseline.main(['--campaign', str(campaign), '--out', str(root/'report')]), 2)
                report = json.loads((root/'report/baseline.json').read_text())
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertEqual(report['checks']['identity']['status'], 'PASS')
                self.assertEqual(len(report['checks']), len(baseline.CASES)+3)
                nested = campaign/'runs/smoke/report'
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    baseline.main(['--campaign', str(campaign), '--out', str(nested)])
                self.assertFalse(nested.exists())

    def test_uart_evidence_must_cover_every_byte_and_both_engines(self):
        inputs = asic_inputs(baseline.ROOT)
        plan = dict(image_sha256='a'*64, asic_inputs=inputs)
        with tempfile.TemporaryDirectory() as temp:
            for variant in ('valid', 'missing_byte', 'simulation', 'other_image'):
                with self.subTest(variant=variant):
                    run = Path(temp)/variant
                    run.mkdir()
                    payload = bytes(range(256)).hex()
                    manifest = dict(status='PASS', suite='uart_rx', asic_inputs=inputs,
                                    image_sha256='b'*64 if variant == 'other_image' else 'a'*64,
                                    evidence_kind='simulation' if variant == 'simulation' else 'hardware_transport',
                                    fixture=dict(uart_rx=dict(baud=115200)))
                    save_json(run/'manifest.json', manifest)
                    records = [dict(test='uart_rx_byte', status='PASS', engine=index, sequence=n,
                                    expected=n, observed=n) for index in (0, 1) for n in range(256)]
                    if variant == 'missing_byte':
                        records.pop()
                    records.extend(dict(test='uart_rx_engine', status='PASS', engine=index,
                                        expected_hex=payload, observed_hex=payload) for index in (0, 1))
                    (run/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
                    (run/'transport.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in traffic()))
                    seal(run)
                    if variant == 'valid':
                        self.assertEqual(baseline.check_case('uart_rx', dict(run=str(run)), plan)['status'], 'PASS')
                    else:
                        with self.assertRaises(ValueError):
                            baseline.check_case('uart_rx', dict(run=str(run)), plan)

    def test_peer_variants_and_invalid_board(self):
        for board, pin in (('nano33iot', 'D8'), ('nano33ble', 'D10')):
            fixture = dict(port='COM3', nano_port='COM4', uart_peer_port='COM5', nano_board=board)
            self.assertEqual(nano_peer(fixture)['cs_pin'], pin)
            with patch.dict(sys.modules, serial=SimpleNamespace(Serial=unittest.mock.MagicMock())) as modules:
                with HardwarePeers(fixture, lambda *_: None, 1200):
                    self.assertEqual(modules['serial'].Serial.call_count, 2)
        with self.assertRaises(ValueError):
            nano_peer(dict(nano_board='classic-nano'))

    def test_filtered_or_skipped_regression_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'results.xml'
            path.write_text('<testsuites><testsuite><testcase/><testcase><skipped/></testcase></testsuite></testsuites>')
            with self.assertRaises(ValueError):
                baseline.check_xml(path, 2)
