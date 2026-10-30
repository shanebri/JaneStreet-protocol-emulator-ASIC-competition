`default_nettype none
// FPGA-only serial control plane. Core clock runs continuously at 50 MHz.
// No retries, one command at a time. Bridge reset also resets the ASIC.
module bringup_bridge #(parameter integer BIT_CYCLES=434)(
    input wire clk, reset, uart_rx,
    output wire uart_tx,
    input wire [1:0] dedicated_in,
    output wire [7:0] dedicated_out,
    inout wire [3:0] protocol_pad
);
    wire rx_valid; wire [7:0] rx_data;
    bringup_uart_rx #(.BIT_CYCLES(BIT_CYCLES)) receiver(
        .clk(clk),.reset(reset),.rx(uart_rx),.valid(rx_valid),.data(rx_data));
    reg tx_start=0; reg [7:0] tx_data=0; wire tx_busy;
    spi_test_uart_tx #(.BIT_CYCLES(BIT_CYCLES)) transmitter(
        .clk(clk),.reset(reset),.start(tx_start),.data(tx_data),.tx(uart_tx),.busy(tx_busy));
    reg [7:0] packet[0:7]; reg [7:0] reply[0:7];
    reg [2:0] count=0, send_index=0;
    reg [7:0] checksum=0;
    reg [3:0] state=0;
    reg [15:0] remaining=0;
    reg [15:0] gap=0;
    reg core_reset=1, enabled=1;
    reg [5:0] request=0;
    reg [7:0] write_data=0;
    wire [5:0] control; wire [3:0] nibble;
    wire [7:0] data,oe,read_data; wire done;
    byte_nibble_host host(.clk(clk),.reset(reset|core_reset),.request(request),
        .write_data(write_data),.nibble_in(data[3:0]),.control(control),
        .nibble_out(nibble),.read_data(read_data),.done(done));
    tt_um_shanebri_top emulator(.clk(clk),.rst_n(!(reset|core_reset)),.ena(enabled),
        .ui_in({dedicated_in,control}),.uio_in({protocol_pad,nibble}),
        .uio_out(data),.uio_oe(oe),.uo_out(dedicated_out));
    genvar p;
    generate for(p=0;p<4;p=p+1) begin: pads
        assign protocol_pad[p]=oe[p+4] ? data[p+4] : 1'bz;
    end endgenerate
    integer i;
    always @(posedge clk) begin
        tx_start<=0;
        if(reset) begin
            state<=8; remaining<=8; core_reset<=1; enabled<=1;
            request<=0; count<=0; checksum<=0; reply[0]<=0; gap<=0;
        end else case(state)
            0: if(rx_valid) begin
                gap<=0;
                if(count!=0 || rx_data==8'hc3) begin
                    packet[count]<=rx_data; checksum<=checksum^rx_data;
                    count<=count+1'b1;
                    if(count==7) state<=1;
                end
            end else if(count!=0) begin
                // Discard truncated packets after twenty UART bit periods.
                // A later command starts at a fresh C3 marker.
                if(gap==20*BIT_CYCLES) begin count<=0; checksum<=0; gap<=0; end
                else gap<=gap+1'b1;
            end
            1: begin
                for(i=0;i<8;i=i+1) reply[i]<=0;
                reply[0]<=8'hc3; reply[1]<=packet[1];
                count<=0; checksum<=0;
                if(checksum!=0 || packet[6]!=0 || packet[3]>15) begin reply[2]<=1; state<=4; end
                else case(packet[2])
                    1,2: begin
                        if(!enabled || packet[5]!=0) begin reply[2]<=2; state<=4; end
                        else begin
                            request<={(packet[2]==1),(packet[2]==2),packet[3][3:0]};
                            write_data<=packet[4]; remaining<=32; state<=2;
                        end
                    end
                    3: begin core_reset<=1; enabled<=1; remaining<=8; state<=8; end
                    4: begin remaining<={packet[5],packet[4]}; state<=3; end
                    5: begin enabled<=packet[4][0]; remaining<=4; state<=3; end
                    6: begin reply[3]<=dedicated_out; state<=4; end
                    default: begin reply[2]<=3; state<=4; end
                endcase
            end
            2: begin
                remaining<=remaining-1'b1;
                if(done) begin request<=0; reply[3]<=read_data; state<=4; end
                else if(remaining==0) begin request<=0; reply[2]<=4; state<=4; end
            end
            3: if(remaining==0) state<=4; else remaining<=remaining-1'b1;
            4: begin
                reply[7]<=reply[0]^reply[1]^reply[2]^reply[3]^reply[4]^reply[5]^reply[6];
                send_index<=0; state<=5;
            end
            5: if(!tx_busy) begin tx_data<=reply[send_index]; tx_start<=1; state<=6; end
            6: if(tx_busy) state<=7;
            7: if(!tx_busy) begin
                if(send_index==7) state<=0;
                else begin send_index<=send_index+1'b1; state<=5; end
            end
            8: if(remaining==0) begin core_reset<=0; remaining<=4; state<=9; end
               else remaining<=remaining-1'b1;
            9: if(remaining==0) begin
                // Startup reset has no request; command reset has a reply.
                if(reply[0]==8'hc3) state<=4; else state<=0;
            end else remaining<=remaining-1'b1;
            default: state<=0;
        endcase
    end
endmodule
`default_nettype wire
