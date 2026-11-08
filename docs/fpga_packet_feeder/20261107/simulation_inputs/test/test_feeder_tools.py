"""Host framing, bounded recovery and physical-capture evidence contracts."""
import asyncio
from copy import deepcopy
from functools import reduce
import json
from operator import xor
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from bringup.analyze import verify_records
from bringup.artifacts import sha, verify
from bringup.capture import CHANNELS, PHYSICAL_INPUTS, export_samples, save_json
from bringup.transport import SerialTransport
from bringup.waveforms import analyze_capture
from streaming import feeder_hardware
from streaming.feeder import (Feeder, INFO, SEQ_LOW, SEQ_HIGH, BEGIN, WORD_LOW,
                              WORD_HIGH, COMMIT, STATUS, ACTIVE, COMPLETE)
from streaming.usb_ls import symbols, inspect


class Bus:
    def __init__(self):
        self.commands=[]
        self.replies={INFO:bytes((1,2,29,3))}
        self.now=0

    def clock(self):
        self.now+=.01
        return self.now

    async def command(self, op, address=0, value=0):
        await asyncio.sleep(0)
        self.commands.append((op,address,value))
        return self.replies.get((op,address),self.replies.get(op,0))


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_is_serialized_and_full_words_are_little_endian(self):
        bus=Bus()
        client=Feeder(bus)
        payloads=(b'\xff'*8,bytes(range(8)))
        await asyncio.gather(*(client.submit(slot,slot,payload,sequence=0x12345678+slot)
                               for slot,payload in enumerate(payloads)))
        first=bus.commands.index((COMMIT,0,0))+1
        for slot,commands in enumerate((bus.commands[:first],bus.commands[first:])):
            words,_=symbols(payloads[slot])
            self.assertEqual(commands[:3],[(SEQ_LOW,slot,0x5678+slot),
                                           (SEQ_HIGH,slot,0x1234),(BEGIN,slot*3,words[0])])
            reconstructed=[]
            for index in range(3,len(commands)-1,2):
                low,high=commands[index:index+2]
                self.assertEqual((low[0],high[0],low[1],high[1]),(WORD_LOW,WORD_HIGH,slot,slot))
                reconstructed.append(low[2] | high[2]<<16)
            self.assertEqual(reconstructed,words[1:])
            self.assertEqual(commands[-1],(COMMIT,slot,0))

    async def test_invalid_inputs_have_no_transport_side_effects(self):
        bus=Bus();client=Feeder(bus)
        for slot,engine,payload,sequence in ((2,0,b'',0),(0,2,b'',0),(0,0,b'',-1),
                                             (0,0,b'',1<<32),(0,0,bytes(9),0)):
            with self.assertRaises(ValueError):
                await client.submit(slot,engine,payload,sequence=sequence)
        for operation in (client.status(2),client.abort(-1),client.release(2),
                          client.launch(2),client.completion(0,sequence=0,timeout=0)):
            with self.assertRaises(ValueError):
                await operation
        self.assertEqual(bus.commands,[])

    async def test_terminal_failure_sequence_and_poll_deadline(self):
        bus=Bus();client=Feeder(bus)
        bus.replies[(STATUS,0)]=(COMPLETE | 3<<3 | 1<<5).to_bytes(4,'little')
        bus.replies[(STATUS,2)]=(0x89abcdef).to_bytes(4,'little')
        bus.replies[(STATUS,4)]=(5 | 1<<6 | 4<<14 | 2<<22).to_bytes(4,'little')
        result=await client.completion(0,sequence=0x89abcdef)
        self.assertEqual(result,dict(state=COMPLETE,result=3,engine=1,sequence=0x89abcdef,
                                    words_sent=5,terminal_status=1,terminal_levels=4,terminal_errors=2))
        with self.assertRaisesRegex(ValueError,'sequence'):
            await client.completion(0,sequence=1)
        bus.replies[(STATUS,0)]=ACTIVE.to_bytes(4,'little')
        with self.assertRaises(TimeoutError):
            await client.completion(0,sequence=0,timeout=.025)
        self.assertTrue(all(op==STATUS for op,_,_ in bus.commands))

    async def test_serial_transport_accepts_fragmented_wide_feeder_replies(self):
        class Port:
            def write(self,request):
                if request[2]==INFO:
                    data=bytes((1,2,29,3))
                else:
                    data=(0xfedcba98).to_bytes(4,'little')
                reply=bytes((0xc3,request[1],0))+data
                self.reply=bytearray(reply+bytes((reduce(xor,reply),)))
                return len(request)
            def read(self,count):
                data=self.reply[:1];del self.reply[:1];return data
        io=SerialTransport(Port())
        await Feeder(io).identify()
        self.assertEqual(await io.command(STATUS,2),bytes.fromhex('98badcfe'))


