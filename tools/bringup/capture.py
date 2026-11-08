"""FPGA v2 digital snapshots; input-pin observations are labelled explicitly."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import struct
import time

CHANNELS = ([f'out{i}' for i in range(8)] + [f'pad{i}' for i in range(4)]
            + ['in0', 'in1'] + [f'oe{i}' for i in range(4)]
            + ['enabled', 'rst_n', 'host_write_bin', 'host_read_bin'])
PHYSICAL_INPUTS = {f'pad{i}' for i in range(4)} | {'in0', 'in1'}


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def export_samples(directory, words, clock_hz, decimation):
    """Retain native little-endian words and lossless nominal-cycle CSV/VCD."""
    period_ns = 1_000_000_000 * (1 << decimation) // clock_hz
    (directory/'samples.bin').write_bytes(b''.join(struct.pack('<I', word) for word in words))
    with (directory/'samples.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['time_ns', *CHANNELS])
        for index, word in enumerate(words):
            writer.writerow([index*period_ns, *[(word >> bit) & 1 for bit in range(len(CHANNELS))]])
    with (directory/'samples.vcd').open('w', encoding='ascii') as stream:
        stream.write('$timescale 1ns $end\n$scope module bringup $end\n')
        for bit, name in enumerate(CHANNELS):
            stream.write(f'$var wire 1 {chr(33+bit)} {name} $end\n')
        stream.write('$upscope $end\n$enddefinitions $end\n')
        previous = None
        for index, word in enumerate(words):
            stream.write(f'#{index*period_ns}\n')
            for bit in range(len(CHANNELS)):
                value = (word >> bit) & 1
                if previous is None or value != ((previous >> bit) & 1):
                    stream.write(f'{value}{chr(33+bit)}\n')
            previous = word
    return period_ns


class Recorder:
    def __init__(self, io, root, fixture, emit, *, image_sha256):
        self.io, self.root, self.fixture, self.emit = io, Path(root), fixture, emit
        self.image_hash = image_sha256
        self.config = fixture.get('capture', {'mode': 'none'})
        self.current = None

    async def arm(self, label, *, channel, decimation=0, immediate=False, falling=True, expected=None):
        if self.current is not None:
            raise RuntimeError('Finish or cancel the previous capture before arming another')
        mode = self.config.get('mode', 'none')
        if mode == 'none':
            self.emit(dict(test=label, type='capture', status='NOT_ACQUIRED',
                           reason='capture.mode=none explicitly selected'))
            return False
        if mode != 'fpga':
            raise ValueError('capture.mode must be none or fpga; import external captures during analysis')
        if self.config.get('loopbacks') and self.config.get('loopbacks_confirmed') is not True:
            raise ValueError('confirm the capture loopback wiring in the fixture before acquiring')
        if channel not in CHANNELS:
            raise ValueError('unknown capture trigger channel')
        directory = self.root/'captures'/label
        directory.mkdir(parents=True, exist_ok=False)
        metadata = dict(status='ARMED', label=label, source='fpga_digital_observer',
            evidence_kind=getattr(self.io, 'evidence_kind', 'simulation'),
            image_sha256=self.image_hash, clock_hz=self.fixture['clock_hz'],
            decimation=decimation, trigger=dict(channel=channel, falling=falling, immediate=immediate),
            expected=expected or {}, fixture_loopbacks=self.config.get('loopbacks', {}),
            fixture_pad_conditions=self.fixture.get('pads', {}),
            signal_scope={name: ('physical_input' if name in PHYSICAL_INPUTS else 'internal_net') for name in CHANNELS},
            host_activity='OR of each host strobe over its sample interval; not an exact edge timestamp',
            timebase='nominal FPGA clock; oscillator accuracy and analog voltages are not measured',
            input_sampling='two physical-input synchronizer registers, then one shared observation register for all channels; no subcycle timing or analog claim',
            started_utc=datetime.now(timezone.utc).isoformat())
        save_json(directory/'capture.json', metadata)
        self.current = (directory, metadata)
        await self.io.trace_cancel()
        await self.io.trace_arm(CHANNELS.index(channel), decimation=decimation, immediate=immediate, falling=falling)
        self.emit(dict(test=label, type='capture', status='ARMED', trigger=metadata['trigger']))
        return True

    async def finish(self):
        if self.current is None:
            return None
        directory, metadata = self.current
        words = []
        try:
            status = await self.io.trace_status()
            # Cover even the longest valid decimation at a fast control link.
            # The extra waits allow a bounded trigger interval; UART overhead
            # adds time but must not be relied on to fill the sample buffer.
            window_cycles = status['depth'] * (1 << metadata['decimation'])
            poll_limit = 200 + (window_cycles+65534)//65535
            for _ in range(poll_limit):
                if status['done']:
                    break
                await self.io.wait(65535)
                status = await self.io.trace_status()
            else:
                raise TimeoutError('digital capture did not trigger and fill; check trigger/loopback wiring')
            if status['count'] != status['depth'] or not status['triggered']:
                raise ValueError('incomplete digital capture')
            with (directory/'partial.bin').open('xb') as partial:
                for index in range(status['count']):
                    word = await self.io.trace_read(index)
                    words.append(word)
                    partial.write(struct.pack('<I', word))
                    if index and index % 1024 == 0:
                        self.emit(dict(test=metadata['label'], type='capture_progress', samples=index, total=status['count']))
            period_ns = export_samples(directory, words, metadata['clock_hz'], metadata['decimation'])
            metadata.update(status='COMPLETE', samples=len(words), sample_period_ns=period_ns,
                            native_sha256=hashlib.sha256((directory/'samples.bin').read_bytes()).hexdigest())
            self.emit(dict(test=metadata['label'], type='capture', status='COMPLETE',
                           samples=len(words), sample_period_ns=period_ns, path=str(directory)))
            return directory
        except BaseException as exc:
            metadata.update(status='FAIL', error=str(exc), retrieved_samples=len(words))
            raise
        finally:
            metadata['finished_utc'] = datetime.now(timezone.utc).isoformat()
            save_json(directory/'capture.json', metadata)
            self.current = None

    async def cancel(self, reason):
        if self.current is not None:
            directory, metadata = self.current
            metadata.update(status='FAIL', error=reason)
            save_json(directory/'capture.json', metadata)
            self.current = None
        if not getattr(self.io, 'poisoned', False):
            await self.io.trace_cancel()
