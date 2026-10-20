`default_nettype none
`timescale 1ns/1ps
// Byte-side boundary tests place host and both engine FIFO operations on one edge.
module pio_subsystem_tb;
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0, enable=1, wr=0, rd=0;
    reg [3:0] address=0;
    reg [7:0] data=0;
    reg [5:0] pin_in=0;
    wire [7:0] read_data;
    wire [11:0] pins;
    wire [3:0] directions, od;
    pio_subsystem dut(.clk(clk), .rst_n(rst_n), .enable(enable),
        .host_address(address), .host_write_en(wr), .host_read_en(rd),
        .host_write_data(data), .host_read_data(read_data), .pin_in(pin_in),
        .pins(pins), .directions(directions), .open_drain(od));
    task write_byte(input [3:0] a, input [7:0] d);
        begin
            @(negedge clk); address=a; data=d; wr=1;
            @(posedge clk); #1;
            @(negedge clk); wr=0;
        end
    endtask
    task word(input [7:0] selector, input [31:0] value);
        begin
            write_byte(5,selector); write_byte(6,value[7:0]);
            write_byte(7,value[15:8]); write_byte(9,value[23:16]);
            write_byte(10,value[31:24]);
        end
    endtask
    task instruction(input [15:0] value);
        begin write_byte(3,value[7:0]); write_byte(4,value[15:8]); end
    endtask
    task check(input condition, input [511:0] message);
        if (condition !== 1'b1) $fatal(1,"%0s",message);
    endtask
    integer e, i;
    initial begin
        #100000; $fatal(1,"subsystem watchdog");
    end
    initial begin
        repeat(3) @(negedge clk);
        rst_n=1;
        for(e=0;e<2;e=e+1) begin
            write_byte(15,e[7:0]);
            write_byte(2,0);
            instruction(16'h2080); // WAIT 1 GPIO 0
            instruction(16'h80a0); // PULL block
            instruction(16'ha0c7); // MOV ISR,OSR
            instruction(16'h8020); // PUSH block
            instruction(16'h0001); // JMP 1
            for(i=0;i<4;i=i+1) word(8,32'h12340000+(e*256)+i);
        end
        word(8'h1c,3); // Both wait on the same sampled input.
        write_byte(15,0);
        // Stage an extra TX0 word while engines remain at WAIT.
        write_byte(5,8); write_byte(6,8'hef); write_byte(7,8'hbe); write_byte(9,8'had);
        pin_in=1;
        wait(dut.engines[0].core.current_pc==1);
        // Both full TX queues pop; only TX0 also pushes, preserving old head.
        @(negedge clk); address=10; data=8'hde; wr=1;
        @(posedge clk); #1;
        check(dut.engines[0].core.osr==32'h12340000,"TX0 did not consume old head");
        check(dut.engines[1].core.osr==32'h12340100,"TX1 did not consume old head");
        check(dut.engines[0].core.tx_level==4,"full TX0 simultaneous pop/push");
        check(dut.engines[1].core.tx_level==3,"TX1 pop coupled to selected host");
        @(negedge clk); wr=0;
        // Engine0 eventually blocks pushing its fifth word; engine1 waits for TX.
        wait(dut.engines[0].core.current_pc==3 && dut.engines[0].core.rx_level==4);
        check(dut.engines[1].core.rx_level==4,"simultaneous RX fills");
        write_byte(15,1);
        write_byte(5,8); write_byte(6,8'h55); write_byte(7,8'h66); write_byte(9,8'h77);
        // Empty TX has no host-write fall-through at the PULL attempt edge.
        @(negedge clk); address=10; data=8'h88; wr=1;
        @(posedge clk); #1;
        check(dut.engines[1].core.current_pc==1,"empty TX bypassed host write");
        check(dut.engines[1].core.tx_level==1,"empty TX host enqueue");
        @(negedge clk); wr=0;
        @(posedge clk); #1;
        check(dut.engines[1].core.osr==32'h88776655,"TX refill not consumed next tick");
        wait(dut.engines[1].core.current_pc==3);
        repeat(2) @(negedge clk);
        check(dut.engines[0].core.current_pc==3,"RX0 did not remain blocked");
        // RX0 pop creates room only for engine0; simultaneous push keeps it full.
        write_byte(15,0); write_byte(5,9);
        @(negedge clk); address=6; rd=1;
        #1; check(read_data==0,"RX0 old head low byte");
        @(posedge clk); #1;
        check(dut.engines[0].core.rx_level==4,"RX0 full pop/push");
        check(dut.engines[0].core.current_pc==4,"RX0 host pop did not unblock PUSH");
        check(dut.engines[1].core.current_pc==3,"RX0 pop incorrectly unblocked RX1");
        @(negedge clk); rd=0;
        check(dut.engines[0].bank.data_snapshot==32'h12340000,"RX0 snapshot not old head");
        write_byte(15,1); write_byte(5,9);
        @(negedge clk); address=6; rd=1;
        @(posedge clk); #1;
        check(dut.engines[1].core.rx_level==4,"RX1 full pop/push");
        check(dut.engines[1].core.current_pc==4,"RX1 pop did not unblock PUSH");
        @(negedge clk); rd=0;
        check(dut.engines[1].bank.data_snapshot==32'h12340100,"RX1 snapshot isolation");
        // Clear alone while running is ignored. Abort+clear is engine-local.
        word(8'h1c,3<<8);
        check(dut.engines[0].core.rx_level==4 && dut.engines[1].core.rx_level==4,"live FIFO clear accepted");
        word(8'h1c,(1<<6)|(1<<8));
        check(dut.running==2'b10,"group abort mask or priority");
        check(dut.engines[0].core.rx_level==0 && dut.engines[1].core.rx_level==4,"group FIFO clear leaked");
        check(dut.engines[0].core.debug_flags==0 && dut.engines[1].core.debug_flags==0,"unexpected queue error");
        $display("PASS: subsystem simultaneous FIFO edges and group isolation");
        $finish;
    end
endmodule
`default_nettype wire
