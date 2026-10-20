`default_nettype none
// Technology-independent electrical boundary. No internal tri-states.
module pio_pads (
    input wire rst_n,
    input wire [11:0] values,
    input wire [3:0] directions, open_drain,
    output wire [7:0] dedicated,
    output wire [3:0] pad_data, pad_oe
);
    assign dedicated = values[7:0];
    assign pad_data = values[11:8] & ~open_drain;
    assign pad_oe = {4{rst_n}} & directions & ~(open_drain & values[11:8]);
endmodule
`default_nettype wire
