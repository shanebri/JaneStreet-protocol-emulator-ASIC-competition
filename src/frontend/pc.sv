`default_nettype none

// Word-addressed 32-entry program counter. Stalls retain the current word.
module pc (
    input  wire       clk,
    input  wire       rst,
    input  wire       restart,
    input  wire       advance,
    input  wire       branch,
    input  wire [4:0] target,
    output reg  [4:0] pc_out
);
    always @(posedge clk) begin
        if (rst || restart)
            pc_out <= 5'd0;
        else if (advance)
            pc_out <= branch ? target : pc_out + 5'd1;
    end
endmodule

`default_nettype wire
