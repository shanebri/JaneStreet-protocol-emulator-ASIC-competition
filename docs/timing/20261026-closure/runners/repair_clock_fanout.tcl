# Controlled SG13CMOS5L experiment: split overloaded CTS buffer branches.
# Run immediately after CTS, before the normal post-CTS hold/setup repair.
# This changes clock distribution only; all final electrical checks remain on.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]

set fixed 0
set added 0
# Take a snapshot before insertion, and use stable ordering for reproducibility.
set drivers {}
foreach cell [get_cells -quiet clkbuf*] {
    lappend drivers [get_property $cell full_name]
}
foreach name [lsort $drivers] {
    set out [get_pins -of_objects [get_cells $name] -filter {direction == output}]
    if {[llength $out] != 1} { error "Expected one CTS buffer output: $name" }
    set net [get_nets -of_objects $out]
    set sinks {}
    foreach pin [get_pins -of_objects $net -filter {direction == input}] {
        lappend sinks [get_property $pin full_name]
    }
    set sinks [lsort $sinks]
    set count [llength $sinks]
    if {$count <= 8} { continue }
    if {$count > 64} { error "Unexpected CTS branch fanout $count at $name" }
    set inst [$::block findInst $name]
    lassign [$inst getLocation] x y
    set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
    puts "Splitting CTS branch $name with $count sinks"
    for {set first 0} {$first < $count} {incr first 8} {
        set chunk [lrange $sinks $first [expr {$first+7}]]
        insert_buffer -buffer_cell sg13cmos5l_buf_8 -load_pins $chunk \
            -location $location -buffer_name clkbuf_fanoutfix_$added \
            -net_name clknet_fanoutfix_$added
        incr added
    }
    incr fixed
}
foreach cell [get_cells -quiet clkbuf*] {
    set out [get_pins -of_objects $cell -filter {direction == output}]
    set net [get_nets -of_objects $out]
    set count [llength [get_pins -of_objects $net -filter {direction == input}]]
    if {$count > 8} { error "CTS output remains overloaded: [get_property $cell full_name] ($count)" }
}
puts "Clock fanout repair: split $fixed branches, inserted $added buffers"
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
