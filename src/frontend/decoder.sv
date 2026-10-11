`default_nettype none

module decoder (
    input  wire [15:0] instruction,
    output wire [11:0] immediate,
    output reg  [2:0]  alu_op,
    output reg         reg_write,
    output reg         mem_read,
    output reg         mem_write,
    output reg  [1:0]  branch,
    output reg         wait_cycles,
    output reg         wait_uart,
    output reg         halt,
    output reg         illegal
);
    assign immediate = instruction[11:0];

    always @* begin
        alu_op = 3'd0;
        reg_write = 1'b0;
        mem_read = 1'b0;
        mem_write = 1'b0;
        branch = 2'd0;
        wait_cycles = 1'b0;
        wait_uart = 1'b0;
        halt = 1'b0;
        illegal = 1'b0;
        case (instruction[15:12])
            4'h0: ;                                                   // NOP
            4'h1: reg_write = 1'b1;                                   // LDI
            4'h2: begin reg_write = 1'b1; mem_read = 1'b1; end          // LD
            4'h3: mem_write = 1'b1;                                   // ST
            4'h4: begin reg_write = 1'b1; alu_op = 3'd1; end           // ADDI
            4'h5: begin reg_write = 1'b1; alu_op = 3'd2; end           // SUBI
            4'h6: begin reg_write = 1'b1; alu_op = 3'd3; end           // ANDI
            4'h7: begin reg_write = 1'b1; alu_op = 3'd4; end           // XORI
            4'h8: branch = 2'd1;                                      // JMP
            4'h9: branch = 2'd2;                                      // JZ
            4'ha: branch = 2'd3;                                      // JNZ
            4'hb: wait_cycles = 1'b1;                                 // WAIT
            4'hc: wait_uart = 1'b1;                                   // WAIT_TX
            4'hd: halt = 1'b1;                                       // HALT
            4'he: begin reg_write = 1'b1; alu_op = 3'd5; end           // SHL
            default: illegal = 1'b1;
        endcase
        if (branch != 0 && instruction[11:5] != 0)
            illegal = 1'b1;
    end
endmodule

`default_nettype wire
