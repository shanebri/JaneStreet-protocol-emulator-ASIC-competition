# Arty A7-100 Rev D/E JD header, digital side of a low-speed USB transceiver.
set_property -dict {PACKAGE_PIN D4 IOSTANDARD LVCMOS33} [get_ports {usb_rx[1]}]
set_property -dict {PACKAGE_PIN D3 IOSTANDARD LVCMOS33} [get_ports {usb_rx[0]}]
set_property -dict {PACKAGE_PIN D2 IOSTANDARD LVCMOS33} [get_ports {usb_rx[2]}]
set_property -dict {PACKAGE_PIN F4 IOSTANDARD LVCMOS33} [get_ports {usb_tx[1]}]
set_property -dict {PACKAGE_PIN F3 IOSTANDARD LVCMOS33} [get_ports {usb_tx[0]}]
set_property -dict {PACKAGE_PIN E2 IOSTANDARD LVCMOS33} [get_ports usb_tx_oe_n]
set_false_path -from [get_ports {usb_rx[*]}] -to [get_pins {usb_link/rx_meta_reg[*]/D}]
# The transceiver inputs have no forwarded clock. Bound the FPGA's
# clock-to-output contribution independently of external PHY delay.
set_max_delay 15.000 -to [get_ports {usb_tx[*] usb_tx_oe_n}]
set_min_delay 0.000 -to [get_ports {usb_tx[*] usb_tx_oe_n}]
