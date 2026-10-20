`default_nettype none
// One owner per output, stable while either engine executes. No execution grants.
module pio_gpio_owner (
    input wire clk, rst_n, write_en,
    input wire [11:0] write_owner,
    input wire [1:0] running,
    input wire [11:0] values0, values1,
    input wire [3:0] dirs0, dirs1, od0, od1,
    output reg [11:0] owner,
    output wire [11:0] values,
    output wire [3:0] directions, open_drain
);
    wire [3:0] changing_pads = owner[11:8] ^ write_owner[11:8];
    wire released = ~|(changing_pads & (dirs0 | dirs1));
    always @(posedge clk) begin
        if (!rst_n) owner <= 0;
        else if (write_en && !running[0] && !running[1] && released) owner <= write_owner;
    end
    assign values = (values0 & ~owner) | (values1 & owner);
    assign directions = (dirs0 & ~owner[11:8]) | (dirs1 & owner[11:8]);
    assign open_drain = (od0 & ~owner[11:8]) | (od1 & owner[11:8]);
endmodule
`default_nettype wire
