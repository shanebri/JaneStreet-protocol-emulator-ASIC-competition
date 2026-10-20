"""Reproducible generic structural check using the submission manifest.

python test/synth.py --yosys yosys [--revision HEAD] [--name baseline]
The optional Git revision is read into an isolated build directory, never checked
out over working changes. -noabc is intentional for comparable portable stats.
"""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yosys', default='yosys')
    parser.add_argument('--revision')
    parser.add_argument('--name', default='final')
    args = parser.parse_args()
    output = ROOT/'test'/'sim_build'/('synth_'+args.name)
    output.mkdir(parents=True, exist_ok=True)

    def read(path):
        if args.revision:
            return subprocess.check_output(['git','show',f'{args.revision}:{path}'],cwd=ROOT,text=True)
        return (ROOT/path).read_text()

    sources=[]
    for line in read('info.yaml').split('  source_files:\n',1)[1].splitlines():
        if not line.startswith('    - '):
            break
        name='src/'+line.split('"')[1]
        target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(read(name))
        sources.append('"'+target.as_posix()+'"')
    script = ('read_verilog -sv '+' '.join(sources)+'; synth -noabc -top tt_um_shanebri_top; '
              'check -assert; select -assert-none t:$dlatch t:$dlatchsr t:$_DLATCH_*; stat')
    with (output/'synthesis.log').open('w') as log:
        subprocess.run([args.yosys,'-Q','-T','-p',script],stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
    print(output/'synthesis.log')


if __name__=='__main__':
    main()
