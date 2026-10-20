`timescale 1ns/1ps
module host_interface_tb;
    reg clk=0, rst_n=0, ena=1;
    always #10 clk=~clk;
    reg [7:0] control=0, source=0;
    reg [3:0] din=0;
    wire [3:0] address, dout, oe;
    wire we, re;
    wire [7:0] wd;
    integer writes=0, reads=0;
    reg [7:0] last_write;
    host_interface dut(clk,rst_n,ena,control,din,source,address,we,re,wd,dout,oe);
    always @(posedge clk) begin
        if (we) begin writes=writes+1; last_write=wd; end
        if (re) reads=reads+1;
        if (we && re) $fatal(1,"simultaneous core acceptance");
    end
    task tick; begin @(posedge clk); #1; end endtask
    task idle(input [3:0] addr, input integer cycles);
        begin @(negedge clk); control={4'b0,addr}; repeat(cycles) tick(); end
    endtask
    task beat(input [3:0] addr, input bit rd, input [3:0] value, input integer held);
        begin
            @(negedge clk); control={2'b0,rd,!rd,addr}; din=value;
            repeat(held) begin
                tick();
                if (oe !== (rd ? 4'hf : 0)) $fatal(1,"host enable");
            end
        end
    endtask
    integer a,v,w,r;
    initial begin
        tick(); rst_n=1; idle(0,1);
        for(a=0;a<16;a=a+1) for(v=0;v<256;v=v+1) begin
            w=writes; r=reads;
            beat(a,0,v & 15,3);
            if(writes!=w) $fatal(1,"first write side effect");
            idle(a,1+(v%7)); beat(a,0,v>>4,2);
            if(writes!=w+1 || last_write!==v[7:0]) $fatal(1,"write framing");
            idle(a,1); source=v;
            beat(a,1,0,1);
            if(dout!==v[3:0] || reads!=r+1) $fatal(1,"read first");
            source=~v; repeat(3) tick();
            if(dout!==v[3:0] || reads!=r+1) $fatal(1,"held read coherence");
            idle(a,3); beat(a,1,0,2);
            if(dout!==v[7:4] || reads!=r+1) $fatal(1,"read snapshot");
            idle(a,1);
        end
        w=writes;
        beat(2,0,9,1); idle(3,1); idle(2,2); beat(2,0,5,1);
        if(writes!=w) $fatal(1,"idle address change must abort");
        idle(2,1); beat(2,1,0,1); // direction aborts abandoned write
        idle(2,1); beat(2,0,6,1);
        if(writes!=w) $fatal(1,"direction abort");
        @(negedge clk); control=8'h32; tick();
        if(oe || we || re) $fatal(1,"resync driving");
        control=8'h12; repeat(2) tick();
        if(writes!=w) $fatal(1,"resync requires low");
        idle(2,1); beat(2,0,7,1); ena=0; tick(); ena=1;
        repeat(2) tick();
        if(writes!=w || oe) $fatal(1,"disable discards");
        idle(2,1); beat(2,0,8,1); rst_n=0; #1;
        if(oe || we || re) $fatal(1,"reset immediate gating");
        tick(); rst_n=1; idle(2,1); beat(2,0,10,1);
        if(writes!=w) $fatal(1,"reset phase");
        idle(2,1); beat(2,0,11,1);
        if(writes!=w+1 || last_write!=8'hba) $fatal(1,"reentry");
        idle(2,1); source=8'hab; r=reads; beat(2,1,0,1);
        if(reads!=r+1 || dout!=11) $fatal(1,"initial read");
        ena=0; #1;
        if(oe) $fatal(1,"disable must release held RD immediately");
        tick(); ena=1; source=8'hcd; repeat(2) tick();
        if(oe || reads!=r+1) $fatal(1,"disabled RD must require low reentry");
        idle(2,2); beat(2,1,0,1);
        if(dout!=13 || reads!=r+2) $fatal(1,"disable must discard read snapshot");
        idle(2,1); rst_n=0; tick(); rst_n=1; source=8'he7;
        idle(2,1); beat(2,1,0,1);
        if(dout!=7 || reads!=r+3) $fatal(1,"reset must discard read snapshot");
        idle(2,1); beat(3,1,0,1);
        if(dout!=7 || reads!=r+4) $fatal(1,"read address change must restart");
        $display("PASS: host all 4096 address/byte combinations, coherence, holds, gaps, abort/reset/disable/resync");
        $finish;
    end
    initial begin #3000000; $fatal(1,"host unit timeout"); end
endmodule
