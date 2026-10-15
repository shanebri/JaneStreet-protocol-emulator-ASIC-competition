`timescale 1ns/1ps
`default_nettype none
// Exhaust all occupancy/push/pop combinations, then exercise pointer wrap.
module pio_fifo_tb;
    reg clk = 0, rst = 1, clear = 0, push = 0, pop = 0;
    reg [31:0] write_data = 0;
    wire [31:0] read_data;
    wire full, empty;
    wire [2:0] level;
    pio_fifo dut (.*);
    reg [31:0] model [0:3];
    integer used = 0, serial = 0;
    integer occupancy, operation, n;
    task cycle(input reg do_push, do_pop, do_clear);
        reg accepted_pop, accepted_push;
        integer i;
        begin
            clk = 0; push = do_push; pop = do_pop; clear = do_clear;
            write_data = 32'h80000000 + serial;
            serial = serial + 1;
            #5;
            if (read_data !== (used == 0 ? 32'd0 : model[0])) $fatal(1, "old head mismatch");
            accepted_pop = do_pop && used > 0;
            accepted_push = do_push && (used < 4 || accepted_pop);
            if (rst || do_clear) used = 0;
            else begin
                if (accepted_pop) begin
                    for (i = 0; i < 3; i = i + 1) model[i] = model[i+1];
                    used = used - 1;
                end
                if (accepted_push) begin model[used] = write_data; used = used + 1; end
            end
            clk = 1; #5;
            if (level !== used[2:0] || full !== (used == 4) || empty !== (used == 0))
                $fatal(1, "occupancy mismatch");
            if (read_data !== (used == 0 ? 32'd0 : model[0])) $fatal(1, "new head mismatch");
        end
    endtask
    initial begin
        // Initialize before checking the FIFO's combinational flags.
        #5; clk = 1; #5; rst = 0;
        for (occupancy = 0; occupancy <= 4; occupancy = occupancy + 1)
            for (operation = 0; operation < 4; operation = operation + 1) begin
                cycle(0, 0, 1);
                for (n = 0; n < occupancy; n = n + 1) cycle(1, 0, 0);
                cycle(operation[0], operation[1], 0);
                cycle(1, 1, 1); // Clear wins even simultaneous traffic.
            end
        for (n = 0; n < 1000; n = n + 1)
            cycle((n % 7) < 4, (n % 11) < 5, 0);
        $display("PASS: FIFO occupancy, full/empty simultaneous traffic, clear and wrap");
        $finish;
    end
endmodule
`default_nettype wire
