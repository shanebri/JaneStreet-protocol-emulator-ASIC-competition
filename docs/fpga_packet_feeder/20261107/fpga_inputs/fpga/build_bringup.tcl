# Invoked by tools/bringup/build.py, in a fresh build directory.
# No hardware connection or programming is performed.
if {$argc < 2 || $argc > 3} { error "Expected source manifest, job count and optional feeder enable" }
set manifest [lindex $argv 0]
set jobs [lindex $argv 1]
set feeder [expr {$argc == 3 && [lindex $argv 2] == 1}]
set root [file normalize [file join [file dirname [info script]] ..]]
set out [pwd]
create_project bringup [file join $out project] -part xc7a100tcsg324-1
set f [open $manifest r]
foreach source [split [read $f] "\n"] {
    if {$source ne ""} { add_files $source }
}
close $f
add_files -fileset constrs_1 [file join $root fpga arty_bringup.xdc]
set_property top arty_bringup_top [get_filesets sources_1]
if {$feeder} { set_property generic {FEEDER_ENABLED=1} [get_filesets sources_1] }
update_compile_order -fileset sources_1
# Spend available FPGA area on timing-oriented synthesis and placement. This
# changes mapping/locality, without changing RTL, clocks or cycle contracts.
set_property strategy Flow_PerfOptimized_high [get_runs synth_1]
set_property strategy Performance_Explore [get_runs impl_1]
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "Synthesis failed" }
launch_runs impl_1 -to_step place_design -jobs $jobs
wait_on_run impl_1
set placed [file join [get_property DIRECTORY [get_runs impl_1]] arty_bringup_top_placed.dcp]
if {![file isfile $placed]} { error "Placement produced no checkpoint" }
# A run intentionally stopped after placement reports the next step as
# 'Not started phys_opt_design'; use its concrete completed checkpoint.
close_project
open_checkpoint $placed
phys_opt_design -directive Explore
# Measured early-decode and bit-count fanout dominates the PC-to-RX-FIFO cone.
# Replicate these LUT drivers before final routing; preserve all register cycles.
set locality_net [get_nets -hierarchical -regexp {^bridge/emulator/pio/engines\[[01]\]\.core/fetch/(exec_instruction_reg\[14\]\[[01]\]|bit_count\[0\])$}]
if {[llength $locality_net] != 6} { error "Missing measured decode/count locality targets" }
set pc_pins [get_pins -hierarchical -regexp {^bridge/emulator/pio/engines\[[01]\]\.core/program_counter/pc_out_reg\[[0-4]\]/Q$}]
if {[llength $pc_pins] != 10} { error "Missing measured PC locality targets" }
phys_opt_design -force_replication_on_nets [concat $locality_net [get_nets -of_objects $pc_pins]]
route_design -directive Explore
# Independently repair measured hold paths below the preserved 40 ps margin.
# Use complete native clock-pin-to-data-pin paths (no path segmentation).
# Temporary tighter requirements are always cleared before original-XDC checks.
set hold_floor [expr {$feeder ? 0.047 : 0.040}]
for {set pass 0} {$pass < 3} {incr pass} {
    set weak [get_timing_paths -delay_type min -slack_lesser_than $hold_floor -max_paths 200 -nworst 1]
    if {[llength $weak] == 0} { break }
    set log [open [file join $out hold_targets_$pass.txt] w]
    foreach path $weak {
        set first [get_property STARTPOINT_PIN $path]
        set last [get_property ENDPOINT_PIN $path]
        set start_clock [get_pins -of_objects [get_cells -of_objects $first] -filter {REF_PIN_NAME == C}]
        if {[llength $start_clock] != 1 || [llength $last] != 1} { error "Invalid hold repair boundary" }
        puts $log "$start_clock -> $last: [get_property SLACK $path] ns"
        set_min_delay 0.100 -from $start_clock -to $last
    }
    close $log
    route_design -directive Explore
    report_timing -delay_type min -max_paths 20 -file [file join $out hold_repair_tightened_$pass.rpt]
    reset_timing
    read_xdc [file join $root fpga arty_bringup.xdc]
}
write_checkpoint [file join $out qualified_routed.dcp]
report_timing_summary -report_unconstrained -file [file join $out timing_summary.rpt]
report_timing -delay_type max -max_paths 20 -nworst 1 -file [file join $out setup_paths.rpt]
report_timing -delay_type min -max_paths 20 -nworst 1 -file [file join $out hold_paths.rpt]
report_clocks -file [file join $out clocks.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_exceptions -file [file join $out exceptions.rpt]
report_drc -file [file join $out drc.rpt]
report_cdc -file [file join $out cdc.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_utilization -file [file join $out utilization.rpt]
# An exception that silently matches nothing must not qualify the build.
foreach pin {
    reset_button_sync_reg[0]/D
    bridge/receiver/sync_reg[0]/D
} {
    if {[llength [get_pins -quiet $pin]] != 1} { error "Missing exception endpoint: $pin" }
}
if {[llength [get_pins -quiet {bridge/emulator/pio/inputs_shared/pins_meta_reg[*]/D}]] != 6} {
    error "Expected all six protocol input synchronizer exception endpoints"
}
if {[llength [get_pins -quiet {bridge/trace_inputs_meta_reg[*]/D}]] != 6} {
    error "Expected all six FPGA observer synchronizer exception endpoints"
}
set f [open [file join $out margins.txt] w]
set parent_margin [dict create max 4.618 min 0.040]
if {$feeder} { set parent_margin [dict create max 4.871 min 0.047] }
foreach kind {max min} {
    set paths [get_timing_paths -delay_type $kind -max_paths 1 -sort_by slack]
    if {[llength $paths] != 1} { error "No finite $kind timing path" }
    set slack [get_property SLACK [lindex $paths 0]]
    puts $f "$kind $slack"
    dict set measured_margin $kind $slack
}
close $f
foreach kind {max min} {
    set slack [dict get $measured_margin $kind]
    if {![string is double -strict $slack] || $slack < 0 || $slack > 1e10} {
        error "Invalid/failing $kind timing slack: $slack"
    }
    if {$slack < [dict get $parent_margin $kind]} {
        error "Timing headroom regression: $kind $slack < preserved parent [dict get $parent_margin $kind] ns"
    }
}
set fatal [get_drc_violations -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning" || SEVERITY == "Warning"}]
if {[llength $fatal]} { error "DRC has warnings/errors; inspect drc.rpt" }
write_bitstream [file join $out arty_bringup_top.bit]
puts "BUILD_READY: [file join $out arty_bringup_top.bit]"
