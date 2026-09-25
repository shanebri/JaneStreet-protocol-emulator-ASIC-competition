`timescale 1ns / 1ps

module instruction_fetch(
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] instr_out       // 16-bit instruction output
);

    logic [4:0] current_pc;

    pc u_pc(
        .clk(clk),
        .rst(rst),
        .pc_out(current_pc)
    );


endmodule