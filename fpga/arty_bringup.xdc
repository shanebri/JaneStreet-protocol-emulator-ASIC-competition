# Arty A7-100 Rev D/E. Standalone constraints for arty_bringup_top only.
# Mapping source: https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS33} [get_ports clk100]
create_clock -name clk100 -period 10.000 [get_ports clk100]
set_property -dict {PACKAGE_PIN D9 IOSTANDARD LVCMOS33} [get_ports btn_reset]
set_false_path -from [get_ports btn_reset] -to [get_pins {reset_button_sync_reg[0]/D}]
set_property -dict {PACKAGE_PIN A9 IOSTANDARD LVCMOS33} [get_ports uart_rx]
set_property -dict {PACKAGE_PIN D10 IOSTANDARD LVCMOS33} [get_ports uart_tx]
set_false_path -from [get_ports uart_rx] -to [get_pins {bridge/receiver/sync_reg[0]/D}]
set_property -dict {PACKAGE_PIN T10 IOSTANDARD LVCMOS33} [get_ports locked_led]
# JA1/2/3 output0/1/2 (SPI MOSI/SCLK/CS); JA4/7 input0/1 (MISO/READY).
set_property -dict {PACKAGE_PIN G13 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[0]}]
set_property -dict {PACKAGE_PIN B11 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[1]}]
set_property -dict {PACKAGE_PIN A11 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[2]}]
set_property -dict {PACKAGE_PIN D12 IOSTANDARD LVCMOS33} [get_ports {dedicated_in[0]}]
set_property -dict {PACKAGE_PIN D13 IOSTANDARD LVCMOS33} [get_ports {dedicated_in[1]}]
set_property PULLDOWN true [get_ports {dedicated_in[*]}]
# JB1/2/3/4/7: outputs3..7. JC1/2/3/4: bidirectional protocol pads0..3.
set_property -dict {PACKAGE_PIN E15 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[3]}]
set_property -dict {PACKAGE_PIN E16 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[4]}]
set_property -dict {PACKAGE_PIN D15 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[5]}]
set_property -dict {PACKAGE_PIN C15 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[6]}]
set_property -dict {PACKAGE_PIN J17 IOSTANDARD LVCMOS33} [get_ports {dedicated_out[7]}]
set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[0]}]
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[1]}]
set_property -dict {PACKAGE_PIN V10 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[2]}]
set_property -dict {PACKAGE_PIN V11 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[3]}]
# External protocol pins are asynchronous. Only synchronizer first stages exempt.
set_false_path -from [get_ports {dedicated_in[*] protocol_pad[*]}] -to [get_pins {bridge/emulator/pio/inputs_shared/pins_meta_reg[*]/D}]
# Slow observable outputs; this does not qualify board-level protocol timing.
set_false_path -to [get_ports {uart_tx locked_led dedicated_out[*] protocol_pad[*]}]
