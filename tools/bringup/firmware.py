"""Load assembly through the programmed FPGA bridge; optionally start and read RX."""
import argparse
import asyncio
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pioasm import assemble
from pio_host import PIOHost, CAPABILITIES, DUAL_CAPABILITIES
from bringup.transport import SerialTransport
from bringup.scenarios import load, equal


def number(text): return int(text,0)


def setting(text):
    try:
        key,value=map(number,text.split('='))
        if not 0<=key<=255 or not 0<=value<=0xffffffff: raise ValueError()
        return key,value
    except ValueError: raise argparse.ArgumentTypeError('use selector=value, e.g. 0x13=31')


async def execute(io,args,words):
    if not args.no_reset: await io.reset()
    engine=PIOHost(io).engine(args.engine)
    equal(await engine.read(15),0x21,'host revision')
    equal(await engine.read_word(CAPABILITIES),DUAL_CAPABILITIES,'dual capabilities')
    await engine.write(0,2|4)  # Stop selected engine and clear its FIFOs.
    await load(engine,words)
    async with engine.transaction() as bus:
        for i,word in enumerate(words):
            await bus.write(2,i)
            equal(await bus.read(3)|(await bus.read(4)<<8),word,f'instruction {i}')
    # Establish entry 0, wrap 0..31; preset or explicit settings may override.
    await engine.write_word(0x11,31<<5)
    presets={'none':(), 'uart':((0x12,0x1008),(0x10,3),(0x13,31)),
             'spi':((4,4),(0x12,0x20a08),(0x10,0),(0x11,0x83e0),(0x13,32))}
    for selector,value in (*presets[args.preset],*args.set):
        await engine.write_word(selector,value)
    for word in args.tx: await engine.write_word(8,word)
    print(f'Loaded and read back {len(words)} instructions in engine {args.engine}.')
    if not args.start: return
    await engine.write(0,1)
    deadline=time.monotonic()+args.timeout
    received=[]
    while True:
        status=await engine.read(1)
        if status&4: raise RuntimeError('PIO instruction fault')
        level=await engine.read(11)
        if len(received)<args.rx and level&0x70:
            received.append(await engine.read_word(9))
            print(f'RX {received[-1]:08X}')
        if not status&1 and len(received)==args.rx: break
        if time.monotonic()>=deadline: raise TimeoutError('firmware completion/RX deadline')
    print('Firmware halted without an instruction fault.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--program',type=Path,required=True)
    p.add_argument('--engine',type=int,choices=(0,1),default=0)
    p.add_argument('--preset',choices=('none','uart','spi'),default='none')
    p.add_argument('--set',type=setting,action='append',default=[])
    p.add_argument('--tx',type=number,action='append',default=[],help='32-bit FIFO word; repeat at most four times')
    p.add_argument('--rx',type=int,default=0,help='number of RX words to drain while waiting')
    p.add_argument('--start',action='store_true',help='start and wait for HALT; otherwise load only')
    p.add_argument('--no-reset',action='store_true',help='preserve peer engine; selected engine still stopped/FIFOs cleared')
    p.add_argument('--timeout',type=float,default=5)
    args=p.parse_args()
    if args.timeout<=0 or args.rx<0 or len(args.tx)>4 or any(not 0<=x<=0xffffffff for x in args.tx):
        p.error('positive timeout, nonnegative RX count and at most four uint32 TX words required')
    if args.rx and not args.start: p.error('--rx requires --start')
    try:
        words=assemble(args.program.read_text())
        if not 1<=len(words)<=32: raise ValueError('program must contain 1..32 instructions')
        import serial
        with serial.Serial(args.port,115200,timeout=.05,write_timeout=2) as port:
            asyncio.run(execute(SerialTransport(port),args,words))
        return 0
    except (OSError,ValueError,RuntimeError,TimeoutError,AssertionError) as exc:
        print(f'FAIL: {exc}',file=sys.stderr); return 1


if __name__=='__main__': sys.exit(main())
