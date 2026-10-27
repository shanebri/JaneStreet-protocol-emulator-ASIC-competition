`default_nettype none
// Synchronous low-nibble-first adapter; core interface remains byte oriented.
module host_gold (
    input wire clk, rst_n, ena,
    input wire [7:0] control,
    input wire [3:0] data_in,
    input wire [7:0] read_data,
    output wire [3:0] address,
    output wire write_en, read_en,
    output wire [7:0] write_data,
    output reg [3:0] data_out,
    output wire [3:0] data_oe,
    // Intent is consumed only by synchronous-reset state, with a separate
    // local reset guard on unreset IMEM. Public acceptance remains qualified.
    output wire [23:0] formal_state, output wire formal_invariant, output wire write_intent, read_intent, word_write_intent
);
    reg armed, pending, pending_read, valid_read;
    reg [3:0] pending_address, low;
    reg [7:0] captured;
    wire wr = control[4];
    wire rd = control[5];
    wire beat = ena && armed && (wr ^ rd);
    wire matching = pending && pending_address == address && pending_read == rd;
    assign address = control[3:0];
    assign write_data = {data_in, low};
    assign write_intent = beat && wr && matching;
    assign read_intent = beat && rd && !matching;
    assign write_en = rst_n && write_intent;
    assign read_en = rst_n && read_intent;
    assign data_oe = {4{ena && rst_n && rd && !wr && (armed || valid_read)}};
    always @(posedge clk) begin
        if (!rst_n || !ena) begin
            armed <= 0; pending <= 0; pending_read <= 0;
            pending_address <= 0; low <= 0; captured <= 0;
            data_out <= 0; valid_read <= 0;
        end else if (rd && wr) begin
            armed <= 0; pending <= 0; valid_read <= 0;
        end else begin
            if (!rd && !wr) begin armed <= 1; valid_read <= 0; end
            if (pending && (address != pending_address ||
                ((rd || wr) && rd != pending_read))) pending <= 0;
            if (beat) begin
                armed <= 0;
                pending <= !matching;
                pending_address <= address;
                pending_read <= rd;
                if (rd) begin
                    valid_read <= 1;
                    if (matching) data_out <= captured[7:4];
                    else begin captured <= read_data; data_out <= read_data[3:0]; end
                end else if (!matching) low <= data_in;
            end
        end
    end
assign word_write_intent = write_intent && address == 4'ha;
assign formal_invariant = 1'b1;
assign formal_state = {armed,pending,pending_read,valid_read,pending_address,low,captured,data_out};
endmodule
`default_nettype wire
