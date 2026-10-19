# Run in a separate Vivado batch process; does not open or change the demo project.
set root [file normalize [file join [file dirname [info script]] ..]]
set output [file join $root fpga build uart_diagnostic]
file mkdir $output
create_project -in_memory -part xc7a100tcsg324-1
read_verilog -sv [file join $root fpga arty_uart_diagnostic.sv]
read_xdc [file join $root fpga arty_uart_diagnostic.xdc]
synth_design -top arty_uart_diagnostic -part xc7a100tcsg324-1
opt_design
place_design
route_design
report_timing_summary -file [file join $output timing_summary.rpt]
report_io -file [file join $output io.rpt]
report_drc -file [file join $output drc.rpt]
write_bitstream -force [file join $output arty_uart_diagnostic.bit]
puts "UART diagnostic ready: [file join $output arty_uart_diagnostic.bit]"
