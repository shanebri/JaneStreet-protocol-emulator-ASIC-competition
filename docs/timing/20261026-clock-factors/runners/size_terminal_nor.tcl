# Isolated mechanism test for the measured _23246_ -> _33839_/D cone.
# The control uses this same legalization/export step without replacing a cell.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
set inst [$::block findInst _23246_]
if {$inst eq "NULL"} { error "Measured terminal NOR _23246_ is missing" }
set before [[$inst getMaster] getName]
if {$before ne "sg13cmos5l_nor4_1"} {
    error "Unexpected original master for _23246_: $before"
}
if {$::env(PIO_SIZE_TERMINAL_NOR)} {
    replace_cell _23246_ sg13cmos5l_nor4_2
    if {[[$inst getMaster] getName] ne "sg13cmos5l_nor4_2"} {
        error "Terminal NOR replacement did not update the physical database"
    }
}
puts "Terminal NOR trial: _23246_ $before -> [[$inst getMaster] getName]"
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
