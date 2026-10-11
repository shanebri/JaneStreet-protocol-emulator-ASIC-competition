# Timing constraints for tt_um_shanebri_top.
# 50 MHz target, matching CLOCK_PERIOD = 20 ns in src/config.json.
create_clock -name clk -period 20.000 [get_ports clk]

# Board pin assignments and external interface delays depend on the FPGA board
# and connected host; specify those separately for hardware implementation.
