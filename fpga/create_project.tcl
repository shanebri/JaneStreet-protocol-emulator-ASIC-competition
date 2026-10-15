# In the Vivado Tcl console: source C:/path/to/repository/fpga/create_project.tcl
# Creates an isolated project. Close the current project first.
if {[llength [get_projects -quiet]] != 0} {
    error "Close the current project before sourcing this script."
}
set root [file normalize [file join [file dirname [info script]] ..]]
create_project janestreet_arty [file join $root fpga build janestreet_arty] -part xc7a100tcsg324-1
foreach source {project.sv host_interface.sv protocol_core.sv pio_fifo.sv execution_unit.sv frontend/pc.sv frontend/instruction_fetch.sv frontend/decoder.sv} {
    add_files [file join $root src $source]
}
add_files [file join $root fpga arty_a7_top.sv]
add_files [file join $root fpga arty_demo.sv]
add_files -fileset constrs_1 [file join $root fpga arty_a7_100t.xdc]
set_property top arty_a7_top [get_filesets sources_1]
update_compile_order -fileset sources_1
puts "Arty project ready. Run synthesis, implementation and Generate Bitstream."
