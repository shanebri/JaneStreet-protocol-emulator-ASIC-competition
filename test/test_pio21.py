"""Pin-level direction/routing/lifecycle coverage for revision 0x21."""
import cocotb
from test import Host, encode, assemble


def route(base=8, width=4, in_base=2, side=11, jump=5, side_dirs=False):
    return 1 | (base << 1) | (width << 5) | (base << 9) | (width << 13) | (in_base << 17) | (side << 20) | (jump << 24) | (int(side_dirs) << 27)


@cocotb.test()
async def directions_mapping_counts_autopull_and_exec(dut):
    h=Host(dut)
    for right in (False,True):
        for count in range(1,33):
            await h.reset()
            value=0x96a53cc3
            await h.write_word(0x16,route())
            await h.write_word(0x10,int(right)|4)
            await h.load(f"out pindirs, {count}\nhalt")
            await h.write(0,1)
            await h.tick(5)
            assert await h.read_word(0x17)==255
            assert await h.read_word(5)==32
            await h.write_word(8,value)
            await h.done()
            expected=(value & ((1<<count)-1)) if right else value>>(32-count)
            assert await h.read_word(0x17)==255|((expected&15)<<8)
            assert await h.read_word(5)==count
    for base in range(16):
        for width in (0,1,4,12,15):
            await h.reset()
            await h.write_word(0x16,route(base,width))
            await h.write_word(0x17,0xa00)
            await h.write_word(4,0x501)
            await h.load("set pindirs, 5\nhalt")
            await h.write(0,1); await h.done()
            expected=0xaff
            for bit in range(12 if width==0 or width>12 else width):
                if 8<=base+bit<12:
                    expected=(expected & ~(1<<(base+bit))) | (((5>>bit)&1)<<(base+bit))
            assert await h.read_word(0x17)==expected
            assert await h.read_word(4)==0x501
    for injection in ('out exec, 16','mov exec, osr'):
        await h.reset(); await h.write_word(0x16,route())
        await h.write_word(8,assemble('set pindirs, 9')[0])
        await h.load('pull block\n'+injection+'\nhalt')
        await h.write(0,1); await h.done()
        assert await h.read_word(0x17)==0x9ff


@cocotb.test()
async def input_namespaces_sync_filter_and_physical_readback(dut):
    h=Host(dut)
    for index in range(6):
        await h.reset()
        await h.write_word(0x16,route(in_base=index,jump=index))
        await h.load(f'wait 1, gpio, {index}\nwait 1, pin, 0\njmp pin, 4\nhalt\nmov x, pins\nin pins, 1\nhalt')
        await h.write(0,1); await h.tick(3)
        assert await h.read(8)==0
        h.inputs=(1<<index) if index<2 else 0
        h.control(0)
        dut.uio_in.value=(1<<(index+2)) if index>=2 else 0
        await h.tick(3); await h.done()
        assert await h.read_word(0)==1
        assert await h.read_word(3)==0x80000000
    await h.reset()
    await h.write_word(0x18,0xffff)
    await h.write_word(0x17,0xffff)
    assert await h.read_word(0x18)==0xf00
    assert await h.read_word(0x17)==0xfff
    assert await h.read_word(4)==0xf01
    assert int(dut.uio_oe.value)&0xf0==0  # OD ones release
    dut.uio_in.value=0  # external low overrides released latch=1
    assert await h.read(14)==0
    await h.write_word(0x19,15)
    # Poll snapshots introduce latency; use a waiting program to inspect edge latency.
    await h.write_word(0x16,route(in_base=2))
    await h.load('wait 1, pin, 0\nset pins, 0\nhalt')
    await h.write(0,1)
    dut.uio_in.value=0x10
    await h.tick(2)
    dut.uio_in.value=0
    await h.tick(8)
    assert int(dut.uio_oe.value)&0xf0==0, '40 ns pulse passed filter'
    dut.uio_in.value=0x10
    await h.tick(6)
    assert int(dut.uio_oe.value)&0xf0==0
    await h.tick(3)
    assert int(dut.uio_oe.value)&0xf0==0xf0
    for index in (6,7):
        await h.reset(); await h.write_word(0x16,route(in_base=index,jump=index))
        await h.load('wait 0, pin, 5\nmov x, pins\njmp pin, 4\nhalt\nset x, 31\nhalt')
        await h.write(0,1); await h.done()
        assert await h.read_word(0)==0


