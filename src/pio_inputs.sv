`default_nettype none
// Physical sampling is shared; each engine selects qualification independently.
module pio_inputs (
    input wire clk, rst_n,
    input wire [5:0] pin_in,
    output wire [5:0] synchronized,
    output reg [3:0] qualified
);
    (* ASYNC_REG = "TRUE" *) reg [5:0] pins_meta, pins_sync;
    reg [3:0] history [0:2];
    assign synchronized = pins_sync;
    integer f;
    always @(posedge clk) begin
        if (!rst_n) begin
            pins_meta <= 0; pins_sync <= 0;
            qualified <= 0;
            history[0] <= 0; history[1] <= 0; history[2] <= 0;
        end else begin
            pins_meta <= pin_in; pins_sync <= pins_meta;
            history[0] <= pins_sync[5:2];
            history[1] <= history[0]; history[2] <= history[1];
            for (f=0; f<4; f=f+1) begin
                if (&{pins_sync[f+2],history[0][f],history[1][f],history[2][f]}) qualified[f] <= 1;
                else if (~|{pins_sync[f+2],history[0][f],history[1][f],history[2][f]}) qualified[f] <= 0;
            end
        end
    end
endmodule
`default_nettype wire
