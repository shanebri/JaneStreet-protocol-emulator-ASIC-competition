"""The feature branch works with the committed bring-up byte transport."""
from functools import reduce
from operator import xor
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from streaming.transport import INFO,SerialTransport


class Port:
    def __init__(self,version=2,corrupt=False):
        self.version=version;self.corrupt=corrupt;self.writes=[];self.reply=bytearray()

    def write(self,packet):
        self.writes.append(packet)
        assert packet[2]==INFO
        assert reduce(xor,packet)==0
        reply=bytes((0xc3,packet[1],0,self.version,0,0,0))
        reply+=bytes((reduce(xor,reply) ^ int(self.corrupt),))
        self.reply.extend(reply)
        return len(packet)

    def read(self,count):
        result=bytes(self.reply[:count]);del self.reply[:count]
        return result


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_v2_query_uses_only_info(self):
        port=Port();io=SerialTransport(port)
        self.assertEqual(await io.require_v2(),2)
        self.assertEqual(len(port.writes),1)
        self.assertEqual(port.writes[0][2],INFO)

    async def test_old_bridge_is_rejected(self):
        with self.assertRaises(ValueError):await SerialTransport(Port(version=1)).require_v2()

    async def test_corruption_prevents_further_side_effects(self):
        port=Port(corrupt=True);io=SerialTransport(port)
        with self.assertRaises(IOError):await io.command(INFO)
        self.assertTrue(io.poisoned)
        with self.assertRaises(IOError):await io.write(0,1)
        self.assertEqual(len(port.writes),1)


if __name__=='__main__':unittest.main()
