`default_nettype none

// TX-only 8N1. Each of the ten frame bits lasts exactly clocks_per_bit clocks.
module uart_tx (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire        cancel,
    input  wire        send,
    input  wire [7:0]  data,
    input  wire [15:0] clocks_per_bit,
    output wire        tx,
    output reg         busy
);
    reg [9:0] shift;
    reg [3:0] bits_left;
    reg [15:0] ticks_left;
    reg [15:0] reload_ticks;

    assign tx = shift[0];

    always @(posedge clk) begin
        if (rst || cancel) begin
            shift <= 10'h3ff;
            bits_left <= 4'd0;
            ticks_left <= 16'd0;
            reload_ticks <= 16'd0;
            busy <= 1'b0;
        end else if (enable) begin
            if (busy) begin
                if (ticks_left != 0) begin
                    ticks_left <= ticks_left - 16'd1;
                end else begin
                    shift <= {1'b1, shift[9:1]};
                    ticks_left <= reload_ticks;
                    bits_left <= bits_left - 4'd1;
                    if (bits_left == 1)
                        busy <= 1'b0;
                end
            end else if (send) begin
                shift <= {1'b1, data, 1'b0};
                bits_left <= 4'd10;
                reload_ticks <= (clocks_per_bit == 0) ? 16'd0 : clocks_per_bit - 16'd1;
                ticks_left <= (clocks_per_bit == 0) ? 16'd0 : clocks_per_bit - 16'd1;
                busy <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
