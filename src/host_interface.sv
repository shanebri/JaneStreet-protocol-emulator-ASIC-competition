`default_nettype none

// Synchronous byte bus: address ui[3:0], WR ui[4], RD ui[5], data uio[7:0].
// One transaction on a strobe's sampled rising edge. Return data is latched.
module host_interface (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       ena,
    input  wire [7:0] control,
    input  wire [7:0] data_in,
    input  wire [7:0] read_data,
    output wire [3:0] address,
    output wire       write_en,
    output wire       read_en,
    output wire [7:0] write_data,
    output reg  [7:0] data_out,
    output wire [7:0] data_oe
);
    reg wr_previous;
    reg rd_previous;
    wire wr = control[4];
    wire rd = control[5];

    assign address = control[3:0];
    assign write_data = data_in;
    assign write_en = ena && rst_n && wr && !wr_previous && !rd;
    assign read_en = ena && rst_n && rd && !rd_previous && !wr;
    assign data_oe = {8{ena && rst_n && rd && !wr}};

    always @(posedge clk) begin
        if (!rst_n) begin
            wr_previous <= 1'b0;
            rd_previous <= 1'b0;
            data_out <= 8'd0;
        end else begin
            wr_previous <= wr;
            rd_previous <= rd;
            if (read_en)
                data_out <= read_data;
        end
    end

    wire _unused = &{control[7:6], 1'b0};
endmodule

`default_nettype wire
