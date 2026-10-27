source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
set inst [$::block findInst {_23190_}]
if {$inst eq "NULL"} { error "Measured driver missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_a21oi_1"} { error "Unexpected driver master" }
replace_cell {_23190_} sg13cmos5l_a21oi_2
if {[[$inst getMaster] getName] ne "sg13cmos5l_a21oi_2"} { error "Replacement failed" }
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
