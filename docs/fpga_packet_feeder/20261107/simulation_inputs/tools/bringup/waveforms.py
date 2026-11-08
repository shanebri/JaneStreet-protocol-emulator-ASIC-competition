"""Strict digital waveform decoding; no analog or sub-sample timing claims."""
import bisect
import csv
import math
from pathlib import Path


class Waveform:
    def __init__(self, times, channels):
        if len(times) < 2 or any(not math.isfinite(t) for t in times):
            raise ValueError('waveform requires at least two finite timestamps')
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError('timestamps must increase strictly')
        if not channels or any(len(values) != len(times) for values in channels.values()):
            raise ValueError('channel/sample lengths do not match')
        if any(value not in (0, 1) for values in channels.values() for value in values):
            raise ValueError('digital samples must be defined 0/1')
        self.times, self.channels = times, channels
        self.max_interval = max(b-a for a, b in zip(times, times[1:]))

    def value(self, channel, when):
        if when < self.times[0] or when > self.times[-1]:
            raise ValueError('frame extends beyond the capture')
        return self.channels[channel][bisect.bisect_right(self.times, when)-1]

    def edges(self, channel, rising=None):
        values = self.channels[channel]
        return [(self.times[i], values[i]) for i in range(1, len(values))
                if values[i] != values[i-1] and (rising is None or values[i] == int(rising))]


def read_csv(path, mapping=None):
    mapping = mapping or dict(time_column='time_ns', time_unit='ns')
    scale = {'s': 1., 'ms': 1e-3, 'us': 1e-6, 'ns': 1e-9}[mapping.get('time_unit', 'ns')]
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError('empty waveform CSV')
        columns = mapping.get('channels') or {name: name for name in reader.fieldnames if name != mapping['time_column']}
        if (not isinstance(columns, dict) or not columns or mapping['time_column'] not in reader.fieldnames
                or any(column not in reader.fieldnames for column in columns.values())):
            raise ValueError('missing time/channel columns')
        times, channels = [], {name: [] for name in columns}
        for row in reader:
            if row.get(mapping['time_column']) is None or any(row.get(column) is None for column in columns.values()):
                raise ValueError('truncated waveform CSV row')
            times.append(float(row[mapping['time_column']])*scale)
            for name, column in columns.items():
                value = row[column].strip()
                if value not in ('0', '1', '0.0', '1.0'):
                    raise ValueError(f'{column}: expected digital 0/1, got {value!r}')
                channels[name].append(int(float(value)))
    return Waveform(times, channels)


def decode_uart(wave, channel, baud, *, triggered_falling=False):
    if not math.isfinite(baud) or baud <= 0 or wave.max_interval > 1/(8*baud):
        raise ValueError('UART decoding requires at least eight samples per nominal bit')
    bit = 1/baud
    starts = [when for when, _ in wave.edges(channel, rising=False)]
    if triggered_falling and wave.channels[channel][0] == 0:
        starts.insert(0, wave.times[0])
    result, next_start = [], -math.inf
    for start in starts:
        if start < next_start:
            continue
        if wave.value(channel, start+.5*bit) != 0:
            raise ValueError('invalid UART start bit')
        value = sum(wave.value(channel, start+(1.5+i)*bit) << i for i in range(8))
        if wave.value(channel, start+9.5*bit) != 1:
            raise ValueError('UART framing error')
        result.append(dict(start_s=start, end_s=start+10*bit, byte=value))
        next_start = start+9.75*bit
    return result


def decode_spi(wave, *, sclk, mosi, miso, cs, clock_hz):
    if clock_hz <= 0 or not math.isfinite(clock_hz) or wave.max_interval > 1/(8*clock_hz):
        raise ValueError('SPI decoding requires at least eight samples per nominal clock')
    if wave.channels[cs][0] == 0:
        raise ValueError('capture begins inside an SPI transaction')
    active, bits, result = None, [], []
    cs_edges = dict(wave.edges(cs))
    rises = set(t for t, _ in wave.edges(sclk, rising=True))
    for when in sorted(set(cs_edges) | rises):
        if when in cs_edges:
            if cs_edges[when] == 0:
                if active is not None or wave.value(sclk, when) != 0:
                    raise ValueError('invalid mode-0 CS assertion')
                active, bits = when, []
            else:
                if active is None or len(bits) != 8:
                    raise ValueError(f'SPI transaction has {len(bits)} rising edges, expected eight')
                tx = rx = 0
                for tx_bit, rx_bit in bits:
                    tx, rx = (tx << 1) | tx_bit, (rx << 1) | rx_bit
                result.append(dict(start_s=active, end_s=when, mosi=tx, miso=rx, bits=8))
                active = None
        if when in rises and active is not None:
            bits.append((wave.value(mosi, when), wave.value(miso, when)))
    if active is not None:
        raise ValueError('capture ends inside an SPI transaction')
    return result


