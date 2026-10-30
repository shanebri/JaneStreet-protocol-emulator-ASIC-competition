# Invoked by tools/bringup/build.py, in a fresh build directory.
# No hardware connection or programming is performed.
if {$argc != 2} { error "Expected source manifest and job count" }
set manifest [lindex $argv 0]
set jobs [lindex $argv 1]
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
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "Synthesis failed" }
launch_runs impl_1 -to_step route_design -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "Routing failed" }
open_run impl_1
report_timing_summary -report_unconstrained -file [file join $out timing_summary.rpt]
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
set f [open [file join $out margins.txt] w]
foreach kind {max min} {
    set paths [get_timing_paths -delay_type $kind -max_paths 1 -sort_by slack]
    if {[llength $paths] != 1} { error "No finite $kind timing path" }
    set slack [get_property SLACK [lindex $paths 0]]
    puts $f "$kind $slack"
    if {![string is double -strict $slack] || $slack < 0 || $slack > 1e10} {
        error "Invalid/failing $kind timing slack: $slack"
    }
}
close $f
set fatal [get_drc_violations -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning"}]
if {[llength $fatal]} { error "DRC has errors/critical warnings; inspect drc.rpt" }
write_bitstream [file join $out arty_bringup_top.bit]
puts "BUILD_READY: [file join $out arty_bringup_top.bit]"
