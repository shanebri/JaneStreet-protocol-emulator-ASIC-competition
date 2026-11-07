"""Real UART/bridge/core tests. Fixture pulls/loopbacks are external to the DUT."""
import sys
import os
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, FallingEdge, RisingEdge, with_timeout
from cocotb.utils import get_sim_time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from test_bringup_serial import WireTransport
from i2c_model import Bus
from bringup.stress import dual_engine_stress, boundaries, recovery, pads, word_read
from bringup.capture import Recorder
from bringup.concurrent_protocols import run_with_peers
from bringup.protocols import i2c, receive_uart_with_sender
from bringup.transport import RAW_BEAT, TRACE_READ
from pio_host import PIOHost


class IO(WireTransport):
    evidence_kind = 'simulation'

    def clock(self):
        return float(get_sim_time(unit='sec'))


async def start(dut):
    dut.reset.value=1; dut.uart_rx.value=1; dut.dedicated_in.value=0; dut.loopbacks.value=0
    dut.i2c_target_low.value=0
    cocotb.start_soon(Clock(dut.clk, 20, unit='ns').start())
    await Timer(400, unit='ns')
    dut.reset.value=0
    await Timer(800, unit='ns')
    return IO(dut)


@cocotb.test()
async def i2c_target_and_address_nack(dut):
    io = await start(dut)
    assert await io.require_v2() == 2

    def drive_levels(levels):
        dut.i2c_target_low.value = (1-levels[0]) | ((1-levels[1]) << 1)

    for rate in (100_000, 400_000):
        bus = Bus(dut.bridge.emulator, host=None, drive_levels=drive_levels,
                  address=0x50, data=b'PIO', rate=rate)
        records = []
        try:
            await i2c(io, dict(i2c=dict(address=0x50, nack_address=0x51, write_hex='00',
                                       expected_hex='50494f', rate=rate, timeout=.02)),
                      records.append, lambda *_: None)
            assert [record['status'] for record in records] == ['PASS', 'PASS']
            assert bus.bytes == [0xa0, 0, 0xa1, 0xa2]
            assert bus.controller_acks == [0, 0, 1]
            assert (bus.starts, bus.stops) == (3, 2)
            assert await io.sample_pads() == dict(inputs=15, oe=0)
            bus.check_timing()
        finally:
            bus.close()
            dut.i2c_target_low.value = 0


@cocotb.test()
async def uart_receive_both_engines(dut):
    io = await start(dut)
    dut.dedicated_in.value = 1
    payload = bytes((0, 0xff, 0x55, 0xaa, 0x81, 1, 0x7e, 0xa6))
    records = []
    async def send(byte):
        # The peer runs at requested baud independently of the rounded PIO divider.
        for bit in [0, *[(byte >> i) & 1 for i in range(8)], 1]:
            dut.dedicated_in.value = bit
            await Timer(1e9/115200, unit='ns', round_mode='round')
    fixture = dict(clock_hz=50_000_000, uart_rx=dict(payload_hex=payload.hex(), wiring_confirmed=True))
    await receive_uart_with_sender(io, fixture, records.append, send)
    engines = [r for r in records if r['test'] == 'uart_rx_engine']
    assert [r['engine'] for r in engines] == [0, 1]
    assert all(r['observed_hex'] == payload.hex() for r in engines)


@cocotb.test()
async def v2_raw_and_capture(dut):
    io = await start(dut)
    assert await io.require_v2() == 2
    await io.write(5, 1)
    await io.raw_beat(6, 11)
    await io.raw_beat(6, 10)
    await io.write(7, 0x12); await io.write(9, 0x34); await io.write(10, 0x56)
    assert await word_read(io, 1) == 0x563412ab
    await io.command(RAW_BEAT, 6, 0x0100, status=2)
    assert (await io.sample_pads())['oe'] == 0
    await io.trace_arm(0, immediate=True)
    await io.wait(2048)
    status = await io.trace_status()
    assert status['done'] and status['count'] == status['depth']
    for index in (0, 1, 31, status['depth']-1):
        assert (await io.trace_read(index)) & 255 == 1
    await io.command(TRACE_READ, value=status['depth'], status=2)
    await io.trace_cancel()
    assert not (await io.trace_status())['done']


@cocotb.test()
async def stress_and_fifo_boundaries(dut):
    io = await start(dut)
    dut.loopbacks.value=2
    records=[]
    fixture=dict(clock_hz=50_000_000, capture=dict(mode='fpga', loopbacks_confirmed=True,
                 loopbacks={'pad2':'out0', 'pad3':'out4'}))
    root=Path(os.environ['BRINGUP_SIM_OUT'])/'stress-capture'
    root.mkdir()
    recorder=Recorder(io, root, fixture, records.append, image_sha256='simulation')
    await dual_engine_stress(io, 3101, records.append, rounds=3, recorder=recorder)
    from bringup.waveforms import analyze_capture
    assert analyze_capture(root/'captures/dual-markers')['status']=='PASS'
    dut.loopbacks.value=0
    await boundaries(io, 3102, records.append)
    assert any(r['test']=='continued_engine_progress' for r in records)
    assert records[-1]['test']=='boundaries' and records[-1]['status']=='PASS'


