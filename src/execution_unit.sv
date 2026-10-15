`default_nettype none

// Combinational 32-bit shift datapath. A decoded count is always 1..32.
module execution_unit (
    input wire [31:0] osr, isr, source,
    input wire [5:0] count,
    input wire out_right, in_right,
    output wire [31:0] out_value, shifted_osr, shifted_isr
);
    wire [31:0] mask = 32'hffffffff >> (6'd32 - count);
    assign out_value = out_right ? (osr & mask) : (osr >> (6'd32 - count));
    assign shifted_osr = out_right ? (osr >> count) : (osr << count);
    assign shifted_isr = in_right ?
        ((isr >> count) | ((source & mask) << (6'd32 - count))) :
        ((isr << count) | (source & mask));
endmodule

`default_nettype wire