@cocotb.test()
async def side_direction_priority_lifecycle_abort(dut):
    h=Host(dut)
    for side_dirs in (False,True):
        await h.reset()
        await h.write_word(0x16,route(side=8,side_dirs=side_dirs))
        await h.write_word(0x11,0x83e0)
        # Different state updates coexist; same-state side-set wins.
        await h.load('.sideset\nset pindirs, 15 side 0\nset pins, 0 side 1\npull block side 1\nhalt side 0')
        await h.write(0,1); await h.tick(8)
        assert await h.read_word(0x17)==0xfff
        assert await h.read_word(4)==(1 if side_dirs else 0x101)
        for selector,value in ((0x16,0),(0x17,0),(0x18,0xf00),(0x19,15)):
            before=await h.read_word(selector)
            await h.write_word(selector,value)
            assert await h.read_word(selector)==before
        await h.write(0,2)
        before=int(dut.uio_oe.value)&0xf0
        dut.ena.value=0; await h.tick(3)
        assert int(dut.uio_oe.value)&0xf0==before
        dut.ena.value=1; await h.tick()
        # Combined abort/start/resume prioritizes release, preserves FIFO.
        await h.write_word(8,0)
        await h.write(0,0x31)
        assert await h.read_word(0x17)==255
        assert await h.read(11)==1
        assert await h.read(1)&1==0
        await h.write(0,1); await h.tick(5)
        # Firmware explicitly re-arms; START itself does not.
        await h.write(0,0x20)
        await h.write_word(0x17,0xf00)
        await h.load([encode(7,0x60,side=1,sideset=True)])
        before=await h.read_word(4)
        await h.write(0,1); await h.tick(5)
        assert await h.read(1)&5==4
        assert await h.read_word(4)==before
        assert await h.read_word(0x17)==0xfff
        dut.rst_n.value=0
        from cocotb.triggers import Timer
        await Timer(1,unit='ns')
        assert int(dut.uio_oe.value)==0


@cocotb.test()
async def assembler_revision_and_checked_examples(dut):
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    import json
    import i2c_driver
    metadata=json.loads((root/'examples/i2c.json').read_text())
    assert metadata['revision']==i2c_driver.VERSION
    assert metadata['entry']==i2c_driver.ENTRY
    assert metadata['execctrl']==0x8000|(31<<5)|(i2c_driver.ENTRY<<10)
    assert metadata['instruction_words']==len(assemble((root/'examples/i2c.asm').read_text()))
    assert {int(k):v for k,v in metadata['dividers'].items()}==i2c_driver.DIVIDERS
    assert metadata['commands']==dict(bits=i2c_driver.BITS,start=i2c_driver.START,low=i2c_driver.LOW,stop=i2c_driver.STOP)
    for source in (root/'examples').glob('*.asm'):
        assert assemble(source.read_text())==[int(w,16) for w in source.with_suffix('.hex').read_text().split()]
    assert assemble('out pindirs, 32\nset pindirs, 31\nwait 1, gpio, 5')==[0x6080,0xe09f,0x2085]
    for bad in ('set null, 1','mov pindirs, x','in pindirs, 1','wait 1, gpio, 6','wait 0, pin, 31','out pindirs, 0'):
        try: assemble(bad)
        except ValueError: pass
        else: raise AssertionError(bad)


@cocotb.test()
async def partial_host_commits_and_abandoned_rx_snapshot(dut):
    h=Host(dut); await h.reset()
    await h.write_word(0x14,255)
    h.control(0x1c); dut.uio_in.value=15; await h.tick(4)
    assert int(dut.uio_oe.value)&15==0
    h.control(12); await h.tick()
    # Changing address/direction cancels the staged clear.
    assert await h.read(12)==255
    await h.write(12,0x55,held=4)
    assert await h.read(12)==0xaa
    await h.write(2,0); await h.write(3,0x42)
    h.control(0x14); dut.uio_in.value=10; await h.tick()
    h.control(4); await h.tick()
    assert await h.read(2)==0
    await h.write(4,0xa0,held=4)
    assert await h.read(2)==1
    await h.write(5,8)
    for reg in (6,7,9): await h.write(reg,0x55)
    h.control(0x1a); dut.uio_in.value=5; await h.tick()
    h.control(10); await h.tick()
    assert await h.read(11)==0
    await h.write(10,0xaa,held=4)
    assert await h.read(11)==1
    await h.load('pull block\nmov isr, osr\npush block\nhalt')
    await h.write(0,1); await h.done()
    await h.write(5,9)
    h.control(0x26); await h.tick(4)
    assert int(dut.uio_out.value)&15==5
    h.control(6); await h.tick()
    assert await h.read(11)==0  # abandoned DATA_0 read still popped exactly once
    # Snapshot upper bytes survive the abandoned low-byte nibble.
    assert await h.read(7)==0x55
    assert await h.read(9)==0x55
    assert await h.read(10)==0xaa
    assert await h.read(13)==0


