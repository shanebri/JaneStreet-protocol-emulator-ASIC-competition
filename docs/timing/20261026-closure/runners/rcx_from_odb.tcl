# Isolated extraction-import trial: use the unchanged routed OpenDB instead of
# reparsing DEF. Same tech data, extraction rules and electrical constraints.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_db $::env(CURRENT_ODB)
set_global_vars
set_propagated_clock [all_clocks]
set rcx_flags ""
if {!$::env(RCX_MERGE_VIA_WIRE_RES)} { set rcx_flags "-no_merge_via_res" }
puts "Using unchanged RCX ruleset '$::env(RCX_RULESET)' on routed OpenDB"
define_process_corner -ext_model_index 0 CURRENT_CORNER
log_cmd extract_parasitics $rcx_flags -ext_model_file $::env(RCX_RULESET) -lef_res
write_views
