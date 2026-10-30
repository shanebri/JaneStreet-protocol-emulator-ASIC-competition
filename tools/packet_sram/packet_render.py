"""Render declared, connectivity-audited candidate data repairs."""
def render_script(operations):
    text='source $::env(SCRIPTS_DIR)/openroad/common/io.tcl\nread_current_odb\nset_propagated_clock [all_clocks]\n'
    for index,op in enumerate(operations):
        target=op.get('instance',op.get('target'))
        if op['old'] is not None:
            name=target.split('/')[0]
            text+=f'set inst [$::block findInst {{{name}}}]\nif {{$inst eq "NULL" || [[$inst getMaster] getName] ne "{op["old"]}"}} {{ error "Candidate repair master mismatch" }}\n'
        if op['kind']=='size':
            text+=f'replace_cell {{{target}}} {op["new"]}\n'
            continue
        if '/' in target:
            text+=f'set net [get_nets -of_objects [get_pins {{{target}}}]]\nlassign [$inst getLocation] x y\n'
        else:
            text+=f'set term [$::block findBTerm {{{target}}}]\nset net [get_nets [list [[$term getNet] getName]]]\nset box [lindex [[lindex [$term getBPins] 0] getBoxes] 0]\nset x [expr {{([$box xMin]+[$box xMax])/2}}]\nset y [expr {{([$box yMin]+[$box yMax])/2}}]\n'
        text+='''if {[llength $net]!=1} {error "Missing candidate repair net"}
set all_loads {}
foreach pin [get_pins -of_objects $net -filter {direction == input}] {
    set name [get_property $pin full_name]
    if {[string match */CLK $name] || [string match */A_CLK $name]} {error "Candidate data repair touches clock"}
    lappend all_loads $name
}
set loads [lsort $all_loads]
'''
        if 'loads' in op:
            text+='set loads [list '+' '.join('{'+name+'}' for name in sorted(op['loads']))+']\n'
            text+='foreach sink $loads {if {[lsearch -exact $all_loads $sink]<0} {error "Declared sink not attached to candidate driver"}}\n'
        text+='if {[llength $loads]<1} {error "No candidate repair loads"}\n'
        text+='set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]\n'
        if 'location_um' in op: text+=f'set location [list {op["location_um"][0]} {op["location_um"][1]}]\n'
        text+=f'for {{set first 0}} {{$first<[llength $loads]}} {{incr first {op["max_loads"]}}} {{\nset chunk [lrange $loads $first [expr {{$first+{op["max_loads"]}-1}}]]\n'
        if op.get('location')=='sink_centroid':
            text+='''set sx 0; set sy 0
foreach sink $chunk {
    set cell [$::block findInst [lindex [split $sink /] 0]]
    lassign [$cell getLocation] px py
    incr sx $px; incr sy $py
}
set location [list [ord::dbu_to_microns [expr {$sx/[llength $chunk]}]] [ord::dbu_to_microns [expr {$sy/[llength $chunk]}]]]
'''
        text+=f'insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location -buffer_name eco_data_{index}_$first -net_name eco_net_{index}_$first\n}}\n'
    return text+'source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl\nwrite_views\n'
