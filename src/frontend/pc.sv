`timescale 1ns / 1ps

module pc(
    input  logic clk,
    input  logic rst,
    output logic [4:0] pc_out
    );

    logic [4:0]  pc;
    logic [4:0]  pc_next;

    assign pc_next   = pc + 5'd1;

    always_ff @(posedge clk) begin
        if (rst)
            pc <= 5'd0;
        else
            pc <= pc_next;
    end

    assign pc_out = pc;

endmodule
