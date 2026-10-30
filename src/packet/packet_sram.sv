`default_nettype none
// Candidate only: deliberately absent from the production source manifest until
// the exact-corner availability and complete physical qualification gates pass.
// One outstanding 16-bit transaction; request and response are both registered.
module packet_sram (
    input wire clk, rst_n, enable,
    input wire req_valid,
    output wire req_ready,
    input wire req_write,
    input wire [5:0] req_addr,
    input wire [15:0] req_wdata,
    output wire rsp_valid,
    input wire rsp_ready,
    output reg [15:0] rsp_rdata
);
    localparam [1:0] IDLE=0, ISSUE=1, CAPTURE=2, RESPONSE=3;
    reg [1:0] state;
    reg write_q;
    reg [5:0] addr_q;
    reg [15:0] wdata_q;
    wire [15:0] macro_rdata;
    wire access = rst_n && enable && state == ISSUE;

    assign req_ready = rst_n && enable && state == IDLE;
    assign rsp_valid = rst_n && state == RESPONSE;

    RM_IHPSG13_1P_64x16_c2 memory (
        .A_CLK(clk), .A_MEN(access), .A_WEN(access && write_q),
        .A_REN(access && !write_q), .A_ADDR(addr_q), .A_DIN(wdata_q),
        .A_DLY(1'b1), .A_DOUT(macro_rdata)
    );

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            write_q <= 0;
            addr_q <= 0;
            wdata_q <= 0;
            rsp_rdata <= 0;
        end else begin
            case (state)
                IDLE: if (req_valid && enable) begin
                    write_q <= req_write;
                    addr_q <= req_addr;
                    wdata_q <= req_wdata;
                    state <= ISSUE;
                end
                ISSUE: if (enable) state <= CAPTURE;
                CAPTURE: begin
                    rsp_rdata <= write_q ? 16'd0 : macro_rdata;
                    state <= RESPONSE;
                end
                RESPONSE: if (rsp_ready) state <= IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
