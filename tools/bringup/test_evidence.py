import asyncio
from contextlib import redirect_stdout
from functools import reduce
import io
import json
from operator import xor
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bringup import analyze, prepare, run
from bringup.artifacts import seal, verify
from bringup.capture import Recorder, save_json
from bringup.traffic import summarize
from bringup.transport import SerialTransport, TRACE_READ
from bringup.waveforms import Waveform, decode_uart, decode_spi, loopbacks, read_csv, analyze_capture
from pio_host import GROUP_RESUME_BOTH


def packet(*fields):
    return bytes(fields)+bytes((reduce(xor, fields),))


def traffic(op=7, wide=False):
    request = packet(0xc3, 0, op, 0, 0, 0, 0)
    response = packet(0xc3, 0, 0, 2, 1 if wide else 0, 0, 0)
    return [dict(direction='tx', data=request.hex()),
            dict(direction='tx_result', data=dict(bytes_sent=8, requested=8)),
            dict(direction='rx_chunk', data=response[:3].hex()),
            dict(direction='rx_chunk', data=response[3:].hex()),
            dict(direction='rx', data=response.hex())]


class PacketTests(unittest.TestCase):
    def test_wide_fragmented_reply_and_no_retry(self):
        class Port:
            writes = 0
            def write(self, request):
                self.writes += 1
                self.reply = bytearray(packet(0xc3, request[1], 0, 0x12, 0x34, 0x56, 0x78))
                return 8
            def read(self, count):
                chunk = self.reply[:2]; del self.reply[:2]; return chunk
        port, events = Port(), []
        bridge = SerialTransport(port, trace=lambda *r:events.append(r))
        self.assertEqual(asyncio.run(bridge.trace_read(0)), 0x78563412)
        self.assertEqual(len([r for r in events if r[0] == 'rx_chunk']), 4)
        with self.assertRaises(IOError): asyncio.run(bridge.read(0))
        with self.assertRaises(IOError): asyncio.run(bridge.read(0))
        self.assertTrue(bridge.poisoned)
        self.assertEqual(port.writes, 2)

    def test_partial_timeout_retained(self):
        class Port:
            def write(self, request): self.first=True; return 8
            def read(self, count):
                if self.first: self.first=False; return b'\xc3\x00'
                return b''
        events=[]
        bridge=SerialTransport(Port(), timeout=.005, trace=lambda *r:events.append(r))
        with self.assertRaises(TimeoutError): asyncio.run(bridge.read(0))
        self.assertEqual(events[-1], ('rx_timeout', dict(partial_hex='c300', expected_bytes=8)))
        self.assertTrue(bridge.poisoned)

    def test_capture_arm_failure_remains_identifiable(self):
        class IO:
            evidence_kind='simulation'
            async def trace_cancel(self): raise IOError('unplugged while arming')
        with tempfile.TemporaryDirectory() as temp:
            recorder=Recorder(IO(), temp, dict(clock_hz=50_000_000, capture=dict(mode='fpga')), lambda r:None, image_sha256='test')
            with self.assertRaises(IOError):
                asyncio.run(recorder.arm('failed-arm', channel='out0'))
            self.assertIsNotNone(recorder.current)
            self.assertTrue((Path(temp)/'captures/failed-arm/capture.json').is_file())

    def test_impossible_capture_window_rejected_before_core_reset(self):
        from bringup.concurrent_protocols import run_with_peers
        class IO:
            async def require_v2(self): return 2
            async def trace_status(self): return dict(depth=8192)
            async def reset(self): raise AssertionError('must validate window before programming')
        fixture=dict(clock_hz=50_000_000, concurrent=dict(uart_baud=1200, spi_divider=8192),
            capture=dict(mode='fpga', decimation=0, loopbacks_confirmed=True,
                         loopbacks={'pad0':'out0','pad1':'out2','pad2':'out3','pad3':'out1'}))
        with self.assertRaisesRegex(ValueError, 'capture depth/decimation'):
            asyncio.run(run_with_peers(IO(), fixture, 1, lambda r:None, lambda *args:None, None))

    def test_long_capture_window_gets_enough_explicit_waits(self):
        class IO:
            evidence_kind='simulation'
            elapsed=0
            async def trace_cancel(self): pass
            async def trace_arm(self, *args, **kwargs): pass
            async def trace_status(self):
                done=self.elapsed >= 8192*(1<<15)
                return dict(depth=8192, done=done, triggered=True, count=8192 if done else 0)
            async def wait(self, cycles): self.elapsed += cycles
            async def trace_read(self, index): return 0
        with tempfile.TemporaryDirectory() as temp:
            bridge=IO()
            recorder=Recorder(bridge, temp, dict(clock_hz=50_000_000, capture=dict(mode='fpga')),
                              lambda r:None, image_sha256='test')
            async def acquire():
                await recorder.arm('long', channel='out0', decimation=15, immediate=True)
                return await recorder.finish()
            directory=asyncio.run(acquire())
            self.assertGreater(bridge.elapsed, 200*65535)
            self.assertEqual((directory/'samples.bin').stat().st_size, 8192*4)
            self.assertEqual(json.loads((directory/'capture.json').read_text())['status'], 'COMPLETE')

    def test_traffic_rejects_corruption_short_write_and_incomplete(self):
        self.assertEqual(summarize(traffic())['completed_commands'], 1)
        self.assertEqual(summarize(traffic(TRACE_READ, True))['status'], 'PASS')
        bad=traffic(); bad[1]['data']['bytes_sent']=7
        self.assertEqual(summarize(bad)['status'], 'FAIL')
        self.assertEqual(summarize(traffic()[:-1])['status'], 'FAIL')
        bad=traffic(); bad[-1]['data']='00'*8
        self.assertEqual(summarize(bad)['status'], 'FAIL')
        self.assertEqual(GROUP_RESUME_BOTH, 0x30)


