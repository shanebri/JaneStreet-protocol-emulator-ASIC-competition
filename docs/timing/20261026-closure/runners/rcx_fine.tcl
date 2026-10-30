# Isolated RCX segmentation trial. Same DEF/LEFs, rules and via handling;
# prevent wire-resistance segment merging instead of excluding live sinks.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_lefs "RCX_LEF"
read_def $::env(CURRENT_DEF)
set_global_vars
set_propagated_clock [all_clocks]
set rcx_flags ""
if {!$::env(RCX_MERGE_VIA_WIRE_RES)} { set rcx_flags "-no_merge_via_res" }
puts "Fine RCX segmentation with unchanged rules '$::env(RCX_RULESET)'"
define_process_corner -ext_model_index 0 CURRENT_CORNER
log_cmd extract_parasitics $rcx_flags -max_res 0 -ext_model_file $::env(RCX_RULESET) -lef_res
write_views
