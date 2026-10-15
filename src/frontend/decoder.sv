`default_nettype none

// PIO-style 16-bit encoding: opcode, delay/optional side-set, operands.
module decoder (
    input wire [15:0] instruction,
    input wire sideset_enable,
    output wire [2:0] opcode,
    output wire [7:0] argument,
    output wire [4:0] delay_cycles,
    output wire side_write, side_value,
    output wire [5:0] bit_count,
    output reg illegal
);
    assign opcode = instruction[15:13];
    assign argument = instruction[7:0];
    assign delay_cycles = sideset_enable ? {2'b0, instruction[10:8]} : instruction[12:8];
    assign side_write = sideset_enable && instruction[12];
    assign side_value = instruction[11];
    assign bit_count = instruction[4:0] == 0 ? 6'd32 : {1'b0, instruction[4:0]};

    always @* begin
        illegal = 0;
        case (opcode)
            3'd0: ;
            3'd1: begin
                case (argument[6:5])
                    0, 1: illegal = argument[4:0] > 1;
                    2: illegal = argument[4:3] != 0;
                    default: illegal = 1;
                endcase
            end
            3'd2: illegal = argument[7:5] == 4 || argument[7:5] == 5;
            3'd3: illegal = argument[7:5] == 4; // No bidirectional protocol pads yet.
            3'd4: illegal = argument[4:0] != 0;
            3'd5: illegal = argument[4:3] == 3 || argument[2:0] == 4 ||
                           argument[7:5] == 3;
            3'd6: begin // IRQ, plus local HALT extension at argument 0x80.
                if (argument[7]) illegal = argument != 8'h80;
                else illegal = argument[4:3] != 0 || argument[6:5] == 3;
            end
            3'd7: illegal = argument[7:5] > 2;
            default: illegal = 1;
        endcase
    end
endmodule

`default_nettype wire