def decode_i2c(wave, *, rate):
    if rate not in (10_000, 100_000, 400_000) or wave.max_interval * rate > 0.125000001:
        raise ValueError('I2C decoding requires at least eight samples per nominal clock')
    sda, scl = wave.channels['sda'], wave.channels['scl']
    if sda[0] != 1 or scl[0] != 1:
        raise ValueError('I2C capture must begin with both lines idle high')
    sda_edges, scl_edges = dict(wave.edges('sda')), dict(wave.edges('scl'))
    phases, bits = [], []
    high_bit, stop = None, None
    for when in sorted(sda_edges.keys() | scl_edges.keys()):
        if when in sda_edges and when in scl_edges:
            raise ValueError('simultaneous SDA/SCL edges are ambiguous; increase sample rate')
        if stop is not None:
            raise ValueError('unexpected I2C activity after STOP')
        if when in sda_edges and wave.value('scl', when):
            # The SCL rise used to set up START/STOP has no completing fall.
            if phases and (bits or high_bit is None or not phases[-1]['frames']):
                raise ValueError('I2C framing edge before the previous byte completed')
            if sda_edges[when] == 0:
                phases.append(dict(start_s=when, frames=[]))
            elif phases:
                stop = when
            else:
                raise ValueError('I2C STOP before START')
            high_bit = None
        elif when in scl_edges:
            if not phases:
                raise ValueError('I2C clock activity before START')
            if scl_edges[when]:
                high_bit = wave.value('sda', when)
            elif high_bit is not None:
                bits.append(high_bit)
                high_bit = None
                if len(bits) == 9:
                    byte = sum(bit << (7-i) for i, bit in enumerate(bits[:8]))
                    phases[-1]['frames'].append(dict(byte=byte, ack=bits[8] == 0))
                    bits.clear()
    if stop is None or sda[-1] != 1 or scl[-1] != 1:
        raise ValueError('I2C capture is missing STOP or final bus idle')
    return dict(start_s=phases[0]['start_s'], stop_s=stop,
                repeated_starts=len(phases)-1, phases=phases)


def measure_i2c_rise(path, *, supply_v, rate):
    """Measure 30–70% crossing times from a scope CSV sampled in seconds/volts."""
    if type(supply_v) not in (int, float) or not math.isfinite(supply_v) or supply_v <= 0:
        raise ValueError('rise_supply_v must be a positive finite voltage')
    limit = 300 if rate == 400_000 else 1000
    low, high = 0.3 * supply_v, 0.7 * supply_v
    begins = [None, None]
    widths = [[], []]
    previous, interval = None, 0
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        names = ('time_s', 'sda_v', 'scl_v')
        if not reader.fieldnames or not set(names) <= set(reader.fieldnames):
            raise ValueError('scope CSV must contain time_s,sda_v,scl_v')
        for row in reader:
            current = tuple(float(row[name]) for name in names)
            if not all(map(math.isfinite, current)) or (previous and current[0] <= previous[0]):
                raise ValueError('scope CSV requires finite voltages and increasing timestamps')
            if previous:
                dt = current[0] - previous[0]
                interval = max(interval, dt)
                for i, (before, after) in enumerate(zip(previous[1:], current[1:])):
                    if after < low:
                        begins[i] = None
                    if before < low <= after:
                        begins[i] = previous[0] + dt*(low-before)/(after-before)
                    if before < high <= after and begins[i] is not None:
                        end = previous[0] + dt*(high-before)/(after-before)
                        widths[i].append(1e9*(end-begins[i]))
                        begins[i] = None
            previous = current
    if not all(widths):
        raise ValueError('scope CSV needs at least one complete 30–70% rise on each line')
    interval_ns = interval*1e9
    if interval_ns > limit/10 + 1e-6:
        raise ValueError(f'scope CSV sample interval must be at most {limit/10:g} ns')
    maxima = dict(zip(('sda', 'scl'), map(max, widths)))
    return dict(status='PASS' if max(maxima.values()) <= limit else 'FAIL',
                supply_v=supply_v, max_ns=maxima, limit_ns=limit, max_sample_interval_ns=interval_ns,
                edges=dict(zip(('sda', 'scl'), map(len, widths))),
                scope='sampled 30–70% crossings with linear interpolation')


