`timescale 1ns/1ps
module pio_pads_tb;
    reg rst_n=1;
    reg [11:0] values;
    reg [3:0] dirs, od;
    wire [7:0] dedicated;
    wire [3:0] data, oe;
    pio_pads dut(rst_n,values,dirs,od,dedicated,data,oe);
    integer v,d,o,p;
    initial begin
        // Independently classify each physical driver, including mixed modes.
        for(v=0;v<16;v=v+1) for(d=0;d<16;d=d+1) for(o=0;o<16;o=o+1) begin
            values={v[3:0],8'ha5}; dirs=d; od=o; #1;
            if(dedicated!=8'ha5) $fatal(1,"dedicated outputs changed");
            for(p=0;p<4;p=p+1) begin
                if(!dirs[p] || (od[p] && values[8+p])) begin
                    if(oe[p]) $fatal(1,"released pad driven");
                end else if(!oe[p] || data[p]!==values[p+8]) $fatal(1,"driven pad mismatch");
                if(od[p] && data[p]) $fatal(1,"open drain drives high");
            end
            rst_n=0; #1;
            if(oe) $fatal(1,"asynchronous reset OE gate");
            rst_n=1;
        end
        $display("PASS: all 4096 mixed value/direction/electrical-mode combinations");
        $finish;
    end
endmodule
