# Constraint fragment for protocol_pad at the board top; 50 MHz clock and the
# byte requester must be integrated separately. Verified against Digilent's
# Arty-A7-100-Master.xdc for Rev D/E, JA physical pins 1,2,3,4.
# https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc
set_property -dict {PACKAGE_PIN G13 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[0]}]
set_property -dict {PACKAGE_PIN B11 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[1]}]
set_property -dict {PACKAGE_PIN A11 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[2]}]
set_property -dict {PACKAGE_PIN D12 IOSTANDARD LVCMOS33} [get_ports {protocol_pad[3]}]