def loopbacks(wave, declared, *, lag_samples=1, triggered_output=None):
    result = {}
    for physical, output in declared.items():
        if physical not in wave.channels or output not in wave.channels:
            raise ValueError('declared loopback channel missing')
        source, sampled = wave.channels[output], wave.channels[physical]
        # A rising-edge trigger can make sample zero already high. Its
        # pre-capture rising edge is absent, but release must still be visible.
        source_edges=1 if output==triggered_output and source[0] else 2
        input_edges=1 if output==triggered_output and sampled[0] else 2
        if len(wave.edges(physical)) < input_edges or len(wave.edges(output)) < source_edges:
            raise ValueError('loopback correlation requires observable activity at both ends')
        # Allow the declared sampled lag, including input synchronization.
        # Timestamps cannot establish subcycle propagation.
        bad = sum(sampled[i] not in source[max(0,i-lag_samples):i+1] for i in range(lag_samples, len(source)))
        if bad:
            raise ValueError(f'{physical}->{output}: {bad} inconsistent digital samples')
        result[physical] = dict(output=output, inconsistent_samples=bad, scope='sampled digital correlation')
    return result


def analyze_capture(directory):
    import json
    directory = Path(directory)
    metadata = json.loads((directory/'capture.json').read_text())
    if metadata['status'] != 'COMPLETE':
        raise ValueError('capture is not complete')
    wave = read_csv(directory/'samples.csv', metadata.get('csv_mapping'))
    expected = metadata['expected']
    kind = expected.get('kind')
    result = dict(status='PASS', evidence_kind=metadata['evidence_kind'], kind=kind,
                  expectation=expected,
                  sample_count=len(wave.times), max_sample_interval_s=wave.max_interval,
                  scope='sampled digital behavior; no analog compliance or timing signoff')
    hardware = metadata['evidence_kind'] == 'hardware_transport'
    result['physical_input_evidence'] = False
    if kind == 'uart_spi':
        if metadata.get('source') == 'fpga_digital_observer' and any(any(wave.channels[f'oe{pad}']) for pad in range(4)):
            raise ValueError('loopback pads were driven by the core during protocol capture')
        trigger = metadata.get('trigger', {})
        uart = decode_uart(wave, expected['uart_channel'], expected['uart_baud'],
            triggered_falling=trigger.get('channel') == expected['uart_channel'] and trigger.get('falling') is True)
        spi = decode_spi(wave, sclk=expected['sclk_channel'], mosi=expected['mosi_channel'],
                         miso=expected['miso_channel'], cs=expected['cs_channel'], clock_hz=expected['spi_clock_hz'])
        actual_uart = bytes(frame['byte'] for frame in uart).hex()
        if actual_uart != expected['uart_hex'] or len(spi) != 1:
            raise ValueError(f'waveform transaction count/data mismatch: UART={actual_uart}, SPI={len(spi)}')
        if spi[0]['mosi'] != expected['spi_mosi'] or spi[0]['miso'] != expected['spi_miso']:
            raise ValueError(f'decoded SPI MOSI/MISO observed={spi[0]["mosi"]}/{spi[0]["miso"]}, '
                             f'expected={expected["spi_mosi"]}/{expected["spi_miso"]}')
        start = max(uart[0]['start_s'], spi[0]['start_s'])
        end = min(uart[-1]['end_s'], spi[0]['end_s'])
        if end <= start:
            raise ValueError('UART and SPI execution do not overlap in this capture')
        host = [name for name in ('host_write_bin', 'host_read_bin') if name in wave.channels]
        activity = any(wave.channels[name][i] for name in host for i, when in enumerate(wave.times) if start < when < end)
        if metadata.get('source') == 'fpga_digital_observer' and not activity:
            raise ValueError('no host access observed during concurrent protocol overlap')
        result.update(uart=uart, spi=spi, overlap_s=end-start, host_activity_during_overlap=activity)
        if metadata.get('fixture_loopbacks'):
            result['loopbacks'] = loopbacks(wave, metadata['fixture_loopbacks'])
            result['physical_input_evidence'] = hardware
    elif kind == 'usb_feeder':
        from streaming.usb_ls import inspect
        if abs(wave.max_interval-20e-9) > 1e-12:
            raise ValueError('USB feeder capture requires nominal 50 MHz sampling without decimation')
        if any(any(wave.channels[f'oe{pad}']) for pad in range(4)):
            raise ValueError('USB feeder loopback pads were driven during capture')
        declared={name:f'out{packet["engine"]*3+bit}' for packet in expected['packets']
                  for bit,name in enumerate(packet['channels'])}
        if not declared or metadata.get('fixture_loopbacks') != declared:
            raise ValueError('USB feeder loopbacks must identify all physical DP/DM/marker inputs')
        frames=[]
        for packet in expected['packets']:
            engine=packet['engine']
            channels=packet['channels']
            if any(metadata['signal_scope'].get(name) != 'physical_input' for name in channels):
                raise ValueError('USB feeder evidence requires physical DP/DM/marker input samples')
            physical=[sum(wave.channels[name][i]<<bit for bit,name in enumerate(channels))
                      for i in range(len(wave.times))]
            internal=[sum(wave.channels[f'out{engine*3+bit}'][i]<<bit for bit in range(3))
                      for i in range(len(wave.times))]
            decoded=inspect(physical,edge_tolerance=3)
            precise=inspect(internal)
            if any(decoded[key] != packet[key] for key in ('payload_hex','data1')):
                raise ValueError('USB feeder physical payload/PID differs from the submitted packet')
            if any(decoded[key] != precise[key] for key in ('payload_hex','data1','symbols')):
                raise ValueError('physical and internal USB packet decodes differ')
            frames.append(dict(engine=engine,physical=decoded,internal=precise))
        result['usb_feeder']=frames
        result['loopbacks']=loopbacks(wave,metadata['fixture_loopbacks'],lag_samples=3,
                                     triggered_output=metadata.get('trigger',{}).get('channel'))
        result['physical_input_evidence']=hardware
    elif kind == 'i2c':
        decoded = decode_i2c(wave, rate=expected['rate'])
        if [phase['frames'] for phase in decoded['phases']] != expected['phases']:
            raise ValueError(f'I2C bytes, ACKs or repeated START differ from the expected transaction: {decoded}')
        result['i2c'] = [decoded]
        result['rise_time'] = dict(status='NOT_MEASURED')
        if (directory/'rise.csv').is_file():
            result['rise_time'] = measure_i2c_rise(directory/'rise.csv',
                supply_v=metadata['csv_mapping']['rise_supply_v'], rate=expected['rate'])
    elif kind == 'markers':
        for name in ('out0', 'out4'):
            if len(wave.edges(name)) < 2:
                raise ValueError(f'no sustained activity at {name}')
        activity = any(any(wave.channels[name]) for name in ('host_write_bin', 'host_read_bin'))
        if not activity:
            raise ValueError('no host access observed during marker execution')
        result['host_activity_during_markers'] = True
        if metadata.get('fixture_loopbacks'):
            result['loopbacks'] = loopbacks(wave, metadata['fixture_loopbacks'])
            result['physical_input_evidence'] = hardware
    elif kind == 'freeze':
        disabled = [i for i, value in enumerate(wave.channels['enabled']) if not value]
        if not disabled or any(wave.channels[f'oe{expected["pad"]}'][i] != 1 for i in disabled):
            raise ValueError('disable did not retain the expected protocol drive')
    elif kind == 'reset':
        if not any(value == 0 for value in wave.channels['rst_n']):
            raise ValueError('reset assertion was not captured')
        if wave.channels[f'oe{expected["pad"]}'][-1] != 0:
            raise ValueError('reset did not release logical output enable')
        if metadata.get('fixture_pad_conditions', {}).get('pullups_confirmed') is True:
            if wave.channels[f'pad{expected["pad"]}'][-1] != 1:
                raise ValueError('reset did not release the pin to its declared pullup')
            result['physical_input_evidence'] = hardware
    elif kind == 'open_drain':
        pad = expected['pad']
        values, enables = wave.channels[f'pad{pad}'], wave.channels[f'oe{pad}']
        if not any(v == 0 for v in values) or values[-1] != 1 or enables[-1] != 0:
            raise ValueError('missing driven-low/released-high open-drain transition')
        result['release_scope'] = 'digital level with declared external pullup; high impedance and analog rise time not measured'
        result['physical_input_evidence'] = hardware and metadata.get('fixture_pad_conditions', {}).get('pullups_confirmed') is True
    else:
        raise ValueError('unknown or missing capture expectation kind')
    return result
