`timescale 1ns/1ps
`default_nettype none
module tb_packet_feeder_bank;
    reg clk, rst_n, ena;
    reg [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;
    reg cmd_valid=0, cmd_slot=0, cmd_engine=0, cmd_both=0;
    reg [2:0] cmd=0;
    reg [31:0] cmd_data=0;
    reg [15:0] cmd_length_minus_one=0;
    wire cmd_ready, busy;
    reg query_slot=0;
    reg [1:0] query=0;
    wire [31:0] query_data;
    wire [5:0] bus_request, control;
    wire [7:0] bus_write_data, bus_read_data;
    wire [3:0] nibble_out;
    wire bus_done;
    packet_feeder_bank #(.MAX_ACTIVE_CYCLES(20000)) bank(
        .clk(clk),.reset(!rst_n),.cmd_valid(cmd_valid),.cmd_slot(cmd_slot),.cmd_engine(cmd_engine),
        .cmd_both(cmd_both),.cmd(cmd),.cmd_data(cmd_data),.cmd_length_minus_one(cmd_length_minus_one),
        .cmd_ready(cmd_ready),.query_slot(query_slot),.query(query),.query_data(query_data),
        .busy(busy),.bus_request(bus_request),.bus_write_data(bus_write_data),
        .bus_read_data(bus_read_data),.bus_done(bus_done));
    byte_nibble_host adapter(.clk(clk),.reset(!rst_n),.request(bus_request),.write_data(bus_write_data),
        .nibble_in(uio_out[3:0]),.control(control),.nibble_out(nibble_out),
        .read_data(bus_read_data),.done(bus_done));
    tt_um_shanebri_top user_project(
        .clk(clk),.rst_n(rst_n),.ena(ena),.uo_out(uo_out),
        .ui_in(busy ? {ui_in[7:6],control} : ui_in),
        .uio_in(busy ? {uio_in[7:4],nibble_out} : uio_in),
        .uio_out(uio_out),.uio_oe(uio_oe));
endmodule
`default_nettype wire
