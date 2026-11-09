"""Complete serial upload, arbitration, waveform and recovery tests."""
import csv
import json
import os
from pathlib import Path
import cocotb
from cocotb.triggers import RisingEdge, Timer
from test_bringup_extended import start
from streaming.feeder import (Feeder, configure, SEQ_LOW, SEQ_HIGH, BEGIN, WORD_LOW, WORD_HIGH,
                              COMMIT, LAUNCH, ABORT, STATUS, FREE, FILL, READY, ACTIVE, COMPLETE)
from streaming.usb_ls import inspect, symbols
from pio_host import PIOHost
from bringup.capture import Recorder
from bringup.waveforms import analyze_capture


async def capture(dut, samples):
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit='ns')
        samples.append(int(dut.dedicated_out.value))


def save(label, samples, results):
    out = Path(os.environ['BRINGUP_SIM_OUT'])
    with (out/(label+'.csv')).open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['clock', *[f'out{i}' for i in range(6)]])
        writer.writerows([n, *[(word >> bit) & 1 for bit in range(6)]] for n, word in enumerate(samples))
    (out/(label+'.json')).write_text(json.dumps(results, indent=2)+'\n')


@cocotb.test()
async def serial_upload_and_quiet_execution(dut):
    io = await start(dut)
    client = Feeder(io)
    await client.identify()
    await configure(io, 0)
    samples = []
    observer = cocotb.start_soon(capture(dut, samples))
    results = []
    try:
        for sequence, payload in enumerate((b'', b'\xff', bytes(range(8)), b'\xff'*8)):
            expected = await client.submit(0, 0, payload, sequence=sequence, data1=bool(sequence & 1))
            begin = len(samples)
            await client.launch(0)
            await Timer(200_000, unit='ns')  # No PC request during the packet.
            completion = await client.completion(0, sequence=sequence)
            assert completion['result'] == 0 and completion['terminal_levels'] == completion['terminal_errors'] == 0
            observed = inspect(samples[begin:])
            assert observed['payload_hex'] == payload.hex() and observed['symbols'] == expected['symbols']
            results.append(dict(completion=completion, observed=observed))
            await client.release(0)
    finally:
        observer.cancel()
        save('quiet-packets', samples, results)


@cocotb.test()
async def dual_engine_word_arbitration(dut):
    io = await start(dut)
    client = Feeder(io)
    await configure(io, 0)
    await configure(io, 1)
    await client.submit(0, 0, b'\xff'*8, sequence=0x11223344)
    await client.submit(1, 1, bytes(range(8)), sequence=0xaabbccdd, data1=True)
    samples = []
    observer = cocotb.start_soon(capture(dut, samples))
    try:
        await client.launch()
        # Direct host access is rejected while the feeder owns the adapter.
        await io.command(1, 15, status=5)
        await Timer(200_000, unit='ns')
        completions = [await client.completion(slot, sequence=sequence)
                       for slot, sequence in enumerate((0x11223344, 0xaabbccdd))]
        assert all(c['result'] == 0 and c['terminal_levels'] == c['terminal_errors'] == 0 for c in completions)
        decoded = [inspect([word >> shift for word in samples]) for shift in (0, 3)]
        assert [r['payload_hex'] for r in decoded] == ['ff'*8, bytes(range(8)).hex()]
        assert decoded[0]['data1'] is False and decoded[1]['data1'] is True
        assert max(r['first_symbol_clock'] for r in decoded) < min(
            r['first_symbol_clock']+r['total_clocks'] for r in decoded)
        save('dual-packets', samples, dict(completions=completions, decoded=decoded))
    finally:
        observer.cancel()


