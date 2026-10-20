`default_nettype none
// Integrate a synchronous byte requester (soft CPU or loader) at 50 MHz.
// Only these FPGA top-level pads contain tri-states; ASIC RTL has data/OE nets.
module arty_i2c_bridge (
    input wire clk, reset,
    input wire [5:0] request,
    input wire [7:0] write_data,
    output wire [7:0] read_data,
    output wire done,
    input wire [1:0] dedicated_in,
    output wire [7:0] dedicated_out,
    inout wire [3:0] protocol_pad
);
    wire [5:0] control;
    wire [3:0] nibble;
    wire [7:0] data, oe;
    byte_nibble_host host(.clk(clk), .reset(reset), .request(request),
        .write_data(write_data), .nibble_in(data[3:0]), .control(control),
        .nibble_out(nibble), .read_data(read_data), .done(done));
    tt_um_shanebri_top emulator(.clk(clk), .rst_n(!reset), .ena(1'b1),
        .ui_in({dedicated_in,control}), .uio_in({protocol_pad,nibble}),
        .uio_out(data), .uio_oe(oe), .uo_out(dedicated_out));
    genvar p;
    generate for(p=0;p<4;p=p+1) begin: physical_pads
        assign protocol_pad[p] = oe[p+4] ? data[p+4] : 1'bz;
    end endgenerate
endmodule
`default_nettype wire
