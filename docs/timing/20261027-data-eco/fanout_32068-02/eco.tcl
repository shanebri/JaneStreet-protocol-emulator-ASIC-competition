source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
set inst [$::block findInst {_32068_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_dfrbpq_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_32068_/Q}]]
lassign [$inst getLocation] x y
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
puts "ECO _32068_/Q: $count loads, group maximum 8"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 8} {
    set chunk [lrange $loads $first [expr {$first+8-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_0_$first -net_name eco_net_0_$first
}
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
