`timescale 1ns/1ps
module tb_arty_i2c_bridge;
    reg clk=0, reset=1;
    always #10 clk=~clk;
    reg [5:0] request=0;
    reg [7:0] wr=0;
    wire [7:0] rd, dedicated;
    wire done;
    tri1 [3:0] pads;
    reg target_low=0;
    assign pads[0]=target_low ? 1'b0 : 1'bz;
    arty_i2c_bridge dut(clk,reset,request,wr,rd,done,2'b0,dedicated,pads);
    reg [15:0] program_words [0:23];
    task tick; begin @(posedge clk); #1; end endtask
    task byte_write(input [3:0] addr,input [7:0] value);
        begin
            @(negedge clk); request={2'b01,addr}; wr=value;
            while(!done) tick();
            @(negedge clk); request=0; repeat(2) tick();
        end
    endtask
    task byte_read(input [3:0] addr,output [7:0] value);
        begin
            @(negedge clk); request={2'b10,addr};
            while(!done) tick();
            value=rd;
            @(negedge clk); request=0; repeat(2) tick();
        end
    endtask
    task word_write(input [7:0] sel,input [31:0] value);
        begin byte_write(5,sel); byte_write(6,value[7:0]); byte_write(7,value[15:8]);
            byte_write(9,value[23:16]); byte_write(10,value[31:24]); end
    endtask
    integer n, starts=0, stops=0, pulses=0;
    reg active=0;
    reg [8:0] observed=0;
    always @(negedge pads[0]) if(pads[1]===1 && !reset) begin
        starts=starts+1; active=1; pulses=0; observed=0;
    end
    always @(posedge pads[1]) if(active && pulses<9) begin
        pulses=pulses+1; observed={observed[7:0],pads[0]};
    end
    always @(posedge pads[0]) if(pads[1]===1 && active) begin
        stops=stops+1; active=0;
    end
    reg [7:0] value;
    initial begin
        $readmemh("examples/i2c.hex",program_words);
        repeat(3) tick(); reset=0; repeat(2) tick();
        byte_read(15,value); if(value!=8'h21) $fatal(1,"version");
        byte_write(2,0);
        for(n=0;n<24;n=n+1) begin byte_write(3,program_words[n][7:0]); byte_write(4,program_words[n][15:8]); end
        word_write(16,1); word_write(17,32'hd7e0);
        word_write(22,1 | (8<<1) | (1<<5) | (8<<9) | (1<<13) | (2<<17) | (9<<20));
        word_write(19,6); word_write(24,32'h300); word_write(25,3); word_write(23,32'h300);
        byte_write(0,1); word_write(8,9); word_write(8,32'h21302);
        value=0; while(!(value&8'h70)) byte_read(11,value);
        byte_write(5,9); byte_read(6,value);
        if(!value[0]) $fatal(1,"pull-up target must NACK");
        word_write(8,16);
        value=0; while(!value[0]) byte_read(12,value);
        if(starts!=1 || stops!=1 || pulses!=9 || observed!=9'h121) $fatal(1,"wire framing");
        if(dedicated!=1 || pads!=15) $fatal(1,"idle or unrelated pins");
        // Negative contention test: a push-pull high against external low is X.
        byte_write(0,2); word_write(24,0); target_low=1; #1;
        if(pads[0]!==1'bx) $fatal(1,"resolved contention not detected");
        byte_write(0,32); #1;
        if(pads[0]!==0) $fatal(1,"abort did not release contended pad");
        target_low=0; #1;
        if(pads!==4'hf) $fatal(1,"released pullups");
        $display("PASS: FPGA nibble adapter, 24-word I2C firmware, tri-state readback, NACK/STOP, contention and abort");
        $finish;
    end
    initial begin #1000000; $fatal(1,"FPGA I2C timeout"); end
endmodule
