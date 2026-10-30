`default_nettype none
// Experimental host-only portal. Not part of the production source manifest.
module packet_sram_portal (
    input wire clk, rst_n, enable,
    input wire commit,
    input wire [7:0] selector,
    input wire [31:0] data,
    input wire [7:0] read_selector0, read_selector1,
    output wire [31:0] read0, read1
);
    reg [5:0] address, command_address;
    reg [15:0] wdata, command_data, result;
    reg pending, busy, done, rejected, writing;
    wire ready, valid;
    wire [15:0] rdata;
    packet_sram storage (.clk(clk), .rst_n(rst_n), .enable(enable),
        .req_valid(pending), .req_ready(ready), .req_write(writing),
        .req_addr(command_address), .req_wdata(command_data),
        .rsp_valid(valid), .rsp_ready(busy), .rsp_rdata(rdata));
    function [31:0] read_port(input [7:0] s,input [5:0] a,input [15:0] w,r,input b,d,e);
        case(s)
            8'h20: read_port={29'd0,e,d,b};
            8'h21: read_port={26'd0,a};
            8'h22: read_port={16'd0,w};
            8'h24: read_port={16'd0,r};
            default: read_port=0;
        endcase
    endfunction
    assign read0=read_port(read_selector0,address,wdata,result,busy,done,rejected);
    assign read1=read_port(read_selector1,address,wdata,result,busy,done,rejected);
    always @(posedge clk) begin
        if (!rst_n) begin
            address<=0; command_address<=0; wdata<=0; command_data<=0;
            result<=0; pending<=0; busy<=0; done<=0; rejected<=0; writing<=0;
        end else begin
            if (pending && ready) pending<=0;
            if (busy && valid) begin result<=rdata; busy<=0; done<=1; end
            if (commit) case(selector)
                8'h21: if (data[31:6]!=0) rejected<=1; else address<=data[5:0];
                8'h22: if (data[31:16]!=0) rejected<=1; else wdata<=data[15:0];
                8'h23: begin
                    if (data==4 && !busy) begin done<=0; rejected<=0; end
                    else if ((data==1 || data==2) && !busy && !done) begin
                        command_address<=address; command_data<=wdata;
                        writing<=data==2; pending<=1; busy<=1;
                    end else rejected<=1;
                end
                default: ;
            endcase
        end
    end
endmodule
`default_nettype wire
