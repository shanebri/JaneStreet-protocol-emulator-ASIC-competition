"""Freeze a bank-local registered SRAM portal on the verified supply repair."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import production_trial as trial

BASE=trial.REPO/'test/sim_build/packet_sram_repair_20261030_04'
trial.ROOT=trial.REPO/'test/sim_build/packet_sram_buffered_20261030_01'
root=trial.ROOT


def freeze():
    root.mkdir(exist_ok=False); (root/'run').mkdir()
    for folder in ('src','tools/timing','test'):
        shutil.copytree(BASE/folder,root/folder,ignore=shutil.ignore_patterns('sim_build','__pycache__','*.fst','*.vcd','results.xml','gate_level_netlist.v','user_config.json','config_merged.json'))
    for name in ('info.yaml','librelane_plugin_pio.py'): shutil.copy2(BASE/name,root/name)
    (root/'tt').symlink_to(trial.TOOLING/'tt',target_is_directory=True)
    shutil.copy2(trial.REPO/'tools/packet_sram/portal_registered.sv',root/'src/packet/packet_sram_portal.sv')
    # Relocate physical view/config references, without changing constraints.
    def relocate(obj):
        if isinstance(obj,str): return obj.replace(str(BASE),str(root))
        if isinstance(obj,list): return [relocate(v) for v in obj]
        if isinstance(obj,dict): return {k:relocate(v) for k,v in obj.items()}
        return obj
    config=relocate(json.loads((root/'src/config.json').read_text()))
    (root/'src/config.json').write_text(json.dumps(config,indent=2)+'\n')
    bank=(trial.REPO/'src/pio_host_bank.sv').read_text()
    bank=bank.replace('module pio_host_bank (','module pio_host_bank #(parameter PACKET_PORTAL=0) (')
    bank=bank.replace('    output wire [5:0] control_command', '''    input wire [2:0] packet_status,
    input wire [5:0] packet_address,
    input wire [15:0] packet_wdata, packet_result,
    output reg packet_commit,
    output reg [1:0] packet_operation,
    output reg [16:0] packet_payload,
    output wire [5:0] control_command''')
    bank=bank.replace('    reg [7:0] imem_low;', '''    reg [4:0] packet_select;
    wire packet_selected = PACKET_PORTAL && |packet_select;
    wire [31:0] packet_value =
        ({32{packet_select[0]}} & {29'd0,packet_status}) |
        ({32{packet_select[1]}} & {26'd0,packet_address}) |
        ({32{packet_select[2]}} & {16'd0,packet_wdata}) |
        ({32{packet_select[4]}} & {16'd0,packet_result});
    always @(posedge clk) begin
        if (!rst_n) begin
            packet_select<=0; packet_commit<=0; packet_operation<=0; packet_payload<=0;
        end else if (PACKET_PORTAL) begin
            packet_commit<=word_write && (data_address==8'h21 || data_address==8'h22 || data_address==8'h23);
            if (word_write) begin
                packet_operation<=data_address[1:0];
                packet_payload<={ (|write_word[31:16]) ||
                    (data_address==8'h23 &&
                     (((write_word[15:0]==1 || write_word[15:0]==2) && (packet_status[0] || packet_status[1])) ||
                      (write_word[15:0]==4 && packet_status[0]))), write_word[15:0]};
            end
            if (write_en && address==5)
                packet_select<={write_data==8'h24,write_data==8'h23,write_data==8'h22,write_data==8'h21,write_data==8'h20};
        end
    end
    reg [7:0] imem_low;''')
    bank=bank.replace('6: read_data = selected_data[7:0];','6: read_data = packet_selected ? packet_value[7:0] : selected_data[7:0];')
    bank=bank.replace('if (snapshot_read) data_snapshot <= selected_data;','if (snapshot_read) data_snapshot <= packet_selected ? packet_value : selected_data;')
    (root/'src/pio_host_bank.sv').write_text(bank)
    subsystem=(trial.REPO/'src/pio_subsystem.sv').read_text()
    subsystem=subsystem.replace('    genvar e;', '''    wire [1:0] packet_commit;
    wire [1:0] packet_operation [0:1];
    wire [16:0] packet_payload [0:1];
    wire [2:0] packet_status;
    wire [5:0] packet_address;
    wire [15:0] packet_wdata, packet_result;
    wire [1:0] command_operation = ({2{packet_commit[0]}} & packet_operation[0]) | ({2{packet_commit[1]}} & packet_operation[1]);
    wire [16:0] command_payload = ({17{packet_commit[0]}} & packet_payload[0]) | ({17{packet_commit[1]}} & packet_payload[1]);
    packet_sram_portal packet (.clk(clk),.rst_n(rst_n),.enable(enable),
        .commit(|packet_commit),.operation(command_operation),.payload(command_payload),
        .packet_status(packet_status),.packet_address(packet_address),
        .packet_wdata(packet_wdata),.packet_result(packet_result));
    genvar e;''')
    subsystem=subsystem.replace('pio_host_bank bank (','pio_host_bank #(.PACKET_PORTAL(1)) bank (')
    subsystem=subsystem.replace('.control_command(local_control));','''.control_command(local_control),
            .packet_status(packet_status),.packet_address(packet_address),
            .packet_wdata(packet_wdata),.packet_result(packet_result),
            .packet_commit(packet_commit[e]),.packet_operation(packet_operation[e]),.packet_payload(packet_payload[e]));''')
    (root/'src/pio_subsystem.sv').write_text(subsystem)
    files=[p for folder in ('src','tools/timing','test') for p in (root/folder).rglob('*') if p.is_file()]
    files += [root/'info.yaml',root/'librelane_plugin_pio.py']
    (root/'frozen_inputs.json').write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},indent=2)+'\n')


if __name__=='__main__':
    if '--worker' in sys.argv: trial.worker()
    elif '--freeze-only' in sys.argv: freeze(); print(root)
    else:
        freeze()
        command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command','python3','-B',str(Path(__file__).resolve()),'--worker']
        with (root/'launcher.log').open('w') as log:
            proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
        print('Started bank-local registered portal trial',proc.pid)
