source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
source $::env(SCRIPTS_DIR)/openroad/common/set_routing_layers.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_layer_adjustments.tcl
set_macro_extension $::env(GRT_MACRO_EXTENSION)
global_route -start_incremental -allow_congestion
source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
global_route -end_incremental -allow_congestion -congestion_iterations $::env(GRT_OVERFLOW_ITERS) -verbose
write_views
