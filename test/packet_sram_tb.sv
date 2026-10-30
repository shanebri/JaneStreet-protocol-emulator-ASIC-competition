`timescale 1ns/1ps
`default_nettype none
module packet_sram_tb;
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0, enable=1, req_valid=0, req_write=0, rsp_ready=0;
    reg [5:0] req_addr=0;
    reg [15:0] req_wdata=0;
    wire req_ready, rsp_valid;
    wire [15:0] rsp_rdata;
    packet_sram dut (.*);
    reg [15:0] expected [0:63];
    integer accesses=0;
    integer seed=17423;
    integer i, j, address, stalls;
    reg [15:0] value;

    task tick;
        begin @(posedge clk); #1; end
    endtask
    task low;
        begin @(negedge clk); #1; end
    endtask
    task reset;
        begin
            low(); rst_n=0; req_valid=0; rsp_ready=0;
            tick();
            if (req_ready || rsp_valid || dut.access) $fatal(1,"reset interface");
            low(); rst_n=1; enable=1;
            #1;
            if (!req_ready || rsp_valid) $fatal(1,"reset recovery");
        end
    endtask
    always @(posedge clk) begin
        if (dut.access) begin
            accesses=accesses+1;
            if (dut.memory.A_WEN && dut.memory.A_REN) $fatal(1,"read/write overlap");
            if (!rst_n || !enable) $fatal(1,"access while disabled/reset");
        end
    end

    // Each accepted request at N issues at N+1 and responds at N+2. Change
    // request pins after N to prove the macro uses the buffered fields.
    task transaction(input bit wr, input [5:0] addr, input [15:0] data,
                     input integer hold_cycles, input bit pause_issue);
        integer count_before, k;
        reg [15:0] result;
        begin
            low();
            if (!req_ready) $fatal(1,"not ready before request");
            req_valid=1; req_write=wr; req_addr=addr; req_wdata=data;
            count_before=accesses;
            tick();
            if (req_ready || rsp_valid || accesses!=count_before) $fatal(1,"accept latency");
            low(); req_valid=0; req_addr=~addr; req_wdata=~data; req_write=~wr;
            if (pause_issue) begin
                enable=0;
                repeat (3) begin
                    tick();
                    if (req_ready || rsp_valid || accesses!=count_before) $fatal(1,"pending pause");
                    low();
                end
                enable=1;
            end
            tick();
            if (rsp_valid || accesses!=count_before+1) $fatal(1,"issue latency/count");
            // An issued access must complete even when admission is paused.
            low(); enable=0;
            tick();
            result=wr ? 16'd0 : expected[addr];
            if (!rsp_valid || rsp_rdata!==result || req_ready) $fatal(1,"response/data");
            if (wr) expected[addr]=data;
            for (k=0;k<hold_cycles;k=k+1) begin
                low(); enable=k[0]; req_valid=1;
                tick();
                if (!rsp_valid || rsp_rdata!==result || req_ready || accesses!=count_before+1)
                    $fatal(1,"backpressure stability/no extra access");
            end
            low(); enable=0; req_valid=1; rsp_ready=1;
            tick();
            if (rsp_valid || req_ready || accesses!=count_before+1) $fatal(1,"response drain while disabled");
            low(); enable=1; req_valid=0; rsp_ready=0;
        end
    endtask

    initial begin
        reset();
        low(); enable=0; req_valid=1; req_write=1;
        repeat (3) begin
            tick();
            if (req_ready || rsp_valid || accesses!=0) $fatal(1,"disabled admission");
        end
        low(); req_valid=0; enable=1;
        // Initialize all locations, then check data/address independence.
        for (i=0;i<64;i=i+1) transaction(1,i,16'hb109 ^ (i*257),i%3,0);
        for (i=63;i>=0;i=i-1) transaction(0,i,0,i%5,i%7==0);
        for (j=0;j<250;j=j+1) begin
            address=($random(seed) & 32'h7fffffff)%64;
            value=$random(seed);
            stalls=($random(seed) & 32'h7fffffff)%6;
            transaction(j%3!=0,address,value,stalls,j%11==0);
        end
        // Reset cancels a buffered write before macro issue.
        low(); req_valid=1; req_write=1; req_addr=12; req_wdata=16'hffff;
        tick();
        reset();
        transaction(0,12,0,0,0);
        // Reset after macro issue discards acknowledgement, retains the write.
        low(); req_valid=1; req_write=1; req_addr=12; req_wdata=16'h8234;
        tick(); low(); req_valid=0; tick(); expected[12]=16'h8234;
        reset(); transaction(0,12,0,2,0);
        // Reset a held response; memory contents survive.
        low(); req_valid=1; req_write=0; req_addr=12;
        tick(); low(); req_valid=0; tick(); tick();
        if (!rsp_valid) $fatal(1,"missing held response");
        reset(); transaction(0,12,0,0,0);
        // Held valid is accepted only while ready; no bypass on response drain.
        low(); req_valid=1; req_write=0; req_addr=12; rsp_ready=1;
        for (i=0;i<4;i=i+1) begin
            tick();
            if (i==2 && (!rsp_valid || rsp_rdata!==expected[12])) $fatal(1,"ready response");
        end
        if (!req_ready || rsp_valid) $fatal(1,"minimum transaction spacing");
        low(); req_valid=0; rsp_ready=0;
        $display("PASS packet SRAM: official macro model, latency, all addresses, random data, backpressure, pause and reset (%0d accesses)",accesses);
        $finish;
    end
    initial begin #1000000; $fatal(1,"timeout"); end
endmodule
`default_nettype wire
