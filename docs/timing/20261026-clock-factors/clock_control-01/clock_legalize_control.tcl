# Matched control: same post-CTS legalization/export, no branch insertion.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
write_views
