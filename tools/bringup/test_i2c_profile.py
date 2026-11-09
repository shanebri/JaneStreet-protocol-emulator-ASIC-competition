"""Regression checks for the I2C peer profile and external capture import."""
import asyncio
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bringup import analyze, prepare, protocols
from bringup.artifacts import seal, verify
from bringup.capture import save_json
from bringup.test_evidence import traffic
from bringup.waveforms import Waveform, decode_i2c, measure_i2c_rise
from i2c_driver import Result


CONFIG = dict(address=0x50, nack_address=0x51, rate=100_000, write_hex='00', expected_hex='50494f')


def transaction(phases):
    samples = [(1, 1)] * 4

    def hold(sda, scl):
        samples.extend([(sda, scl)] * 4)

    for frames in phases:
        if len(samples) > 4:
            hold(1, 0)
            hold(1, 1)
        hold(0, 1)
        hold(0, 0)
        for byte, ack_bit in frames:
            for bit in [*((byte >> n) & 1 for n in range(7, -1, -1)), ack_bit]:
                hold(bit, 0)
                hold(bit, 1)
                hold(bit, 0)
    hold(0, 0)
    hold(0, 1)
    hold(1, 1)
    return Waveform([i * 1e-6 for i in range(len(samples))],
                    dict(zip(('sda', 'scl'), map(list, zip(*samples)))))


def save_wave(path, wave):
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('seconds', 'D0', 'D1'))
        writer.writerows(zip(wave.times, wave.channels['sda'], wave.channels['scl']))


class I2CProfileTests(unittest.TestCase):
    def test_profile_scores_read_and_nack_and_releases_on_failure(self):
        for idle in (True, False):
            with self.subTest(idle=idle), patch.object(protocols, 'I2C') as cls:
                bridge = AsyncMock()
                bridge.poisoned = False
                bridge.read.side_effect = [0x0c, 0x0c if idle else 0x04]
                driver = cls.return_value
                driver.configure = AsyncMock()
                driver.transfer = AsyncMock(side_effect=[Result('success', 4, b'PIO'),
                                                         Result('address_nack', 0)])
                records = []
                run = protocols.i2c(bridge, dict(i2c=CONFIG), records.append, lambda *_: None)
                if idle:
                    asyncio.run(run)
                else:
                    with self.assertRaisesRegex(AssertionError, 'i2c_address_nack'):
                        asyncio.run(run)
                self.assertEqual(bridge.write.await_args.args, (0, 0x20))
                self.assertEqual([r['status'] for r in records], ['PASS', 'PASS' if idle else 'FAIL'])
                self.assertEqual(driver.transfer.await_args.args, (0x51, b'', 0))

    def test_i2c_only_fixture_and_external_capture_import(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            root = Path(temp)
            image = root/'candidate.bit'
            image.write_bytes(b'candidate')
            prepare.main(['--i2c-only', '--image', str(image), '--bridge-port', 'COM3',
                          '--out', str(root/'campaign')])
            fixture = json.loads((root/'campaign/i2c.json').read_text())
            self.assertEqual(fixture['i2c'], dict(CONFIG, timeout=5, target='nano33iot'))
            source = root/'run'
            source.mkdir()
            manifest = dict(status='PASS', suite='i2c', seed=2201, evidence_kind='simulation',
                            image_sha256=fixture['expected_image_sha256'], fixture=fixture)
            save_json(source/'manifest.json', manifest)
            records = [dict(test='i2c_target', address=0x50, status='PASS',
                            observed=dict(status='success', data='50494f', completed=4, idle_high=True)),
                       dict(test='i2c_address_nack', address=0x51, status='PASS',
                            observed=dict(status='address_nack', data='', completed=0, idle_high=True))]
            (source/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
            (source/'transport.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in traffic()))
            seal(source)
            scope = root/'scope.csv'
            scope.write_text('time_s,sda_v,scl_v\n' + ''.join(
                f'{i*20e-9},{min(3.3, i*.132)},{min(3.3, i*.264)}\n' for i in range(26)))
            mapping = root/'mapping.json'
            save_json(mapping, dict(instrument='synthetic', image_sha256=manifest['image_sha256'],
                      time_column='seconds', time_unit='s', channels=dict(sda='D0', scl='D1'),
                      rise_supply_v=3.3))
            for case, phases in enumerate((
                [[(0xa0, 0), (0, 0)], [(0xa1, 0), (0x50, 0), (0x49, 0), (0x4f, 1)]],
                [[(0xa2, 1)]],
            )):
                external = root/f'case-{case}.csv'
                save_wave(external, transaction(phases))
                output = root/f'analysis-{case}'
                code = analyze.main(['--run', str(source), '--out', str(output), '--case', str(case),
                                     '--import-csv', str(external), '--mapping', str(mapping),
                                     '--rise-csv', str(scope), '--require-physical-waveforms'])
                self.assertEqual(code, 2)
                result = json.loads((output/'analysis.json').read_text())
                capture = result['captures'][0]
                self.assertEqual(capture['i2c'][0]['repeated_starts'], 1-case)
                self.assertFalse(capture['i2c'][0]['phases'][-1]['frames'][-1]['ack'])
                self.assertEqual(capture['rise_time']['status'], 'PASS')
                self.assertAlmostEqual(capture['rise_time']['max_ns']['sda'], 200)
                self.assertEqual(result['physical_digital_captures_validated'], 0)
                verify(output)
            phases[0][-1] = (0xa2, 0)
            save_wave(external, transaction(phases))
            code = analyze.main(['--run', str(source), '--out', str(root/'bad-ack'), '--case', '1',
                                 '--import-csv', str(external), '--mapping', str(mapping)])
            self.assertEqual(code, 1)

    def test_missing_stop_and_slow_rise(self):
        wave = transaction([[(0xa2, 1)]])
        truncated = Waveform(wave.times[:-4], {k: v[:-4] for k, v in wave.channels.items()})
        with self.assertRaisesRegex(ValueError, 'missing STOP'):
            decode_i2c(truncated, rate=100_000)
        with tempfile.TemporaryDirectory() as temp:
            scope = Path(temp)/'scope.csv'
            scope.write_text('time_s,sda_v,scl_v\n' + ''.join(
                f'{i*20e-9},{i*.033},{i*.033}\n' for i in range(101)))
            self.assertEqual(measure_i2c_rise(scope, supply_v=3.3, rate=100_000)['status'], 'PASS')
            self.assertEqual(measure_i2c_rise(scope, supply_v=3.3, rate=400_000)['status'], 'FAIL')
