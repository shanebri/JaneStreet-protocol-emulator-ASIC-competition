`default_nettype none
// Candidate v2: commands arrive from per-bank capture registers. The SRAM
// accepts a ready command directly, retaining the original memory issue cycle.
module packet_sram_portal (
    input wire clk, rst_n, enable,
    input wire commit,
    input wire [1:0] operation,
    input wire [16:0] payload,
    output reg [2:0] packet_status,
    output wire [5:0] packet_address,
    output wire [15:0] packet_wdata, packet_result
);
    reg [5:0] address, command_address;
    reg [15:0] wdata, command_data, result;
    reg pending, busy, done, rejected, writing;
    wire ready, valid;
    wire [15:0] rdata;
    wire read_command = payload == 17'd1;
    wire write_command = payload == 17'd2;
    wire launch = commit && operation == 3 && (read_command || write_command) && !busy && !done;
    packet_sram storage (.clk(clk), .rst_n(rst_n), .enable(enable),
        .req_valid(pending || launch), .req_ready(ready),
        .req_write(pending ? writing : write_command),
        .req_addr(pending ? command_address : address),
        .req_wdata(pending ? command_data : wdata),
        .rsp_valid(valid), .rsp_ready(busy), .rsp_rdata(rdata));
    // Forward only captured events so byte-side readback keeps its original
    // cycle, including a command coincident with memory completion.
    always @* begin
        packet_status={rejected,done,busy || launch};
        if (commit) case(operation)
            1: if (payload[16:6]!=0) packet_status[2]=1;
            2: if (payload[16]) packet_status[2]=1;
            3: if (payload==4 && !busy) begin packet_status[2:1]=0; end
               else if (!launch) packet_status[2]=1;
            default: ;
        endcase
    end
    assign packet_address=(commit && operation==1 && payload[16:6]==0) ? payload[5:0] : address;
    assign packet_wdata=(commit && operation==2 && !payload[16]) ? payload[15:0] : wdata;
    assign packet_result=result;
    always @(posedge clk) begin
        if (!rst_n) begin
            address<=0; command_address<=0; wdata<=0; command_data<=0;
            result<=0; pending<=0; busy<=0; done<=0; rejected<=0; writing<=0;
        end else begin
            if (pending && ready) pending<=0;
            if (busy && valid) begin result<=rdata; busy<=0; done<=1; end
            if (commit) case(operation)
                1: if (payload[16:6]!=0) rejected<=1; else address<=payload[5:0];
                2: if (payload[16]) rejected<=1; else wdata<=payload[15:0];
                3: begin
                    if (payload==4 && !busy) begin done<=0; rejected<=0; end
                    else if (launch) begin
                        busy<=1;
                        if (!ready) begin
                            command_address<=address; command_data<=wdata;
                            writing<=write_command; pending<=1;
                        end
                    end else rejected<=1;
                end
                default: ;
            endcase
        end
    end
endmodule
`default_nettype wire
