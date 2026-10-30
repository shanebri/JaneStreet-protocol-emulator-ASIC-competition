"""Package-pin SRAM regression, usable with the identical RTL or gate netlist."""
import cocotb
from test import Host,CTRL,PINCTRL,DIVIDER

ADDRESS,WDATA,COMMAND,STATUS,RDATA=0x21,0x22,0x23,0x20,0x24


async def complete(h):
    for _ in range(4):
        status=await h.read_word(STATUS)
        if status&2:
            assert not status&1
            return status
    raise AssertionError('SRAM command did not complete within the bounded host polls')


@cocotb.test()
async def packet_sram_host_roundtrip_and_execution(dut):
    h=Host(dut); await h.reset()
    await h.write_word(PINCTRL,8); await h.write_word(DIVIDER,1)
    await h.load('set pins, 1\nset pins, 0\njmp 0')
    await h.write(CTRL,1); await h.tick(6)
    begin=len(h.samples)
    words=[(0x91a5 ^ (i*257))&0xffff for i in range(64)]
    for i,value in enumerate(words):
        await h.write(15,i&1)
        await h.write_word(ADDRESS,i); await h.write_word(WDATA,value)
        await h.write_word(COMMAND,2)
        assert await complete(h)==2
        assert await h.read_word(RDATA)==0
        await h.write_word(COMMAND,4)
    for i in reversed(range(64)):
        await h.write(15,i&1); await h.write_word(ADDRESS,i)
        await h.write_word(COMMAND,1); assert await complete(h)==2
        assert await h.read_word(RDATA)==words[i]
        await h.write_word(COMMAND,1)
        assert await h.read_word(STATUS)==6
        assert await h.read_word(RDATA)==words[i]
        await h.write_word(COMMAND,4)
    # Pending byte staging is bank-local; the complete word commits globally.
    await h.write(15,0); await h.write_word(ADDRESS,7)
    await h.write(5,WDATA); await h.write(6,0xdc); await h.write(7,0xfe); await h.write(9,0)
    await h.write(15,1); await h.write_word(WDATA,0x1234)
    await h.write(15,0); await h.write(10,0)
    assert await h.read_word(WDATA)==0xfedc
    await h.write_word(COMMAND,2); assert await complete(h)==2
    await h.write_word(COMMAND,4); words[7]=0xfedc
    for bad_address in (64,0x10000,0x80000000):
        await h.write_word(ADDRESS,bad_address)
        assert await h.read_word(ADDRESS)==7
        assert await h.read_word(STATUS)==4
        await h.write_word(COMMAND,4)
    samples=[value&1 for value in h.samples[begin:]]
    assert len(samples)>100 and sum(samples[:3])==1
    assert all(value==samples[index%3] for index,value in enumerate(samples)), 'Packet access changed instruction execution cycles'
    # Reset invalidates metadata and cancels response visibility, retaining bits.
    await h.reset(); assert await h.read_word(STATUS)==0
    for i in (0,7,31,63):
        await h.write_word(ADDRESS,i); await h.write_word(COMMAND,1)
        assert await complete(h)==2
        assert await h.read_word(RDATA)==words[i]
        await h.write_word(COMMAND,4)
