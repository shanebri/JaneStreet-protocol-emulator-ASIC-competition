`default_nettype none
module bringup_uart_rx #(parameter integer BIT_CYCLES=434)(
    input wire clk, reset, rx,
    output reg valid, output reg [7:0] data
);
    (* ASYNC_REG="TRUE" *) reg [1:0] sync=3;
    reg [15:0] ticks;
    reg [3:0] bit_index;
    reg active;
    always @(posedge clk) begin
        sync <= {sync[0],rx};
        valid <= 0;
        if(reset) begin active<=0; ticks<=0; bit_index<=0; data<=0; end
        else if(!active) begin
            if(!sync[1]) begin active<=1; ticks<=BIT_CYCLES/2-1; bit_index<=0; end
        end else if(ticks!=0) ticks<=ticks-1'b1;
        else begin
            ticks<=BIT_CYCLES-1;
            if(bit_index==0) begin
                if(sync[1]) active<=0;
                else bit_index<=1;
            end else if(bit_index<=8) begin
                data[bit_index-1]<=sync[1]; bit_index<=bit_index+1'b1;
            end else begin valid<=sync[1]; active<=0; end
        end
    end
endmodule
`default_nettype wire
