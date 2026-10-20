`default_nettype none
// FPGA-only byte request adapter. Hold request/address/data until done, then
// deassert request for a cycle. The core clock continues while the caller waits.
module byte_nibble_host (
    input wire clk, reset,
    input wire [5:0] request,
    input wire [7:0] write_data,
    input wire [3:0] nibble_in,
    output reg [5:0] control,
    output reg [3:0] nibble_out,
    output reg [7:0] read_data,
    output wire done
);
    reg [2:0] phase;
    reg [5:0] saved;
    reg [7:0] data;
    assign done = phase == 5;
    always @* begin
        control = {2'b00, saved[3:0]};
        nibble_out = phase < 3 ? data[3:0] : data[7:4];
        if (phase == 1 || phase == 3) control = saved;
    end
    always @(posedge clk) begin
        if (reset) begin phase <= 0; saved <= 0; data <= 0; read_data <= 0; end
        else case (phase)
            0: if (request[5] ^ request[4]) begin
                saved <= request; data <= write_data; phase <= 1;
            end
            1: phase <= 2;
            2: begin read_data[3:0] <= nibble_in; phase <= 3; end
            3: phase <= 4;
            4: begin read_data[7:4] <= nibble_in; phase <= 5; end
            5: if (!(|request[5:4])) phase <= 0;
            default: phase <= 0;
        endcase
    end
endmodule
`default_nettype wire