def protocol_wave(payload=b'\x55\xa3\x00\xff'):
    times=[i/100000 for i in range(4600)]
    uart=[]; sclk=[]; cs=[]; mosi=[]; miso=[]
    for i,t in enumerate(times):
        u=1
        for n, byte in enumerate(payload):
            bit=int((t-(.001+n*.011))/.001+1e-8)
            if t >= .001+n*.011 and 0 <= bit < 10:
                u=0 if bit == 0 else ((byte>>(bit-1)) & 1 if bit < 9 else 1)
        active=200 <= i < 1050
        position=max(0, min(7, (i-200)//100))
        uart.append(u); cs.append(int(not active))
        sclk.append(int(active and i < 1000 and (i-200)%100 >= 50))
        mosi.append(0); miso.append((0xa5>>(7-position)) & 1)
    return Waveform(times, dict(uart=uart, sclk=sclk, cs=cs, mosi=mosi, miso=miso))


class WaveformTests(unittest.TestCase):
    def test_real_decoding_and_corrupt_stop(self):
        wave=protocol_wave()
        self.assertEqual(bytes(r['byte'] for r in decode_uart(wave, 'uart', 1000)), b'\x55\xa3\x00\xff')
        frames=decode_spi(wave, sclk='sclk', mosi='mosi', miso='miso', cs='cs', clock_hz=1000)
        self.assertEqual([(f['mosi'], f['miso']) for f in frames], [(0, 0xa5)])
        for i,t in enumerate(wave.times):
            if .010 <= t < .011: wave.channels['uart'][i]=0
        with self.assertRaises(ValueError): decode_uart(wave, 'uart', 1000)

    def test_partial_aliasing_undefined_and_loopback(self):
        wave=protocol_wave()
        short=Waveform(wave.times[:800], {k:v[:800] for k,v in wave.channels.items()})
        with self.assertRaises(ValueError): decode_spi(short, sclk='sclk', mosi='mosi', miso='miso', cs='cs', clock_hz=1000)
        with self.assertRaises(ValueError): decode_uart(wave, 'uart', 1e6)
        with self.assertRaises(ValueError): Waveform([0,1], {'x':[0,2]})
        wave.channels['pad']=[1]+wave.channels['uart'][:-1]
        self.assertEqual(loopbacks(wave, {'pad':'uart'})['pad']['inconsistent_samples'], 0)
        wave.channels['pad'][550] ^= 1
        with self.assertRaises(ValueError): loopbacks(wave, {'pad':'uart'})

    def test_empty_csv_clean_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'empty.csv'; path.write_text('')
            with self.assertRaises(ValueError): read_csv(path)

    def test_capture_classification_and_reset_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'samples.csv').write_text('time_ns,rst_n,oe0,pad0\n0,0,1,0\n20,0,0,0\n40,1,0,1\n')
            meta=dict(status='COMPLETE', evidence_kind='simulation', expected=dict(kind='reset', pad=0),
                      fixture_pad_conditions=dict(pullups_confirmed=True))
            save_json(root/'capture.json', meta)
            self.assertFalse(analyze_capture(root)['physical_input_evidence'])
            meta['evidence_kind']='hardware_transport'; save_json(root/'capture.json', meta)
            self.assertTrue(analyze_capture(root)['physical_input_evidence'])
            (root/'samples.csv').write_text('time_ns,rst_n,oe0,pad0\n0,0,1,0\n20,0,0,0\n40,1,0,0\n')
            with self.assertRaises(ValueError): analyze_capture(root)


class BundleTests(unittest.TestCase):
    def test_index_extra_changed_and_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'data').write_text('original'); seal(root); verify(root)
            (root/'extra').write_text('x')
            with self.assertRaises(ValueError): verify(root)
            (root/'extra').unlink(); (root/'data').write_text('changed')
            with self.assertRaises(ValueError): verify(root)
            index=json.loads((root/'artifacts.json').read_text())
            index['files']['../escape']=index['files'].pop('data')
            save_json(root/'artifacts.json', index)
            with self.assertRaises(ValueError): verify(root)

    def test_seed_revalidation(self):
        from bringup.stress import tagged_word
        rng=random.Random(2201 ^ 0xd0a1e)
        expected=[tagged_word(rng, i, 0) for i in (0,1)]
        manifest=dict(suite='dual_engine_stress', status='PASS', seed=2201, rounds=1)
        record=dict(test='dual_word', status='PASS', sequence=0, expected=expected, observed=expected)
        analyze.verify_records(manifest, [record])
        record['observed']=[0,0]
        with self.assertRaises(ValueError): analyze.verify_records(manifest, [record])

    def test_analysis_missing_waveforms_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            root=Path(temp); source=root/'run'; source.mkdir()
            save_json(source/'manifest.json', dict(status='PASS', suite='smoke', seed=1,
                      image_sha256='a'*64, evidence_kind='simulation'))
            (source/'results.jsonl').write_text(json.dumps(dict(type='assertion', status='PASS', expected=1, observed=1))+'\n')
            (source/'transport.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in traffic()))
            seal(source)
            self.assertEqual(analyze.main(['--run',str(source),'--out',str(root/'analysis'), '--require-physical-waveforms']), 2)
            result=json.loads((root/'analysis/analysis.json').read_text())
            self.assertEqual(result['waveform_status'], 'NOT_ACQUIRED')
            self.assertFalse(result['complete_electrical_qualification'])
            (source/'results.jsonl').write_text('tampered')
            self.assertEqual(analyze.main(['--run',str(source),'--out',str(root/'tamper')]), 1)

    def test_preparation_and_failed_run_retention(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            root=Path(temp); image=root/'image.bit'; image.write_bytes(b'image')
            prepare.main(['--image',str(image),'--bridge-port','COM3','--nano-port','COM4',
                          '--uart-peer-port','COM5','--out',str(root/'campaign')])
            fixture=json.loads((root/'campaign/concurrent.json').read_text())
            self.assertFalse(fixture['capture']['loopbacks_confirmed'])
            self.assertEqual(fixture['concurrent']['transfers'],256)
            serial=types.SimpleNamespace(Serial=unittest.mock.Mock(side_effect=OSError('unplugged')))
            with patch.dict(sys.modules, serial=serial):
                self.assertEqual(run.main(['--fixture',str(root/'campaign/concurrent.json'),
                                 '--suite','concurrent','--out',str(root/'failed')]), 1)
            verify(root/'failed')
            self.assertIn('unplugged',(root/'failed/exception.txt').read_text())
            self.assertEqual(json.loads((root/'failed/manifest.json').read_text())['status'], 'FAIL')

    def test_external_capture_import_never_promotes_simulation(self):
        import csv
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            root=Path(temp); source=root/'run'; source.mkdir()
            rng=random.Random(2201); payload=bytes(rng.randrange(256) for _ in range(4))
            manifest=dict(status='PASS', suite='concurrent', seed=2201, image_sha256='a'*64,
                evidence_kind='simulation', fixture=dict(clock_hz=50_000_000,
                    concurrent=dict(transfers=1, uart_baud=1000, spi_divider=3125)))
            save_json(source/'manifest.json', manifest)
            record=dict(test='concurrent_round', status='PASS', sequence=0,
                expected=dict(uart_hex=payload.hex(), spi_mosi=0, spi_miso=0xa5),
                observed=dict(uart_hex=payload.hex(), spi_miso=0xa5, nano='RX 0 0 165 1 1'))
            (source/'results.jsonl').write_text(json.dumps(record)+'\n')
            (source/'transport.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in traffic()))
            seal(source)
            wave=protocol_wave(payload)
            with (root/'external.csv').open('w', newline='') as stream:
                writer=csv.writer(stream); writer.writerow(['seconds', *wave.channels])
                writer.writerows([t, *[v[i] for v in wave.channels.values()]] for i,t in enumerate(wave.times))
            mapping=dict(instrument='synthetic unit fixture', image_sha256='a'*64, time_unit='s',
                         time_column='seconds', channels={k:k for k in wave.channels})
            save_json(root/'mapping.json', mapping)
            code=analyze.main(['--run',str(source),'--out',str(root/'analysis'),
                '--import-csv',str(root/'external.csv'),'--mapping',str(root/'mapping.json'), '--require-physical-waveforms'])
            self.assertEqual(code, 2)
            result=json.loads((root/'analysis/analysis.json').read_text())
            self.assertEqual(result['waveform_status'], 'DIGITAL_DECODE_PASS')
            self.assertEqual(result['physical_digital_captures_validated'], 0)
            self.assertEqual(len((root/'analysis/decoded_transactions.jsonl').read_text().splitlines()), 5)
            verify(root/'analysis')


if __name__ == '__main__': unittest.main()