@cocotb.test()
async def observer_dual_physical_loopback_decode(dut):
    io=await start(dut)
    dut.loopbacks.value=3
    client=Feeder(io)
    packets=[dict(engine=0,payload_hex='ff'*8,data1=False,sequence=101,channels=['pad0','pad1','pad2']),
             dict(engine=1,payload_hex='0001020304050607',data1=True,sequence=102,channels=['pad3','in0','in1'])]
    declared={name:f'out{packet["engine"]*3+bit}' for packet in packets
              for bit,name in enumerate(packet['channels'])}
    root=Path(os.environ['BRINGUP_SIM_OUT'])/'observer'
    root.mkdir()
    records=[]
    recorder=Recorder(io,root,dict(clock_hz=50_000_000,capture=dict(mode='fpga',
        loopbacks=declared,loopbacks_confirmed=True)),records.append,image_sha256='simulation')
    for slot,packet in enumerate(packets):
        await configure(io,slot)
        await client.submit(slot,slot,bytes.fromhex(packet['payload_hex']),
                            sequence=packet['sequence'],data1=packet['data1'])
    await recorder.arm('usb-feeder',channel='out2',falling=False,
                       expected=dict(kind='usb_feeder',packets=packets))
    await client.launch()
    await Timer(200_000,unit='ns')
    for slot,packet in enumerate(packets):
        completion=await client.completion(slot,sequence=packet['sequence'])
        assert completion['result']==0
    directory=await recorder.finish()
    result=analyze_capture(directory)
    assert result['status']=='PASS' and len(result['usb_feeder'])==2
    assert result['physical_input_evidence'] is False
    (root/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')


@cocotb.test()
async def upload_boundaries_and_partial_commands(dut):
    io = await start(dut)
    client = Feeder(io)
    await io.command(SEQ_HIGH, 0, 1, status=2)
    await io.command(BEGIN, 0, 3, status=2)
    await io.command(SEQ_LOW, 0, 0x5678)
    await io.command(SEQ_HIGH, 0, 0x1234)
    await io.command(BEGIN, 0, 116, status=2)
    await io.command(BEGIN, 0, 115)
    await io.command(WORD_HIGH, 0, 0, status=2)
    await io.command(WORD_LOW, 0, 0xbeef)
    await io.command(COMMIT, 0, status=2)
    await io.command(WORD_HIGH, 0, 0xabcd)
    for _ in range(28):
        await io.command(WORD_LOW, 0, 0)
        await io.command(WORD_HIGH, 0, 0)
    await io.command(COMMIT, 0)
    assert (await client.status(0))['state'] == READY
    await io.command(WORD_LOW, 0, 0, status=2)
    await client.abort(0)
    assert (await client.status(0))['state'] == FREE
    # A shared reset invalidates an abandoned half-word and descriptor.
    await io.command(SEQ_LOW, 0, 7)
    await io.command(SEQ_HIGH, 0, 0)
    await io.command(BEGIN, 0, 0)
    await io.command(WORD_LOW, 0, 9)
    await io.reset()
    assert (await client.status(0))['state'] == FREE
    await io.command(WORD_HIGH, 0, 0, status=2)
    await io.command(BEGIN, 0, 0, status=2)


@cocotb.test()
async def abort_watchdog_and_engine_failure(dut):
    io = await start(dut)
    client = Feeder(io)
    for sequence, program, abort, result in (
        (1, 'wait 1, gpio, 0\nhalt', True, 1),
        (2, 'wait 1, gpio, 0\nhalt', False, 3),
        (3, 'halt', False, 2),
    ):
        await configure(io, 0, program)
        await client.submit(0, 0, b'\xff'*8, sequence=sequence)
        await client.launch(0)
        if abort:
            await client.abort(0)
        await Timer(600_000, unit='ns')
        completion = await client.completion(0, sequence=sequence)
        assert completion['result'] == result
        assert completion['words_sent'] == 4
        assert completion['terminal_levels'] == 4
        assert await PIOHost(io).engine(0).read(11) == 0
        assert not (await PIOHost(io).engine(0).read(1)) & 1
        await client.release(0)


@cocotb.test()
async def same_engine_slots_and_reset_in_flight(dut):
    io = await start(dut)
    client = Feeder(io)
    await configure(io, 0)
    await client.submit(0, 0, b'\xff'*8, sequence=10)
    await client.submit(1, 0, b'\x55', sequence=11)
    await io.command(26, status=2)
    assert (await client.status(0))['state'] == (await client.status(1))['state'] == READY
    await client.launch(0)
    await io.command(LAUNCH, 1, status=2)
    await Timer(200_000, unit='ns')
    assert (await client.completion(0, sequence=10))['result'] == 0
    await client.launch(1)
    await Timer(200_000, unit='ns')
    assert (await client.completion(1, sequence=11))['result'] == 0
    await client.release(0)
    await client.release(1)
    await client.submit(0, 0, b'\xff'*8, sequence=12)
    await client.launch(0)
    await io.reset()
    assert (await client.status(0))['state'] == (await client.status(1))['state'] == FREE
    assert int.from_bytes(await io.command(STATUS, 2), 'little') == 0
    await configure(io, 0)
    await client.submit(0, 0, b'\x5a', sequence=13)
    await client.launch(0)
    await Timer(200_000, unit='ns')
    assert (await client.completion(0, sequence=13))['result'] == 0
