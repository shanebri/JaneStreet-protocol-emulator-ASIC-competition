`default_nettype none

module pc (
    input wire clk, rst, restart, advance, branch,
    input wire [4:0] entry, target, wrap_bottom, wrap_top,
    output reg [4:0] pc_out
);
    always @(posedge clk) begin
        if (rst) pc_out <= 0;
        else if (restart) pc_out <= entry;
        else if (advance)
            pc_out <= branch ? target : (pc_out == wrap_top ? wrap_bottom : pc_out + 5'd1);
    end
endmodule

`default_nettype wire
