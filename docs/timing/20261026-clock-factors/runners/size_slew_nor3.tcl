# One measured weak driver, with identical legalization in the control.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
set inst [$::block findInst _19177_]
if {$inst eq "NULL"} { error "Measured NOR3 missing" }
if {[[$inst getMaster] getName] ne "sg13cmos5l_nor3_1"} { error "Unexpected measured NOR3 master" }
if {$::env(PIO_SIZE_SLEW_NOR3)} { replace_cell _19177_ sg13cmos5l_nor3_2 }
puts "Measured slew driver _19177_: [[$inst getMaster] getName]"
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
