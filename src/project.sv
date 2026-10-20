/*
 * Copyright (c) 2026 Shane Bringhurst
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_shanebri_top (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  wire [3:0] host_address;
  wire host_write_en;
  wire host_read_en;
  wire [7:0] host_write_data;
  wire [7:0] host_read_data;

  wire [11:0] values;
  wire [3:0] directions, open_drain;

  host_interface host (
      .clk(clk), .rst_n(rst_n), .ena(ena), .control(ui_in),
      .data_in(uio_in[3:0]), .read_data(host_read_data),
      .address(host_address), .write_en(host_write_en),
      .read_en(host_read_en),
      .write_data(host_write_data), .data_out(uio_out[3:0]), .data_oe(uio_oe[3:0])
  );

  protocol_core core (
      .clk(clk), .rst_n(rst_n), .enable(ena),
      .host_address(host_address), .host_write_en(host_write_en),
      .host_read_en(host_read_en), .pin_in({uio_in[7:4], ui_in[7:6]}),
      .host_write_data(host_write_data), .host_read_data(host_read_data),
      .pins(values), .directions(directions), .open_drain(open_drain)
  );

  pio_pads pads (.rst_n(rst_n), .values(values), .directions(directions),
      .open_drain(open_drain), .dedicated(uo_out),
      .pad_data(uio_out[7:4]), .pad_oe(uio_oe[7:4]));
endmodule

`default_nettype wire
