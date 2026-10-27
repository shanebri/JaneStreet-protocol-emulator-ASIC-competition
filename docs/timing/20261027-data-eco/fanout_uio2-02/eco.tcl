source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
set term [$::block findBTerm {uio_in[2]}]
set db_net [$term getNet]
set net [get_nets [list [$db_net getName]]]
set box [lindex [[lindex [$term getBPins] 0] getBoxes] 0]
set x [expr {([$box xMin]+[$box xMax])/2}]
set y [expr {([$box yMin]+[$box yMax])/2}]
if {[llength $net] != 1} { error "Expected one target net" }
set loads {}
foreach pin [get_pins -of_objects $net -filter {direction == input}] {
    set name [get_property $pin full_name]
    if {[string match */CLK $name]} { error "Data ECO touches clock pin" }
    lappend loads $name
}
set loads [lsort $loads]
set count [llength $loads]
if {$count < 1} { error "No measured loads" }
puts "ECO uio_in[2]: $count loads, group maximum 8"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 8} {
    set chunk [lrange $loads $first [expr {$first+8-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_0_$first -net_name eco_net_0_$first
}
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