@cocotb.test()
async def partial_host_recovery_and_pads(dut):
    io = await start(dut)
    records=[]
    await recovery(io, 3103, records.append)
    await pads(io, 3104, records.append,
               fixture=dict(pads=dict(pullups_confirmed=True, active_peers_disconnected=True)))
    assert any(r['test']=='partial_byte_discard_and_word_stage_retention' and r['status']=='PASS' for r in records)


class Peers:
    def __init__(self, dut, baud):
        self.dut, self.bit_ns = dut, 1e9/baud
        self.received_count=0

    async def arm(self, count):
        self.count=count
        self.dut.dedicated_in.value=2

    async def uart_receive(self, count):
        result=bytearray()
        for _ in range(count):
            await FallingEdge(self.dut.peer_uart)
            await Timer(self.bit_ns*1.5, unit='ns')
            byte=0
            for bit in range(8):
                byte |= int(self.dut.peer_uart.value)<<bit
                await Timer(self.bit_ns, unit='ns')
            assert int(self.dut.peer_uart.value)==1
            result.append(byte)
        return bytes(result)

    async def spi_receive(self, sequence):
        reply=sequence ^ 0xa5
        self.dut.dedicated_in.value=2 | ((reply>>7)&1)
        await FallingEdge(self.dut.peer_cs)
        value=0
        for bit in range(7, -1, -1):
            await RisingEdge(self.dut.peer_sclk)
            await Timer(1, unit='ns')
            value=(value<<1) | int(self.dut.peer_mosi.value)
            await FallingEdge(self.dut.peer_sclk)
            if bit:
                self.dut.dedicated_in.value=2 | ((reply>>(bit-1))&1)
        await RisingEdge(self.dut.peer_cs)
        assert value==sequence
        return value

    async def prepare(self, sequence, payload):
        self.uart_task=cocotb.start_soon(self.uart_receive(len(payload)))
        self.spi_task=cocotb.start_soon(self.spi_receive(sequence))

    async def received(self, sequence, payload, spi_rx):
        uart=await with_timeout(self.uart_task, 10, 'ms')
        mosi=await with_timeout(self.spi_task, 10, 'ms')
        self.received_count+=1
        return uart, f'RX {sequence} {mosi} {sequence ^ 0xa5} 1 1'

    async def finish(self):
        assert self.received_count==self.count


@cocotb.test()
async def concurrent_peers_and_capture(dut):
    io = await start(dut)
    dut.loopbacks.value=1
    records=[]
    fixture=dict(clock_hz=50_000_000, nano_board='nano33iot',
        concurrent=dict(transfers=3, uart_baud=115200, spi_divider=32, capture_rounds=[2], timeout_seconds=.01),
        capture=dict(mode='fpga', loopbacks_confirmed=True,
                     loopbacks={'pad0':'out0','pad1':'out2','pad2':'out3','pad3':'out1'}, decimation=5))
    temp=Path(os.environ['BRINGUP_SIM_OUT'])/'concurrent-capture'
    temp.mkdir()
    try:
        recorder=Recorder(io, temp, fixture, records.append, image_sha256='simulation')
        baud=50_000_000/(14*round(50_000_000/(14*115200)))
        await run_with_peers(io, fixture, 3105, records.append, lambda *args:None,
                             Peers(dut, baud), recorder=recorder)
        capture=Path(temp)/'captures/concurrent-002'
        assert (capture/'samples.bin').stat().st_size==4*(await io.trace_status())['depth']
        assert (capture/'samples.csv').is_file() and (capture/'samples.vcd').is_file()
        from bringup.waveforms import analyze_capture
        assert analyze_capture(capture)['overlap_s'] > 0
    finally:
        import json
        (temp/'records.json').write_text(json.dumps(records, indent=2)+'\n')


@cocotb.test()
async def recovery_and_open_drain_captures(dut):
    io = await start(dut)
    fixture=dict(clock_hz=50_000_000, capture=dict(mode='fpga', loopbacks={}),
                 pads=dict(pullups_confirmed=True, active_peers_disconnected=True))
    root=Path(os.environ['BRINGUP_SIM_OUT'])/'recovery-captures'
    root.mkdir()
    recorder=Recorder(io, root, fixture, lambda record:None, image_sha256='simulation')
    engine=PIOHost(io).engine(0)
    await engine.write_word(4, 0)
    await engine.write_word(0x17, 0x100)
    await recorder.arm('freeze', channel='enabled', decimation=5, expected=dict(kind='freeze', pad=0))
    await io.enable(False)
    await io.wait(2000)
    await io.enable(True)
    await recorder.finish()
    await recorder.arm('reset', channel='rst_n', decimation=5, expected=dict(kind='reset', pad=0))
    await io.reset()
    await recorder.finish()
    await engine.write_word(0x18, 0x100)
    await engine.write_word(4, 0)
    await engine.write_word(0x17, 0x100)
    await recorder.arm('release', channel='pad0', immediate=True, decimation=5,
                       expected=dict(kind='open_drain', pad=0))
    await engine.write_word(4, 0x100)
    await recorder.finish()
    from bringup.waveforms import analyze_capture
    for label in ('freeze', 'reset', 'release'):
        result=analyze_capture(root/'captures'/label)
        assert result['status']=='PASS' and not result['physical_input_evidence']
