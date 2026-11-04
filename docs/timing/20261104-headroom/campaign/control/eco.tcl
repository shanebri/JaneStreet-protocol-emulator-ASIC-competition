source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
source $::env(SCRIPTS_DIR)/openroad/common/set_routing_layers.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_layer_adjustments.tcl
set_macro_extension $::env(GRT_MACRO_EXTENSION)
global_route -start_incremental -allow_congestion
set inst [$::block findInst {place6629}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_buf_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {place6629/X}]]
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
puts "ECO place6629/X: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_0_$first -net_name eco_net_0_$first
}
set inst [$::block findInst {_30253_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a21oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_30253_/Y}]]
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
puts "ECO _30253_/Y: $count loads, group maximum 1"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1} {
    set chunk [lrange $loads $first [expr {$first+1-1}]]
    set sx 0; set sy 0
    foreach sink $chunk {
        set sink_inst [$::block findInst [lindex [split $sink /] 0]]
        if {$sink_inst eq "NULL"} {error "Missing physical sink"}
        lassign [$sink_inst getLocation] px py
        incr sx $px; incr sy $py
    }
    set location [list [ord::dbu_to_microns [expr {$sx/[llength $chunk]}]] [ord::dbu_to_microns [expr {$sy/[llength $chunk]}]]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_1_$first -net_name eco_net_1_$first
}
set inst [$::block findInst {_17710_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nand3_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_17710_/Y}]]
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
puts "ECO _17710_/Y: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    set sx 0; set sy 0
    foreach sink $chunk {
        set sink_inst [$::block findInst [lindex [split $sink /] 0]]
        if {$sink_inst eq "NULL"} {error "Missing physical sink"}
        lassign [$sink_inst getLocation] px py
        incr sx $px; incr sy $py
    }
    set location [list [ord::dbu_to_microns [expr {$sx/[llength $chunk]}]] [ord::dbu_to_microns [expr {$sy/[llength $chunk]}]]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_2_$first -net_name eco_net_2_$first
}
set inst [$::block findInst {_30219_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a21oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_30219_/Y}]]
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
puts "ECO _30219_/Y: $count loads, group maximum 1"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1} {
    set chunk [lrange $loads $first [expr {$first+1-1}]]
    set sx 0; set sy 0
    foreach sink $chunk {
        set sink_inst [$::block findInst [lindex [split $sink /] 0]]
        if {$sink_inst eq "NULL"} {error "Missing physical sink"}
        lassign [$sink_inst getLocation] px py
        incr sx $px; incr sy $py
    }
    set location [list [ord::dbu_to_microns [expr {$sx/[llength $chunk]}]] [ord::dbu_to_microns [expr {$sy/[llength $chunk]}]]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_3_$first -net_name eco_net_3_$first
}
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
global_route -end_incremental -allow_congestion -congestion_iterations $::env(GRT_OVERFLOW_ITERS) -verbose
write_views
