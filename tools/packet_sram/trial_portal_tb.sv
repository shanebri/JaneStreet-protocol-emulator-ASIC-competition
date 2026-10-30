`timescale 1ns/1ps
module trial_portal_tb;
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0,enable=1,commit=0;
    reg [7:0] selector=0,read_selector0=0,read_selector1=0;
    reg [31:0] data=0;
    wire [31:0] read0,read1;
    packet_sram_portal dut(.*);
    task tick; begin @(posedge clk); #1; end endtask
    task write_word(input [7:0] s,input [31:0] d);
        begin @(negedge clk); selector=s; data=d; commit=1;
            tick(); @(negedge clk); commit=0; end
    endtask
    task check(input [7:0] s,input [31:0] d);
        begin read_selector0=s; read_selector1=s; #1;
            if (read0!==d || read1!==d) $fatal(1,"portal read %h expected %h got %h/%h",s,d,read0,read1);
        end
    endtask
    integer i;
    initial begin
        tick(); @(negedge clk); rst_n=1;
        check('h20,0);
        for(i=0;i<64;i=i+1) begin
            write_word('h21,i); write_word('h22,16'ha501 ^ i);
            write_word('h23,2); repeat(5) tick();
            check('h20,2); check('h24,0); write_word('h23,4);
        end
        for(i=63;i>=0;i=i-1) begin
            write_word('h21,i); write_word('h23,1);
            repeat(5) tick(); check('h20,2); check('h24,16'ha501 ^ i);
            write_word('h23,1); check('h20,6); write_word('h23,4);
        end
        write_word('h21,64); check('h20,4); check('h21,0);
        write_word('h23,4); write_word('h22,'h10000); check('h20,4);
        write_word('h23,4); write_word('h23,3); check('h20,4);
        write_word('h23,4);
        enable=0; write_word('h21,63); write_word('h23,1);
        repeat(5) tick(); check('h20,1);
        write_word('h23,4); check('h20,5);
        enable=1; repeat(5) tick(); check('h20,6); check('h24,16'ha501 ^ 63);
        write_word('h23,4);
        @(negedge clk); rst_n=0; tick(); @(negedge clk); rst_n=1;
        check('h20,0); write_word('h21,63); write_word('h23,1);
        repeat(5) tick(); check('h24,16'ha501 ^ 63);
        $display("PASS host SRAM portal: all addresses, shared reads, command/rejection/status, pause and retention");
        $finish;
    end
    initial begin #1000000; $fatal(1,"timeout"); end
endmodule