@cocotb.test()
async def abort_wait_fifo_partial_transport_and_rearm(dut):
    h=Host(dut)
    for program in ('wait 1, gpio, 0','pull block','halt', 'set null, 0'):
        for value in (0,0xf00):
            await h.reset()
            await h.write_word(4,value|0xa5)
            await h.write_word(0x17,0xf00)
            await h.load([encode(7,0x60)] if program=='set null, 0' else program)
            await h.write(0,1); await h.tick(5)
            assert int(dut.uio_oe.value)&0xf0==0xf0
            assert int(dut.uio_out.value)&0xf0==value>>4
            # First nibble is not an abort, even during an execution stall.
            h.control(0x10); dut.uio_in.value=0; await h.tick(3)
            assert int(dut.uio_oe.value)&0xf0==0xf0
            h.control(0); await h.tick()
            h.control(0x10); dut.uio_in.value=2; await h.tick()
            assert int(dut.uio_oe.value)&0xf0==0
            h.control(0); await h.tick()
            assert int(dut.uo_out.value)==0xa5
            await h.write(0,1); await h.tick(4)
            assert int(dut.uio_oe.value)&0xf0==0
            await h.write(0,2)
            await h.write_word(0x17,0xf00)
            assert int(dut.uio_oe.value)&0xf0==0xf0


@cocotb.test()
async def expanded_value_mov_out_mapping_and_sideset(dut):
    h=Host(dut)
    for base in range(16):
        for op in ('out pins, 32','mov pins, osr','out pindirs, 32'):
            await h.reset()
            await h.write_word(0x16,route(base,4,side=11))
            await h.write_word(4,0x5a5); await h.write_word(0x17,0xa00)
            await h.write_word(2,0xb)
            await h.load(op+'\nhalt')
            await h.write(0,16); await h.done()
            expected=0xaff if 'pindirs' in op else 0x5a5
            for bit in range(4):
                pin=base+bit
                if (8 if 'pindirs' in op else 0)<=pin<12:
                    expected=(expected&~(1<<pin))|(((0xb>>bit)&1)<<pin)
            assert await h.read_word(0x17 if 'pindirs' in op else 4)==expected


@cocotb.test()
async def synchronization_latency_and_relative_wait_indices(dut):
    h=Host(dut)
    for disabled in (False, True):
        await h.reset()
        await h.write_word(0x16,route(width=1,in_base=0))
        await h.load('wait 1, gpio, 0\nset pins, 0\nhalt')
        await h.write(0,1)
        if disabled: dut.ena.value=0
        h.inputs=1; h.control(0)
        await h.tick(3)
        assert int(dut.uio_out.value)&0xf0==0xf0
        if disabled:
            dut.ena.value=1; await h.tick()
            assert int(dut.uio_out.value)&0xf0==0xf0
        await h.tick()
        assert int(dut.uio_out.value)&0xf0==0xe0

    for index in range(6):
        await h.reset()
        await h.write_word(0x16,route(width=1,in_base=0))
        await h.load(f'wait 1, pin, {index}\nset pins, 0\nhalt')
        await h.write(0,1)
        h.inputs=(1<<index) if index<2 else 0; h.control(0)
        dut.uio_in.value=(1<<(index+2)) if index>=2 else 0
        await h.tick(6); await h.done()
        assert int(dut.uio_out.value)&0xf0==0xe0


@cocotb.test()
async def sideset_all_indices_halt_capabilities_and_invalid_routing(dut):
    h=Host(dut)
    for direction in (False,True):
        for index in range(16):
            await h.reset()
            await h.write_word(4,0xfff)
            await h.write_word(0x17,0xf00)
            await h.write_word(0x16,route(side=index,side_dirs=direction))
            await h.write_word(0x11,0x83e0)
            await h.load('.sideset\nhalt side 0')
            await h.write(0,1); await h.done()
            expected=0xfff
            if (8 if direction else 0)<=index<12:
                expected &= ~(1<<index)
            assert await h.read_word(0x17 if direction else 4)==expected
            assert await h.read_word(4 if direction else 0x17)==0xfff
