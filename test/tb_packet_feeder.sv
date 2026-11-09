`default_nettype none
`timescale 1ns / 1ps

module tb_packet_feeder;
    reg clk, rst_n, ena;
    reg [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;
    wire reset = !rst_n;

    reg cmd_valid;
    reg [2:0] cmd;
    reg [31:0] cmd_data;
    reg [15:0] cmd_length_minus_one;
    reg cmd_engine=0;
    wire engine, bus_atomic;
    wire cmd_ready;
    wire [2:0] slot_state;
    wire [31:0] completion_sequence;
    wire [1:0] result;
    wire [5:0] words_sent, bus_request;
    wire [7:0] terminal_status, terminal_levels, terminal_errors;
    wire [7:0] bus_write_data, bus_read_data;
    wire bus_done;
    wire [5:0] control;
    wire [3:0] nibble_out;

    packet_feeder feeder (.*);
    byte_nibble_host adapter (
        .clk(clk), .reset(reset), .request(bus_request), .write_data(bus_write_data),
        .nibble_in(uio_out[3:0]), .control(control), .nibble_out(nibble_out),
        .read_data(bus_read_data), .done(bus_done)
    );

    // The testbench sets up the engine through its ordinary pins. Only the
    // feeder drives the host pins while its slot is active.
    wire active = rst_n && slot_state == 3;
    tt_um_shanebri_top user_project (
        .clk(clk), .rst_n(rst_n), .ena(ena), .uo_out(uo_out),
        .ui_in(active ? {ui_in[7:6], control} : ui_in),
        .uio_in(active ? {uio_in[7:4], nibble_out} : uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe)
    );
endmodule

`default_nettype wire
