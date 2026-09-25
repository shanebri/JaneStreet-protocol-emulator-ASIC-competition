`timescale 1ns / 1ps

module decoder(
    input  logic [4:0] opcode,
    output logic       alu_en,
    output logic [1:0] alu_op,        // 00=ADD, 01=SUB, 10=AND
    output logic       mem_read,
    output logic       mem_write,
    output logic       reg_write
);

    always_comb begin
        alu_en    = 1'b0;
        alu_op    = 2'b00;
        mem_read  = 1'b0;
        mem_write = 1'b0;
        reg_write = 1'b0;
        unique case (opcode)

        endcase
    end
endmodule