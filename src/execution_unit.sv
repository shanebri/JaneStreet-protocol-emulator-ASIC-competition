`default_nettype none

module execution_unit (
    input  wire [15:0] accumulator,
    input  wire [15:0] operand,
    input  wire [2:0]  alu_op,
    output reg  [15:0] result
);
    always @* begin
        case (alu_op)
            3'd0: result = operand;
            3'd1: result = accumulator + operand;
            3'd2: result = accumulator - operand;
            3'd3: result = accumulator & operand;
            3'd4: result = accumulator ^ operand;
            3'd5: result = {accumulator[14:0], 1'b0};
            default: result = accumulator;
        endcase
    end
endmodule

`default_nettype wire
