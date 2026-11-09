"""Run finite autonomous USB-symbol packets and retain board evidence."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from bringup.artifacts import asic_inputs, seal, sha
from bringup.capture import Recorder, save_json
from bringup.transport import SerialTransport
from streaming.feeder import Feeder, configure
from streaming.usb_ls import symbols

CHANNELS={0:['pad0','pad1','pad2'],1:['pad3','in0','in1']}


async def execute(io,fixture,out,packets,emit):
    client=Feeder(io)
    await client.identify()
    mode=fixture.get('capture',{}).get('mode','none')
    if mode not in ('none','fpga'):
        raise ValueError('capture.mode must be none or fpga')
    if mode=='fpga':
        loopbacks={channel:f'out{packet["engine"]*3+bit}' for packet in packets
                   for bit,channel in enumerate(CHANNELS[packet['engine']])}
        if (fixture['capture'].get('loopbacks')!=loopbacks
                or fixture['capture'].get('loopbacks_confirmed') is not True):
            raise ValueError('confirm the DP/DM/marker loopbacks described in docs/fpga_packet_feeder.md')
        if (await io.trace_status())['depth']<8192:
            raise ValueError('USB feeder capture requires the 8192-sample observer')
    await io.reset()
    for packet in packets:
        await configure(io,packet['engine'])
    expected=[]
    for slot,packet in enumerate(packets):
        spec=await client.submit(slot,packet['engine'],bytes.fromhex(packet['payload_hex']),
                                 sequence=packet['sequence'],data1=packet['data1'])
        expected.append(spec)
    recorder=Recorder(io,out,fixture,emit,image_sha256=fixture['expected_image_sha256'])
    try:
        if mode=='fpga':
            if (await io.sample_pads())['oe']:
                raise ValueError('capture pads must be released inputs')
            await recorder.arm('usb-feeder',channel=f'out{packets[0]["engine"]*3+2}',falling=False,
                expected=dict(kind='usb_feeder',packets=[dict(packet,channels=CHANNELS[packet['engine']]) for packet in packets]))
        else:
            await recorder.arm('usb-feeder',channel='out2')
        await client.launch(None if len(packets)==2 else 0)
        # The complete scripts run without any further PC request.
        begin=time.monotonic_ns()
        await asyncio.sleep(.02)
        emit(dict(test='quiet_window',type='observation',begin_monotonic_ns=begin,
                  end_monotonic_ns=time.monotonic_ns(),minimum_ns=20_000_000))
        completions=[await client.completion(slot,sequence=packet['sequence']) for slot,packet in enumerate(packets)]
        await recorder.finish()
    except BaseException:
        if recorder.current is not None:
            try:
                await recorder.cancel('packet feeder run failed before capture completed')
            except Exception:
                pass  # Preserve the original error; capture failure is already recorded.
        raise
    for slot,(completion,spec) in enumerate(zip(completions,expected)):
        wanted=dict(result=0,words_sent=1+(spec['symbols']+3)//4,terminal_levels=0,terminal_errors=0)
        observed={key:completion[key] for key in wanted}
        emit(dict(test='feeder_completion',type='assertion',status='PASS' if wanted==observed else 'FAIL',
                  slot=slot,expected=wanted,observed=observed,completion=completion))
        if observed!=wanted:
            raise AssertionError(f'slot {slot} did not complete successfully')
    for slot in range(len(packets)):
        await client.release(slot)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--engine',type=int,choices=(0,1),help='send one slot on this engine; default runs both')
    parser.add_argument('--payload-hex',default='ffffffffffffffff')
    parser.add_argument('--peer-payload-hex',default='0001020304050607')
    args=parser.parse_args(argv)
    fixture=json.loads(args.fixture.read_text())
    if (fixture.get('packet_feeder') is not True or fixture.get('clock_hz')!=50_000_000
            or not fixture.get('port') or fixture['port'].startswith('EDIT')):
        parser.error('fixture must identify the feeder image, 50 MHz clock and actual bridge port')
    image=Path(fixture['image'])
    if not image.is_absolute():
        image=args.fixture.resolve().parent/image
    if sha(image)!=fixture.get('expected_image_sha256'):
        parser.error('selected image does not match the fixture hash')
    engines=(0,1) if args.engine is None else (args.engine,)
    payloads=(args.payload_hex,args.peer_payload_hex)
    packets=[]
    for slot,engine in enumerate(engines):
        payload=bytes.fromhex(payloads[slot])
        symbols(payload,data1=bool(slot))
        packets.append(dict(engine=engine,payload_hex=payload.hex(),sequence=slot+1,data1=bool(slot)))
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    save_json(out/'fixture.json',fixture)
    manifest=dict(status='RUNNING',suite='packet_feeder',seed=0,evidence_kind='hardware_transport',
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  worktree_status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
                  image_sha256=fixture['expected_image_sha256'],fixture=fixture,packets=packets,
                  asic_inputs=asic_inputs(ROOT),image_identity_scope='operator-selected image file and feeder capability query',
                  software_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in
                      [*sorted((ROOT/'tools/streaming').glob('*.py')),
                       *sorted((ROOT/'tools/bringup').glob('*.py')),
                       ROOT/'tools/pio_host.py',ROOT/'tools/pioasm.py',
                       ROOT/'examples/usb_ls_tx_symbols.asm',ROOT/'examples/usb_ls_tx_symbols.hex']})
    save_json(out/'manifest.json',manifest)
    code=1
    with (out/'transport.jsonl').open('w') as traffic,(out/'results.jsonl').open('w') as results:
        def emit(record):
            results.write(json.dumps(record)+'\n');results.flush()
        def trace(direction,data):
            traffic.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(),direction=direction,data=data))+'\n')
            traffic.flush()
        try:
            import serial
            with serial.Serial(fixture['port'],fixture.get('baud',115200),timeout=.05,write_timeout=2,
                               rtscts=False,dsrdtr=False) as port:
                io=SerialTransport(port,trace=trace)
                asyncio.run(execute(io,fixture,out,packets,emit))
            manifest['status']='PASS';code=0
        except BaseException as exc:
            manifest.update(status='FAIL',error=repr(exc))
            (out/'exception.txt').write_text(traceback.format_exc())
            emit(dict(test='session',status='FAIL',error=repr(exc)))
        finally:
            manifest['finished_utc']=datetime.now(timezone.utc).isoformat()
            save_json(out/'manifest.json',manifest)
    seal(out)
    print(f'{manifest["status"]} {out}')
    return code


if __name__=='__main__':
    raise SystemExit(main())
