`timescale 1ns/1ps
module tb_arty_uart_diagnostic;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 0, button = 0;
    wire tx;
    wire [3:0] led;
    arty_uart_diagnostic #(.GAP_CYCLES(1000)) dut (
        .clk100(clk), .btn_reset(reset), .btn_run(button),
        .uart_tx(tx), .led(led)
    );
    integer n, b, cycle;
    reg [9:0] expected = {1'b1, 8'h55, 1'b0};
    initial begin
        for (n = 0; n < 3; n = n + 1) begin
            @(negedge tx); #1;
            for (b = 0; b < 10; b = b + 1) begin
                for (cycle = 0; cycle < 868; cycle = cycle + 1) begin
                    if (tx !== expected[b]) $fatal(1, "Frame %0d bit %0d cycle %0d", n, b, cycle);
                    @(posedge clk); #1;
                end
            end
            if (tx !== 1 || led[1] !== ((n + 1) % 2)) $fatal(1, "Completion/idle mismatch");
        end
        @(negedge clk); button = 1; reset = 1;
        repeat (5) @(posedge clk);
        #1;
        if (tx !== 1 || led[1] !== 0 || led[0] !== 1) $fatal(1, "Button/reset mismatch");
        $display("PASS: three diagnostic U frames, 868 clocks/bit, completion LED and reset.");
        $finish;
    end
    initial begin #1000000; $fatal(1, "Timeout"); end
endmodule
