`default_nettype none
// Synchronous low-nibble-first adapter; core interface remains byte oriented.
module host_interface (
    input wire clk, rst_n, ena,
    input wire [7:0] control,
    input wire [3:0] data_in,
    input wire [7:0] read_data,
    output wire [3:0] address,
    output wire write_en, read_en,
    output wire [7:0] write_data,
    output reg [3:0] data_out,
    output wire [3:0] data_oe
);
    reg armed, pending, pending_read, valid_read;
    reg [3:0] pending_address, low;
    reg [7:0] captured;
    wire wr = control[4];
    wire rd = control[5];
    wire beat = ena && rst_n && armed && (wr ^ rd);
    wire matching = pending && pending_address == address && pending_read == rd;
    assign address = control[3:0];
    assign write_data = {data_in, low};
    assign write_en = beat && wr && matching;
    assign read_en = beat && rd && !matching;
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
endmodule
`default_nettype wire
