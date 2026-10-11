`default_nettype none

// Small inferred memory, with asynchronous instruction and host read ports.
// No reset: the host must load a complete reachable program before START.
module instruction_fetch (
    input  wire        clk,
    input  wire [4:0]  pc_addr,
    input  wire        load_we,
    input  wire [4:0]  load_addr,
    input  wire [15:0] load_data,
    output wire [15:0] instr_out,
    output wire [15:0] host_read_data
);
    reg [15:0] words [0:31];

    always @(posedge clk) begin
        if (load_we)
            words[load_addr] <= load_data;
    end

    assign instr_out = words[pc_addr];
    assign host_read_data = words[load_addr];
endmodule

`default_nettype wire
