# Run in Vivado batch mode; opens or creates this repository's isolated project.
set root [file normalize [file join [file dirname [info script]] ..]]
set project_file [file join $root fpga build janestreet_arty janestreet_arty.xpr]
if {[file exists $project_file]} {
    open_project $project_file
} else {
    source [file join $root fpga create_project.tcl]
}
# Migrate an existing accumulator-era project to the current source manifest.
set obsolete_uart [get_files -quiet */uart_tx.sv]
if {[llength $obsolete_uart]} { remove_files $obsolete_uart }
set fifo_source [file join $root src pio_fifo.sv]
if {![llength [get_files -quiet $fifo_source]]} { add_files $fifo_source }
foreach source {src/pio_subsystem.sv src/pio_gpio_owner.sv src/pio_inputs.sv src/pio_host_bank.sv src/pio_pads.sv fpga/byte_nibble_host.sv} {
    set source_path [file join $root $source]
    if {![llength [get_files -quiet $source_path]]} { add_files $source_path }
}
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "Synthesis failed" }
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "Implementation/bitstream failed" }
open_run impl_1
report_clocks -file [file join $root fpga build clocks.rpt]
report_timing_summary -report_unconstrained -file [file join $root fpga build timing_summary.rpt]
report_drc -file [file join $root fpga build drc.rpt]
report_cdc -file [file join $root fpga build cdc.rpt]
puts "Bitstream and reports ready under fpga/build."
