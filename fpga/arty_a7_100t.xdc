# Arty A7-100 Rev D/E, matching Digilent's Arty-A7-100-Master.xdc:
# https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS33} [get_ports clk100]
create_clock -name clk100 -period 10.000 [get_ports clk100]
# Vivado derives the 50 MHz generated clock through the MMCM automatically.

# BTN0: reset/reload; BTN1: run/replay (active high).
set_property -dict {PACKAGE_PIN D9 IOSTANDARD LVCMOS33} [get_ports btn_reset]
set_property -dict {PACKAGE_PIN C9 IOSTANDARD LVCMOS33} [get_ports btn_run]
# Asynchronous inputs: only the first synchronization stage is exempted.
set_false_path -from [get_ports btn_run] -to [get_pins {demo/run_sync_reg[0]/D}]
set_false_path -from [get_ports btn_reset] -to [get_pins {reset_button_sync_reg[0]/D}]

# FPGA TX -> bridge RX: D10 (uart_rxd_out in Digilent's master XDC).
# A9 (uart_txd_in) is bridge TX -> FPGA RX; never drive it as TX.
set_property -dict {PACKAGE_PIN D10 IOSTANDARD LVCMOS33} [get_ports uart_tx]
# UART is asynchronous to the external receiver, with no shared sampling clock.
set_false_path -to [get_ports uart_tx]

# LD4 ready, LD5 demo complete, LD6 heartbeat, LD7 MMCM locked.
set_property -dict {PACKAGE_PIN H5 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN J5 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN T9 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN T10 IOSTANDARD LVCMOS33} [get_ports {led[3]}]
# LEDs are indicators, with no external setup/hold requirements.
set_false_path -to [get_ports {led[*]}]
