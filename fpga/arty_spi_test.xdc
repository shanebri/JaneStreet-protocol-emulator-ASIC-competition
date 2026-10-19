# Arty A7-100 Rev D/E. Use ONLY with arty_spi_test_top.
# Pin source: https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS33} [get_ports clk100]
create_clock -name clk100 -period 10.000 [get_ports clk100]
set_property -dict {PACKAGE_PIN D9 IOSTANDARD LVCMOS33} [get_ports btn_reset]
set_property -dict {PACKAGE_PIN C9 IOSTANDARD LVCMOS33} [get_ports btn_run]
set_false_path -from [get_ports btn_reset] -to [get_pins {reset_button_sync_reg[0]/D}]
set_false_path -from [get_ports btn_run] -to [get_pins {tester/run_sync_reg[0]/D}]
# PMOD JA1=MOSI, JA2=SCLK, JA3=CS_n, JA4=MISO, JA7=READY.
set_property -dict {PACKAGE_PIN G13 IOSTANDARD LVCMOS33} [get_ports spi_mosi]
set_property -dict {PACKAGE_PIN B11 IOSTANDARD LVCMOS33} [get_ports spi_sclk]
set_property -dict {PACKAGE_PIN A11 IOSTANDARD LVCMOS33} [get_ports spi_cs_n]
set_property -dict {PACKAGE_PIN D12 IOSTANDARD LVCMOS33} [get_ports spi_miso]
set_property -dict {PACKAGE_PIN D13 IOSTANDARD LVCMOS33} [get_ports nano_ready]
set_false_path -from [get_ports nano_ready] -to [get_pins {tester/ready_sync_reg[0]/D}]
set_false_path -from [get_ports spi_miso] -to [get_pins {tester/emulator/core/pins_meta_reg[0]/D}]
# Missing slave/disconnected READY must not start a transaction.
set_property PULLDOWN true [get_ports nano_ready]
set_property PULLDOWN true [get_ports spi_miso]
# Correct FPGA TX -> USB bridge RX pin, used for binary test reports.
set_property -dict {PACKAGE_PIN D10 IOSTANDARD LVCMOS33} [get_ports uart_tx]
set_property -dict {PACKAGE_PIN H5 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN J5 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN T9 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN T10 IOSTANDARD LVCMOS33} [get_ports {led[3]}]
# Slow externally observed waveforms. Board-level SPI timing still needs measurement.
set_false_path -to [get_ports {spi_mosi spi_sclk spi_cs_n uart_tx led[*]}]
