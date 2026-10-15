`default_nettype none

// Four words, old-head asynchronous read, no empty fall-through. Full supports
// simultaneous pop+push. Storage is deliberately unreset; level guards reads.
module pio_fifo (
    input wire clk, rst, clear,
    input wire push, pop,
    input wire [31:0] write_data,
    output wire [31:0] read_data,
    output wire full, empty,
    output reg [2:0] level
);
    reg [31:0] words [0:3];
    reg [1:0] read_ptr, write_ptr;
    wire take_pop = pop && !empty;
    wire take_push = push && (!full || take_pop);
    assign full = level == 4;
    assign empty = level == 0;
    assign read_data = empty ? 32'd0 : words[read_ptr];
    always @(posedge clk) begin
        if (rst || clear) begin
            read_ptr <= 0;
            write_ptr <= 0;
            level <= 0;
        end else begin
            if (take_push) begin
                words[write_ptr] <= write_data;
                write_ptr <= write_ptr + 1'b1;
            end
            if (take_pop) read_ptr <= read_ptr + 1'b1;
            case ({take_push, take_pop})
                2'b10: level <= level + 1'b1;
                2'b01: level <= level - 1'b1;
                default: ;
            endcase
        end
    end
endmodule

`default_nettype wire
