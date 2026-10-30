`default_nettype none
`timescale 1ns/1ps
// Guard the one-edge PC/fetch contract before any timing-driven restructuring.
module frontend_timing_tb;
    reg clk=0, rst=1, restart=0, advance=0, branch=0, load_we=0;
    reg [4:0] entry=0, target=0, wrap_bottom=0, wrap_top=31, load_addr=0;
    reg [15:0] load_data=0;
    wire [4:0] address;
    wire [15:0] instruction, host_data;
    reg [15:0] model [0:31];
    integer a, b;
    always #10 clk=~clk;
    pc counter(clk,rst,restart,advance,branch,entry,target,wrap_bottom,wrap_top,address);
    instruction_fetch fetch(clk,address,load_we,load_addr,load_data,instruction,host_data);
    task tick; begin @(posedge clk); #1; end endtask
    task check(input [4:0] expected);
        begin
            if (address !== expected || instruction !== model[expected])
                $fatal(1,"PC/fetch latency or data mismatch: expected %0d got %0d",expected,address);
            if (host_data !== model[load_addr]) $fatal(1,"host read mismatch");
        end
    endtask
    initial begin
        // Initialize every address: never rely on uninitialized memory values.
        for(a=0;a<32;a=a+1) begin
            @(negedge clk); load_we=1; load_addr=a; load_data=16'h9317 ^ (a*16'h129);
            model[a]=load_data; tick();
        end
        @(negedge clk); load_we=0; rst=0;
        // Every branch destination and independent host address, with no extra
        // fetch clock allowed. Also cover restart priority over branch/advance.
        for(a=0;a<32;a=a+1) begin
            @(negedge clk); restart=1; entry=a; advance=1; branch=1; target=31-a;
            tick(); check(a);
            for(b=0;b<32;b=b+1) begin
                @(negedge clk); restart=0; target=b; load_addr=31-b;
                tick(); check(b);
            end
        end
        // Freeze, wrap and natural overflow preserve exact retirement timing.
        @(negedge clk); advance=0; target=7; tick(); check(31);
        @(negedge clk); advance=1; branch=0; wrap_bottom=9; tick(); check(9);
        @(negedge clk); wrap_top=8; restart=1; entry=31; tick(); check(31);
        @(negedge clk); restart=0; tick(); check(0);
        // A write is visible to both asynchronous ports after its accepted edge,
        // including a collision with the currently fetched address.
        @(negedge clk); advance=0; load_addr=0; load_data=16'hbeef; load_we=1;
        #1; check(0);
        tick(); model[0]=16'hbeef; check(0);
        @(negedge clk); load_we=0; load_data=0; rst=1; restart=1; entry=12;
        tick(); check(0);
        // Reset of the PC must retain all previously programmed words.
        @(negedge clk); rst=0; restart=0; advance=1; branch=1;
        for(a=0;a<32;a=a+1) begin
            @(negedge clk); target=a; load_addr=a; tick(); check(a);
        end
        $display("PASS: frontend all-address branch/read, restart, freeze, wrap, write collision and retention");
        $finish;
    end
    initial begin #100000; $fatal(1,"frontend timeout"); end
endmodule
`default_nettype wire
