source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
set inst [$::block findInst {_23190_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a21oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_23190_/Y}]]
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
puts "ECO _23190_/Y: $count loads, group maximum 1000"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1000} {
    set chunk [lrange $loads $first [expr {$first+1000-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_0_$first -net_name eco_net_0_$first
}
set inst [$::block findInst {_32071_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_dfrbpq_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_32071_/Q}]]
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
puts "ECO _32071_/Q: $count loads, group maximum 8"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 8} {
    set chunk [lrange $loads $first [expr {$first+8-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_1_$first -net_name eco_net_1_$first
}
set inst [$::block findInst {_17226_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_1"} { error "Unexpected driver master" }
replace_cell {_17226_} sg13cmos5l_nor3_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_2"} { error "Replacement failed" }
set inst [$::block findInst {_17236_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_and2_1"} { error "Unexpected driver master" }
replace_cell {_17236_} sg13cmos5l_and2_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_and2_2"} { error "Replacement failed" }
set inst [$::block findInst {_17238_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nand2_1"} { error "Unexpected driver master" }
replace_cell {_17238_} sg13cmos5l_nand2_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nand2_2"} { error "Replacement failed" }
set inst [$::block findInst {_17227_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_and2_1"} { error "Unexpected driver master" }
replace_cell {_17227_} sg13cmos5l_and2_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_and2_2"} { error "Replacement failed" }
set inst [$::block findInst {_17229_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nand2_1"} { error "Unexpected driver master" }
replace_cell {_17229_} sg13cmos5l_nand2_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nand2_2"} { error "Replacement failed" }
set inst [$::block findInst {_17250_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a221oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_17250_/Y}]]
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
puts "ECO _17250_/Y: $count loads, group maximum 1000"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1000} {
    set chunk [lrange $loads $first [expr {$first+1000-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_7_$first -net_name eco_net_7_$first
}
set inst [$::block findInst {_19177_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_1"} { error "Unexpected driver master" }
replace_cell {_19177_} sg13cmos5l_nor3_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_2"} { error "Replacement failed" }
set inst [$::block findInst {_23752_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_1"} { error "Unexpected driver master" }
replace_cell {_23752_} sg13cmos5l_nor3_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_2"} { error "Replacement failed" }
set inst [$::block findInst {_23931_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_1"} { error "Unexpected driver master" }
replace_cell {_23931_} sg13cmos5l_nor3_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_2"} { error "Replacement failed" }
set inst [$::block findInst {_28038_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor4_1"} { error "Unexpected driver master" }
replace_cell {_28038_} sg13cmos5l_nor4_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor4_2"} { error "Replacement failed" }
set inst [$::block findInst {_18133_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a221oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_18133_/Y}]]
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
puts "ECO _18133_/Y: $count loads, group maximum 1000"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1000} {
    set chunk [lrange $loads $first [expr {$first+1000-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_12_$first -net_name eco_net_12_$first
}
set inst [$::block findInst {_24358_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a221oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_24358_/Y}]]
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
puts "ECO _24358_/Y: $count loads, group maximum 1000"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1000} {
    set chunk [lrange $loads $first [expr {$first+1000-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_13_$first -net_name eco_net_13_$first
}
set inst [$::block findInst {_29030_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a22oi_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_29030_/Y}]]
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
puts "ECO _29030_/Y: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_14_$first -net_name eco_net_14_$first
}
set term [$::block findBTerm {uio_in[3]}]
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
puts "ECO uio_in[3]: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_15_$first -net_name eco_net_15_$first
}
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
puts "ECO uio_in[2]: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_16_$first -net_name eco_net_16_$first
}
set inst [$::block findInst {_17026_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_inv_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_17026_/Y}]]
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
puts "ECO _17026_/Y: $count loads, group maximum 2"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 2} {
    set chunk [lrange $loads $first [expr {$first+2-1}]]
    set sx 0; set sy 0
    foreach sink $chunk {
        set sink_inst [$::block findInst [lindex [split $sink /] 0]]
        if {$sink_inst eq "NULL"} {error "Missing physical sink"}
        lassign [$sink_inst getLocation] px py
        incr sx $px; incr sy $py
    }
    set location [list [ord::dbu_to_microns [expr {$sx/[llength $chunk]}]] [ord::dbu_to_microns [expr {$sy/[llength $chunk]}]]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_17_$first -net_name eco_net_17_$first
}
set inst [$::block findInst {_16949_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_inv_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_16949_/Y}]]
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
puts "ECO _16949_/Y: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_18_$first -net_name eco_net_18_$first
}
set inst [$::block findInst {_33838_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_dfrbpq_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_33838_/Q}]]
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
puts "ECO _33838_/Q: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_19_$first -net_name eco_net_19_$first
}
set inst [$::block findInst {_31543_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_dfrbpq_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_31543_/Q}]]
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
puts "ECO _31543_/Q: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_20_$first -net_name eco_net_20_$first
}
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
puts "ECO _32068_/Q: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_21_$first -net_name eco_net_21_$first
}
set inst [$::block findInst {place5417}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_buf_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {place5417/X}]]
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
puts "ECO place5417/X: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_22_$first -net_name eco_net_22_$first
}
set inst [$::block findInst {_23874_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor2_1"} { error "Unexpected driver master" }
replace_cell {_23874_} sg13cmos5l_nor2_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor2_2"} { error "Replacement failed" }
set inst [$::block findInst {_24620_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_1"} { error "Unexpected driver master" }
replace_cell {_24620_} sg13cmos5l_nor3_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_2"} { error "Replacement failed" }
set inst [$::block findInst {_24421_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_o21ai_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_24421_/Y}]]
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
puts "ECO _24421_/Y: $count loads, group maximum 1000"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 1000} {
    set chunk [lrange $loads $first [expr {$first+1000-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_25_$first -net_name eco_net_25_$first
}
set inst [$::block findInst {_26939_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nand2_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_26939_/Y}]]
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
puts "ECO _26939_/Y: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_26_$first -net_name eco_net_26_$first
}
set inst [$::block findInst {_31502_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_dfrbpq_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_31502_/Q}]]
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
puts "ECO _31502_/Q: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_27_$first -net_name eco_net_27_$first
}
set inst [$::block findInst {_32072_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_dfrbpq_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_32072_/Q}]]
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
puts "ECO _32072_/Q: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_28_$first -net_name eco_net_28_$first
}
set inst [$::block findInst {place6195}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_buf_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {place6195/X}]]
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
puts "ECO place6195/X: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_29_$first -net_name eco_net_29_$first
}
set inst [$::block findInst {_17916_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor2b_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_17916_/Y}]]
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
puts "ECO _17916_/Y: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_30_$first -net_name eco_net_30_$first
}
set inst [$::block findInst {_19177_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_2"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {_19177_/Y}]]
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
puts "ECO _19177_/Y: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_31_$first -net_name eco_net_31_$first
}
set inst [$::block findInst {place7144}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_buf_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {place7144/X}]]
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
puts "ECO place7144/X: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_32_$first -net_name eco_net_32_$first
}
set inst [$::block findInst {place5579}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_buf_1"} { error "Unexpected driver master" }
set net [get_nets -of_objects [get_pins {place5579/X}]]
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
puts "ECO place5579/X: $count loads, group maximum 4"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {set first 0} {$first < $count} {incr first 4} {
    set chunk [lrange $loads $first [expr {$first+4-1}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \
        -buffer_name eco_data_33_$first -net_name eco_net_33_$first
}
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
