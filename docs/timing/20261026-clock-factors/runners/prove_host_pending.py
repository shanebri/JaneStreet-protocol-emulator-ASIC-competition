"""Unbounded reset-qualified host-state and specialized commit-pulse proof."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold', type=Path, required=True)
    p.add_argument('--gate', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    for role, path in (('gold', a.gold), ('gate', a.gate)):
        text = path.read_text().replace('module host_interface (', f'module host_{role} (')
        text = text.replace('output wire write_intent,',
            'output wire [23:0] formal_state, output wire formal_invariant, output wire write_intent,')
        if role == 'gold':
            text = text.replace('read_intent\n);', 'read_intent, word_write_intent\n);')
            extra = "assign word_write_intent = write_intent && address == 4'ha;\nassign formal_invariant = 1'b1;"
        else:
            extra = "assign formal_invariant = pending_word == (pending && !pending_read && pending_address == 4'ha);"
        text = text.replace('endmodule', extra+'\nassign formal_state = {armed,pending,pending_read,valid_read,pending_address,low,captured,data_out};\nendmodule')
        (a.out/f'{role}.sv').write_text(text)
    ports = '.clk(clk),.rst_n(rst_n),.ena(ena),.control(control),.data_in(data_in),.read_data(read_data)'
    wrapper = '''module host_miter(input clk,rst_n,ena,input [7:0] control,read_data,input [3:0] data_in,output mismatch);
reg initialized=0;
always @(posedge clk) if (!rst_n) initialized <= 1;
wire [49:0] g,c;
'''
    # Common outputs, complete shared state, specialized pulse and its invariant.
    connections = [('address', '3:0'), ('write_en','4'), ('read_en','5'), ('write_data','13:6'),
                   ('data_out','17:14'), ('data_oe','21:18'), ('write_intent','22'),
                   ('read_intent','23'), ('word_write_intent','24'), ('formal_state','48:25'),
                   ('formal_invariant','49')]
    for role, wire in (('gold','g'), ('gate','c')):
        wrapper += f'host_{role} {role}({ports},'+','.join(f'.{name}({wire}[{bits}])' for name,bits in connections)+');\n'
    wrapper += 'assign mismatch = initialized && (g != c);\nendmodule\n'
    (a.out/'miter.sv').write_text(wrapper)
    script = ('read_verilog -formal -sv gold.sv gate.sv miter.sv\n'
              'prep -top host_miter -flatten\n'
              'sat -seq 4 -tempinduct -maxsteps 12 -set-def-inputs -prove mismatch 0 -verify\n')
    (a.out/'proof.ys').write_text(script)
    with (a.out/'proof.log').open('w') as log:
        result = subprocess.run(['yosys','-s','proof.ys'], cwd=a.out, stdout=log, stderr=subprocess.STDOUT)
    success = result.returncode == 0 and 'Induction step proven: SUCCESS!' in (a.out/'proof.log').read_text()
    (a.out/'result.json').write_text(json.dumps(dict(status='pass' if success else 'fail',
        scope='unbounded after first synchronous reset; all inputs defined and unconstrained',
        sha256={str(v):hashlib.sha256(v.read_bytes()).hexdigest() for v in (a.gold,a.gate,Path(__file__))}),indent=2)+'\n')
    if not success:
        p.exit(1,'Host proof failed; inspect proof.log\n')
    print('PASS: unbounded host-state, pending-class invariant and same-edge commit equivalence')


if __name__ == '__main__':
    main()