def digital_packet(payload,data1=False,offset=10):
    _,spec=symbols(payload,data1=data1)
    samples=[2]*offset
    for index,state in enumerate(spec['expected_states']):
        count=((index+1)*100)//3-(index*100)//3
        samples.extend([state | 4]*count)
    samples.extend([2]*(8192-len(samples)))
    return samples


class EvidenceTests(unittest.TestCase):
    def test_synchronized_physical_dual_packets_and_evidence_classification(self):
        packets=[dict(engine=0,payload_hex='ff'*8,data1=False,channels=['pad0','pad1','pad2']),
                 dict(engine=1,payload_hex='0001020304050607',data1=True,channels=['pad3','in0','in1'])]
        streams=[digital_packet(bytes.fromhex(p['payload_hex']),p['data1'],i*30)
                 for i,p in enumerate(packets)]
        words=[0]*8192
        declared={}
        for packet,samples in zip(packets,streams):
            for bit,channel in enumerate(packet['channels']):
                output=f'out{packet["engine"]*3+bit}'
                declared[channel]=output
                # Unequal two/three-clock input latency checks the bounded
                # physical edge window without relaxing internal timing.
                delay=2+int(bit==1)
                for index,value in enumerate(samples):
                    words[index] |= ((value>>bit)&1)<<CHANNELS.index(output)
                    before=samples[index-delay] if index>=delay else 2
                    words[index] |= ((before>>bit)&1)<<CHANNELS.index(channel)
        physical=[sum(((word>>CHANNELS.index(channel))&1)<<bit
                      for bit,channel in enumerate(packets[0]['channels'])) for word in words]
        with self.assertRaises(ValueError):
            inspect(physical)
        self.assertEqual(inspect(physical,edge_tolerance=3)['payload_hex'],'ff'*8)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            export_samples(out,words,50_000_000,0)
            meta=dict(status='COMPLETE',evidence_kind='simulation',trigger=dict(channel='out2',falling=False),
                      expected=dict(kind='usb_feeder',packets=packets),
                      fixture_loopbacks=declared,signal_scope={name:'physical_input' if name in PHYSICAL_INPUTS
                      else 'internal_net' for name in CHANNELS})
            save_json(out/'capture.json',meta)
            self.assertFalse(analyze_capture(out)['physical_input_evidence'])
            meta['evidence_kind']='hardware_transport';save_json(out/'capture.json',meta)
            self.assertTrue(analyze_capture(out)['physical_input_evidence'])
            corrupted=words.copy();corrupted[90] ^= 1<<CHANNELS.index('pad0')
            export_samples(out,corrupted,50_000_000,0)
            with self.assertRaises(ValueError):
                analyze_capture(out)
            export_samples(out,[word | (1<<CHANNELS.index('oe0')) for word in words],50_000_000,0)
            with self.assertRaisesRegex(ValueError,'driven'):
                analyze_capture(out)

    def test_completion_evidence_is_bound_to_declared_packet(self):
        packet=dict(engine=1,payload_hex='ff',data1=True,sequence=123)
        _,spec=symbols(bytes.fromhex(packet['payload_hex']),data1=True)
        wanted=dict(result=0,words_sent=1+(spec['symbols']+3)//4,terminal_levels=0,terminal_errors=0)
        record=dict(test='feeder_completion',type='assertion',slot=0,status='PASS',
                    expected=wanted,observed=wanted,
                    completion=dict(wanted,state=COMPLETE,engine=1,sequence=123))
        manifest=dict(suite='packet_feeder',status='PASS',packets=[packet])
        self.assertEqual(verify_records(manifest,[record]),[])
        bad=deepcopy(record);bad['completion']['sequence']=124
        with self.assertRaisesRegex(ValueError,'completion'):
            verify_records(manifest,[bad])
        with self.assertRaisesRegex(ValueError,'missing'):
            verify_records(manifest,[])

    def test_hardware_open_failure_seals_reproducible_failure_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'image.bit';image.write_bytes(b'fixture')
            fixture=root/'fixture.json'
            save_json(fixture,dict(packet_feeder=True,clock_hz=50_000_000,port='TEST',
                                  image=str(image),expected_image_sha256=sha(image),capture=dict(mode='none')))
            serial=types.SimpleNamespace(Serial=unittest.mock.Mock(side_effect=OSError('board unplugged')))
            with patch.dict(sys.modules,{'serial':serial}):
                self.assertEqual(feeder_hardware.main(['--fixture',str(fixture),'--out',str(root/'run')]),1)
            verify(root/'run')
            manifest=json.loads((root/'run/manifest.json').read_text())
            self.assertEqual(manifest['status'],'FAIL')
            self.assertIn('unplugged',manifest['error'])
            self.assertIn('examples/usb_ls_tx_symbols.asm',manifest['software_sha256'])
            self.assertIn('finished_utc',manifest)
            self.assertTrue((root/'run/exception.txt').is_file())


if __name__=='__main__':
    unittest.main()
