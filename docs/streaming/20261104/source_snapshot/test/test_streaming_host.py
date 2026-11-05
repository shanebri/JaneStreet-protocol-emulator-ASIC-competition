import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from pio_host import PIOHost
from streaming.host import Stream,payload_words,receive_bytes,program,configure
from pioasm import assemble


class Bus:
    def __init__(self):
        self.bank=0; self.log=[]
        self.tx=[[],[]]; self.rx=[[],[]]; self.selector=[0,0]
        self.stage=[bytearray(4),bytearray(4)]; self.snapshot=[0,0]

    async def write(self,address,value):
        await asyncio.sleep(0)
        self.log.append(('w',self.bank,address,value))
        if address==15: self.bank=value
        elif address==5: self.selector[self.bank]=value
        elif address in (6,7,9,10):
            self.stage[self.bank][(6,7,9,10).index(address)]=value
            if address==10:
                assert self.selector[self.bank]==8
                assert len(self.tx[self.bank])<4
                self.tx[self.bank].append(int.from_bytes(self.stage[self.bank],'little'))

    async def read(self,address):
        await asyncio.sleep(0)
        self.log.append(('r',self.bank,address))
        if address==11: return len(self.tx[self.bank]) | (len(self.rx[self.bank])<<4)
        assert self.selector[self.bank]==9
        if address==6:
            assert self.rx[self.bank]
            self.snapshot[self.bank]=self.rx[self.bank].pop(0)
        return (self.snapshot[self.bank]>>(8*(6,7,9,10).index(address))) & 255


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    def test_packing_and_tail_contract(self):
        payload=bytes.fromhex('123456789a')
        self.assertEqual(payload_words(payload,'uart'),[4,0x78563412,0x9a])
        self.assertEqual(payload_words(payload,'spi'),[4,0x12345678,0x9a000000])
        self.assertEqual(receive_bytes([0x12345678,0x9a],5),payload)
        self.assertEqual(receive_bytes([0x12,0x34,0x56,0x78,0x9a],5,packed=False),payload)
        with self.assertRaises(ValueError): receive_bytes([0x12345678,0x9a00],5)
        with self.assertRaises(ValueError): payload_words(b'','uart')
        with self.assertRaises(ValueError): payload_words(bytes(65537),'spi')

    def test_program_capacity(self):
        for protocol in ('uart','spi'):
            for packed in (False,True):
                self.assertLessEqual(len(assemble(program(protocol,packed=packed))),32)
            image=Path(__file__).resolve().parents[1]/f'examples/{protocol}_packed_stream.hex'
            self.assertEqual([int(s,16) for s in image.read_text().split()],assemble(program(protocol)))

    async def test_invalid_configuration_has_no_side_effect(self):
        bus=Bus();engine=PIOHost(bus).engine(0)
        for args in (('uart',0,{}),('uart',1,{'uart_pin':8}),
                     ('spi',1,{'spi_cs':5}),('spi',1,{'ready_pin':6})):
            with self.assertRaises(ValueError):await configure(engine,args[0],args[1],**args[2])
        self.assertEqual(bus.log,[])

    async def test_two_banks_share_atomic_batches(self):
        bus=Bus(); host=PIOHost(bus)
        a=Stream(host.engine(0),'spi',bytes(range(20)))
        b=Stream(host.engine(1),'uart',bytes(range(30,50)))
        await asyncio.gather(a.service(),b.service())
        self.assertEqual(bus.tx[0],[19,0x00010203,0x04050607,0x08090a0b])
        self.assertEqual(bus.tx[1],[19,0x21201f1e,0x25242322,0x29282726])
        self.assertEqual(a.selector_writes,1)
        self.assertEqual(b.selector_writes,1)
        # Full queues never accept another write, even while clients interleave.
        await asyncio.gather(a.service(),b.service())
        self.assertEqual([len(x) for x in bus.tx],[4,4])

    async def test_snapshot_batch_and_partial_tail(self):
        bus=Bus(); host=PIOHost(bus)
        stream=Stream(host.engine(0),'spi',bytes(9))
        bus.rx[0]=[0x10203040,0x50607080,0x90]
        await stream.service()
        self.assertEqual(stream.received(),bytes.fromhex('102030405060708090'))
        self.assertEqual(stream.selector_writes,2)
        self.assertEqual(stream.data_reads,3)
        self.assertEqual(bus.rx[0],[])

    async def test_single_word_policy_and_capacity_guard(self):
        bus=Bus(); host=PIOHost(bus)
        stream=Stream(host.engine(0),'uart',bytes(range(20)))
        await stream.service(batch=False)
        self.assertEqual(bus.tx[0],[19])
        bus.tx[0]=[0]*5
        before=len(bus.log)
        with self.assertRaises(ValueError): await stream.service()
        self.assertEqual(len(bus.log)-before,2) # bank select + read only


if __name__=='__main__': unittest.main()
