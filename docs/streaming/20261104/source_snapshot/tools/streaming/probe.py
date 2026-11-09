"""Read-only bridge INFO probe; does not reset, program or start a PIO engine."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from bringup.transport import SerialTransport,INFO


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='COM3')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    import serial
    record=dict(port=a.port,scope='read-only bridge INFO; no reset or protocol stimulus',traffic=[])
    try:
        with serial.Serial(a.port,115200,timeout=.1,write_timeout=2) as port:
            io=SerialTransport(port,trace=lambda kind,value:record['traffic'].append(dict(kind=kind,value=value)))
            record.update(status='IDENTIFIED',bridge_version=asyncio.run(io.command(INFO)))
    except Exception as exc:
        record.update(status='UNAVAILABLE',error=repr(exc))
    (a.out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
