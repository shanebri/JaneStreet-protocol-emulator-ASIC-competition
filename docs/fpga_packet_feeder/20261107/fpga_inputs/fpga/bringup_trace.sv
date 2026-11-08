`default_nettype none
// FPGA-only digital observer. No connection drives the emulated ASIC.
// Capture begins at the selected edge and stops after DEPTH samples.
module bringup_trace #(parameter integer DEPTH=8192)(
    input wire clk, reset, arm, cancel,
    input wire [31:0] signals,
    input wire [4:0] trigger_channel,
    input wire trigger_falling, immediate,
    input wire [3:0] decimation,
    input wire [$clog2(DEPTH)-1:0] read_address,
    output reg [31:0] read_data,
    output reg armed=0, capturing=0, done=0, triggered=0,
    output reg [15:0] count=0
);
    (* ram_style = "block" *) reg [31:0] memory [0:DEPTH-1];
    reg [31:0] previous=0, activity=0;
    reg [15:0] divider=0;
    wire edge_seen = trigger_falling ?
        (previous[trigger_channel] && !signals[trigger_channel]) :
        (!previous[trigger_channel] && signals[trigger_channel]);
    // Host strobes are OR-reduced over each sample interval. Other channels
    // are instantaneous digital samples, including the physical pad inputs.
    localparam [31:0] ACTIVITY_MASK=32'h00300000;
    wire start_sample = armed && (immediate || edge_seen);
    wire sample_write = !reset && !cancel && !arm &&
                        (start_sample || (capturing && divider==0));
    wire [$clog2(DEPTH)-1:0] write_address = start_sample ? 0 : count[$clog2(DEPTH)-1:0];
    // One write port and one synchronous read port infer a simple dual-port
    // block RAM. Keep both write cases behind the same address/data mux.
    always @(posedge clk) begin
        if(sample_write) memory[write_address] <= signals | (start_sample ? 32'd0 : activity);
        read_data <= memory[read_address];
    end
    always @(posedge clk) begin
        previous <= signals;
        activity <= (activity | signals) & ACTIVITY_MASK;
        if(reset || cancel) begin
            armed<=0; capturing<=0; done<=0; triggered<=0; count<=0;
            divider<=0; activity<=0;
        end else if(arm) begin
            armed<=1; capturing<=0; done<=0; triggered<=0; count<=0;
            divider<=0; activity<=0;
        end else if(armed && (immediate || edge_seen)) begin
            armed<=0; capturing<=1; triggered<=1; count<=1;
            divider<=(16'd1<<decimation)-1'b1; activity<=0;
        end else if(capturing) begin
            if(divider==0) begin
                count<=count+1'b1;
                divider<=(16'd1<<decimation)-1'b1; activity<=0;
                if(count==DEPTH-1) begin capturing<=0; done<=1; end
            end else divider<=divider-1'b1;
        end
    end
endmodule
`default_nettype wire
