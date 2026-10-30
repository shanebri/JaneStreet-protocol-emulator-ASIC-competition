"""Build the Arty programmable host image, without programming hardware."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
EXTRA=('byte_nibble_host.sv','spi_test_uart_tx.sv','bringup_uart_rx.sv',
       'bringup_bridge.sv','arty_bringup_top.sv')


def sources(root=ROOT):
    text=(root/'info.yaml').read_text().split('  source_files:',1)[1]
    names=[]
    for line in text.splitlines()[1:]:
        if not line.strip(): continue
        match=re.fullmatch(r'    - "([^"]+)"\s*',line)
        if not match: break
        names.append(root/'src'/match[1])
    if not names: raise ValueError('empty submission source manifest')
    names += [root/'fpga'/name for name in EXTRA]
    for path in [*names,root/'fpga/arty_bringup.xdc',root/'fpga/build_bringup.tcl']:
        if not path.is_file(): raise FileNotFoundError(path)
    return names


def find_vivado(explicit=None):
    specified=explicit or os.environ.get('VIVADO')
    if specified:
        path=Path(specified)
        if not path.is_file(): raise FileNotFoundError(f'Vivado executable not found: {path}')
        return path.resolve()
    found=shutil.which('vivado')
    if found: return Path(found).resolve()
    home=os.environ.get('XILINX_VIVADO')
    if home:
        for name in ('vivado.bat','vivado'):
            candidate=Path(home)/'bin'/name
            if candidate.is_file(): return candidate.resolve()
    candidates=[]
    for base in ('C:/Xilinx/Vivado','C:/AMD/Vivado','C:/AMDDesignTools'):
        parent=Path(base)
        if parent.is_dir():
            candidates.extend(parent.glob('*/bin/vivado.bat'))
            candidates.extend(parent.glob('*/Vivado/bin/vivado.bat'))
    if candidates: return sorted(candidates,key=lambda p:str(p),reverse=True)[0].resolve()
    raise FileNotFoundError('Vivado not found. Run from a Vivado-enabled terminal, or pass '
                            '--vivado "C:/path/to/Vivado/version/bin/vivado.bat".')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vivado',help='path to vivado.bat (Windows) or vivado (Linux)')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--port',default='COM3',help='port written to generated fixture.json')
    p.add_argument('--out',type=Path,help='new output directory; never overwrites a build')
    p.add_argument('--check',action='store_true',help='check prerequisites only')
    a=p.parse_args(argv)
    if a.jobs<1: p.error('--jobs must be positive')
    try:
        inputs=sources()
        vivado=find_vivado(a.vivado)
        print(f'Vivado: {vivado}\nSources: {len(inputs)}; top: arty_bringup_top; part: xc7a100tcsg324-1')
        if a.check: return 0
        out=(a.out or ROOT/'fpga/build/bringup'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')).resolve()
        out.mkdir(parents=True,exist_ok=False)
        (out/'.gitignore').write_text('*\n')
        manifest=out/'sources.txt'
        manifest.write_text(''.join(path.resolve().as_posix()+'\n' for path in inputs))
        command=[str(vivado),'-mode','batch','-notrace','-source',str(ROOT/'fpga/build_bringup.tcl'),
                 '-tclargs',str(manifest),str(a.jobs)]
        # Windows batch launch involves cmd.exe; reject shell metacharacters.
        if vivado.suffix.lower() in ('.bat','.cmd') and any(re.search(r'[&|<>^%!\r\n"]',s) for s in command):
            raise ValueError('Batch launcher paths must not contain shell metacharacters')
        record=dict(status='RUNNING',command=command,started=datetime.now(timezone.utc).isoformat(),
                    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    sources_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
                                    for f in [*inputs,ROOT/'fpga/arty_bringup.xdc',ROOT/'fpga/build_bringup.tcl']})
        try:
            print(f'Building in {out}\nVivado may take several minutes. Full output: {out / "console.log"}',flush=True)
            with (out/'console.log').open('w') as log:
                subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
            image=out/'arty_bringup_top.bit'
            if not image.is_file() or not image.stat().st_size: raise RuntimeError('Vivado produced no bitstream')
            record.update(status='PASS',image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
            fixture=dict(bridge_protocol=1,clock_hz=50000000,port=a.port,baud=115200,image=str(image))
            (out/'fixture.json').write_text(json.dumps(fixture,indent=2)+'\n')
            print(f'Build passed. Program this file in Hardware Manager:\n{image}\n')
            print('After programming, run:\n'+subprocess.list2cmdline([sys.executable,str(ROOT/'tools/bringup/run.py'),
                  '--fixture',str(out/'fixture.json'),'--suite','smoke','--out',str(out/'smoke-001')]))
            print('Review timing_summary.rpt, check_timing.rpt, cdc.rpt and exceptions.rpt before board use.')
        except BaseException as exc:
            record.update(status='FAIL',error=str(exc)); raise
        finally:
            record['finished']=datetime.now(timezone.utc).isoformat()
            (out/'build.json').write_text(json.dumps(record,indent=2)+'\n')
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'BUILD FAILED: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__': sys.exit(main())
