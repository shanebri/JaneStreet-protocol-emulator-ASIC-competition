"""Candidate-only flow support; preserve strict acceptance and clock coverage."""
import shutil
from pathlib import Path


def replace_once(text,old,new):
    assert text.count(old)==1,old[:100]
    return text.replace(old,new,1)


def install(root):
    tool=root/'tools/timing'
    shutil.copy2(Path(__file__).with_name('packet_render.py'),tool/'packet_render.py')
    shutil.copy2(Path(__file__).with_name('packet_fanout_policy.py'),tool/'packet_fanout_policy.py')
    path=tool/'production_flow.py'; text=path.read_text()
    text=replace_once(text,'from data_eco_trial import script','from data_eco_trial import script\nfrom packet_render import render_script')
    text=replace_once(text,'return script(operations)','return render_script(operations)')
    text=replace_once(text,"        with (Path(self.step_dir)/'qualification.log').open('w') as log:", '''        parent=Path(self.config['DESIGN_DIR']).parent/'parent/69-openroad-stapostpnr/state_out.json'
        comparison=[sys.executable,str(TOOL/'compare_timing.py'),'--parent',str(parent),
            '--candidate',str(Path(self.step_dir).parent),'--out',str(Path(self.step_dir)/'parent_comparison.json')]
        with (Path(self.step_dir)/'parent_comparison.log').open('w') as log:
            subprocess.run(comparison,stdout=log,stderr=subprocess.STDOUT,check=True)
        with (Path(self.step_dir)/'qualification.log').open('w') as log:''')
    text=replace_once(text,"return self.config['PIO_INCREMENTAL_ECO_CONTRACTS'][self.contract_index]", '''contract=Path(self.step_dir)/'measured_fanout_contract.json'
        configured=self.config['PIO_INCREMENTAL_ECO_CONTRACTS'][self.contract_index]
        if json.loads(Path(configured).read_text()).get('entries'):
            return configured
        state=json.loads((Path(self.step_dir)/'state_in.json').read_text())
        run_tool(self,'packet_fanout_policy.py',['--odb',state['odb'],'--out',contract])
        return contract''')
    path.write_text(text)
    # Keep the original 39 gate tests, then exercise SRAM through package pins
    # on the exact same gate netlist using the vendor's functional model.
    makefile=root/'test/Makefile'
    if makefile.is_file():
        make=makefile.read_text()
        make=replace_once(make,'ifneq ($(GATES),yes)', '''PROJECT_SOURCES += packet/packet_sram.sv packet/packet_sram_portal.sv
COMPILE_ARGS += -DFUNCTIONAL
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog/RM_IHPSG13_1P_64x16_c2.v
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog/RM_IHPSG13_1P_core_behavioral.v

ifneq ($(GATES),yes)''')
        makefile.write_text(make)
        shutil.copy2(Path(__file__).with_name('test_packet_pins.py'),root/'test/test_packet_pins.py')
    path=tool/'qualify_gds_artifact.py'; text=path.read_text()
    text=replace_once(text,"        gate_env = dict(env,", '''        support=a.test_source.resolve().parent
        (out/'tools').mkdir(exist_ok=True)
        for py in (support/'tools').glob('*.py'):
            shutil.copy2(py,out/'tools'/py.name)
        shutil.copytree(support/'examples',out/'examples')
        gate_env = dict(env,''')
    text=replace_once(text,"        manifest['status'] = 'complete'", '''        command(['make','-B','GATES=yes','COCOTB_TEST_MODULES=test_packet_pins','COCOTB_RESULTS_FILE=packet_results.xml'],
                'packet_gate_tests',test,gate_env)
        packet=ET.parse(test/'packet_results.xml')
        if len(packet.findall('.//testcase'))!=1 or any(packet.findall('.//'+tag) for tag in ('failure','error','skipped')):
            raise ValueError('Packet SRAM gate test failed or did not run')
        manifest['checks']['packet_gate_test']=dict(status='pass',tests=1,netlist_sha256=sha(test/'gate_level_netlist.v'))
        manifest['status'] = 'complete' ''')
    path.write_text(text)
    path=tool/'audit_data_eco.py'; text=path.read_text()
    text=replace_once(text,"if any(pin=='CLK' for _,pin in loads[net]):",'if any(sink in before[4] for sink in loads[net]):')
    old="""        count=len(loads[net])
        if net in roots or count < 1 or op['max_loads'] < 1:"""
    new="""        selected=sorted(loads[net],key=lambda sink: '/'.join(sink))
        if 'loads' in op:
            requested=[tuple(name.rsplit('/',1)) for name in op['loads']]
            if len(set(requested))!=len(requested) or not set(requested)<=set(selected):
                raise ValueError('Declared buffer sinks are duplicated or not attached to source')
            selected=sorted(requested,key=lambda sink: '/'.join(sink))
        count=len(selected)
        if net in roots or count < 1 or op['max_loads'] < 1:"""
    text=replace_once(text,old,new)
    text=replace_once(text,"sinks=sorted(loads[net],key=lambda sink: '/'.join(sink))",'sinks=selected')
    path.write_text(text)
    # Independent STA loads the exact configured macro libraries and hashes
    # them in its provenance manifest; missing corner mappings fail closed.
    path=tool/'replay.py'; text=path.read_text()
    text=replace_once(text,'import hashlib','import hashlib\nimport fnmatch')
    text=replace_once(text,'    args = parser.parse_args()', '''    parser.add_argument('--macro-config',type=Path)
    args = parser.parse_args()''')
    text=replace_once(text,'        script = Path(__file__).with_name', '''        macro_libraries={corner:[] for corner in REQUIRED_CORNERS}
        if args.macro_config:
            configured=json.loads(args.macro_config.read_text()).get('MACROS',{})
            for name,macro in configured.items():
                for corner in REQUIRED_CORNERS:
                    matching=[paths for pattern,paths in macro.get('lib',{}).items() if fnmatch.fnmatchcase(corner,pattern)]
                    if len(matching)!=1 or not matching[0]:
                        raise ValueError('Missing or ambiguous macro model: '+name+' '+corner)
                    macro_libraries[corner].extend(map(Path,matching[0]))
            files.extend(path for paths in macro_libraries.values() for path in paths)
            files.append(args.macro_config)
        script = Path(__file__).with_name''')
    text=replace_once(text,'"reset_active": args.reset_active}', '"reset_active": args.reset_active, "macro_libraries_by_corner":{c:list(map(str,v)) for c,v in macro_libraries.items()}}')
    text=replace_once(text,'                log = args.out /', '''                env['PIO_TIMING_MACRO_LIBS']=' '.join('{'+str(p)+'}' for p in macro_libraries[corner])
                log = args.out /''')
    path.write_text(text)
    path=tool/'report_io_paths.tcl'; text=path.read_text()
    text=replace_once(text,'read_verilog $netlist', '''if {[info exists ::env(PIO_TIMING_MACRO_LIBS)]} {
    foreach macro_lib $::env(PIO_TIMING_MACRO_LIBS) {
        if {![file isfile $macro_lib]} {error "Missing configured macro timing library"}
        read_liberty $macro_lib
    }
}
read_verilog $netlist''')
    path.write_text(text)
    # Audit every source clock pin instead of retaining a stale hardcoded sink
    # count. Equality of the full pin sets is stronger than a numeric count.
    path=tool/'audit_clock_tree.py'; text=path.read_text()
    if "name == 'A_CLK'" not in text:
        text=replace_once(text,"if name == 'CLK':", "if name == 'CLK' or (name == 'A_CLK' and inst.getMaster().getName() == 'RM_IHPSG13_1P_64x16_c2'):")
    text=replace_once(text,"    a = p.parse_args()", "    p.add_argument('--expected-odb',type=Path)\n    a = p.parse_args()")
    text=replace_once(text,"    result['runner_sha256']", '''    if a.expected_odb:
        expected_db=odb.dbDatabase.create(); odb.read_db(expected_db,str(a.expected_odb))
        source=snapshot(expected_db.getChip().getBlock())
        if source[4]!=after[4]:
            raise ValueError('Source sequential/macro clock pin set changed')
        result['source_clock_sinks_identical']=True
        result['expected_clock_sink_count']=len(source[4])
        result['input_sha256'][str(a.expected_odb)]=hashlib.sha256(a.expected_odb.read_bytes()).hexdigest()
    result['runner_sha256']''')
    path.write_text(text)
    path=tool/'qualify_final_route.py'; text=path.read_text()
    text=replace_once(text,"str(view), '--pdk-root',", "str(view), '--macro-config', str(a.run.resolve()/'resolved.json'), '--pdk-root',")
    text=replace_once(text,"'--odb', state['odb'], '--out', str(out/'clock_audit.json')", "'--odb', state['odb'], '--expected-odb', str(next(a.run.resolve().glob('*-openroad-floorplan/*.odb'))), '--out', str(out/'clock_audit.json')")
    text=replace_once(text,"        topology = json.loads((out/'clock_audit.json').read_text())['topology']\n        if topology['clock_sink_count'] != 2421 or topology['clock_buffer_outputs_above8']:", "        clock_result=json.loads((out/'clock_audit.json').read_text())\n        topology=clock_result['topology']\n        if not clock_result['source_clock_sinks_identical'] or topology['clock_sink_count']!=clock_result['expected_clock_sink_count'] or topology['clock_buffer_outputs_above8']:")
    path.write_text(text)
