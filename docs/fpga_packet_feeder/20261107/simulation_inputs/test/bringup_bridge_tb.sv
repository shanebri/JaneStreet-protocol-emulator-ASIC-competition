`timescale 1ns/1ps
`default_nettype none
// Test-fixture pullups and optional physical-wire loopbacks are outside the DUT.
module bringup_bridge_tb #(parameter integer BIT_CYCLES=8, TRACE_DEPTH=256,
                          FEEDER_ENABLED=0, FEEDER_TIMEOUT_CYCLES=20000)();
    reg clk=0, reset=1, uart_rx=1;
    wire uart_tx;
    reg [1:0] dedicated_in=0;
    wire [7:0] dedicated_out;
    tri1 [3:0] protocol_pad;
    reg [1:0] loopbacks=0;
    reg [1:0] i2c_target_low=0;
    assign protocol_pad[0]=i2c_target_low[0] ? 1'b0 : 1'bz;
    assign protocol_pad[1]=i2c_target_low[1] ? 1'b0 : 1'bz;
    assign protocol_pad[0]=(loopbacks==1 || loopbacks==3) ? dedicated_out[0] : 1'bz;
    assign protocol_pad[1]=loopbacks==1 ? dedicated_out[2] : (loopbacks==3 ? dedicated_out[1] : 1'bz);
    assign protocol_pad[2]=loopbacks==1 ? dedicated_out[3] : (loopbacks==2 ? dedicated_out[0] : (loopbacks==3 ? dedicated_out[2] : 1'bz));
    assign protocol_pad[3]=loopbacks==1 ? dedicated_out[1] : (loopbacks==2 ? dedicated_out[4] : (loopbacks==3 ? dedicated_out[3] : 1'bz));
    wire [1:0] observed_inputs=loopbacks==3 ? dedicated_out[5:4] : dedicated_in;
    wire peer_uart=dedicated_out[3], peer_sclk=dedicated_out[1];
    wire peer_cs=dedicated_out[2], peer_mosi=dedicated_out[0];
    bringup_bridge #(.BIT_CYCLES(BIT_CYCLES),.TRACE_DEPTH(TRACE_DEPTH),
                    .FEEDER_ENABLED(FEEDER_ENABLED),.FEEDER_TIMEOUT_CYCLES(FEEDER_TIMEOUT_CYCLES)) bridge(
        .clk(clk),.reset(reset),.uart_rx(uart_rx),.uart_tx(uart_tx),
        .dedicated_in(observed_inputs),.dedicated_out(dedicated_out),.protocol_pad(protocol_pad));
endmodule
`default_nettype wire
