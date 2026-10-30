import asyncio
from functools import reduce
from operator import xor
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bringup.transport import SerialTransport


class Port:
    def __init__(self, corrupt=False, stale=False, status=0):
        self.corrupt,self.stale,self.status=corrupt,stale,status
    def write(self, packet):
        r=bytes((0xc3,(packet[1]+int(self.stale))&255,self.status,0x21,0,0,0))
        self.reply=bytearray(r+bytes((reduce(xor,r)^int(self.corrupt),)))
        return len(packet)
    def read(self, size):
        # Deliberately fragmented serial response.
        value=bytes(self.reply[:1]); del self.reply[:1]; return value


class TransportTests(unittest.TestCase):
    def test_fragmented_reply_and_wrap(self):
        io=SerialTransport(Port()); io.sequence=255
        self.assertEqual(asyncio.run(io.read(15)),0x21)
        self.assertEqual(io.sequence,0)
    def test_corrupt_stale_rejected_no_retry(self):
        for kwargs in ({'corrupt':True},{'stale':True},{'status':2}):
            with self.assertRaises(IOError): asyncio.run(SerialTransport(Port(**kwargs)).read(15))
    def test_deadline(self):
        port=Port(); port.read=lambda n:b''
        with self.assertRaises(TimeoutError): asyncio.run(SerialTransport(port,timeout=.001).read(15))
    def test_validation(self):
        with self.assertRaises(ValueError): asyncio.run(SerialTransport(Port()).write(16,0))


if __name__=='__main__': unittest.main()
