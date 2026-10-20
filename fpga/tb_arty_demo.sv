`timescale 1ns/1ps
`default_nettype none
module tb_arty_demo;
    reg clk = 0;
    always #10 clk = ~clk;
    reg reset = 1, button = 0;
    wire tx, ready, done;
    arty_demo #(.DEBOUNCE_CYCLES(4)) dut (
        .clk(clk), .reset(reset), .button_run(button),
        .uart_tx(tx), .ready(ready), .done(done)
    );
    integer frame_count = 0;
    reg [15:0] expected [0:7];
    integer loaded_word = 0;
    reg [7:0] staged_low;
    always @(posedge clk) begin
        if (!dut.core_reset_n) loaded_word = 0;
        else if (dut.control == 8'h13 && dut.bus_done) staged_low = dut.write_data;
        else if (dut.control == 8'h14 && dut.bus_done) begin
            if ({dut.write_data, staged_low} !== ((loaded_word < 8) ? expected[loaded_word] : 16'hc080))
                $fatal(1, "Loaded instruction mismatch at %0d", loaded_word);
            loaded_word = loaded_word + 1;
        end
        if (ready && loaded_word != 32) $fatal(1, "Incomplete program load");
    end
    task tick(input integer cycles);
        repeat (cycles) begin @(posedge clk); #1; end
    endtask
    task press;
        @(negedge clk); button = 1;
        tick(12);
    endtask
    task release_button;
        @(negedge clk); button = 0;
        tick(12);
    endtask
    task expect_u;
        integer bit_index, cycle_index;
        reg [9:0] frame;
        begin
            frame = {1'b1, 8'h55, 1'b0};
            @(negedge tx); #1;
            for (bit_index = 0; bit_index < 10; bit_index = bit_index + 1) begin
                for (cycle_index = 0; cycle_index < 434; cycle_index = cycle_index + 1) begin
                    if (tx !== frame[bit_index])
                        $fatal(1, "UART mismatch bit %0d cycle %0d", bit_index, cycle_index);
                    tick(1);
                end
            end
            if (tx !== 1) $fatal(1, "UART did not return idle");
            tick(30);
            if (!done || !ready) $fatal(1, "Demo did not complete");
            frame_count = frame_count + 1;
        end
    endtask
    initial begin
        // Compare the loader ROM with the canonical example, not a copied expectation.
        $readmemh("examples/uart_v0.hex", expected);
        tick(8);
        @(negedge clk); reset = 0;
        wait(ready); tick(2);
        if (tx !== 1 || done !== 0) $fatal(1, "Boot must be idle, waiting for BTN1");
        // A short bounce must not start execution.
        @(negedge clk); button = 1;
        tick(2);
        @(negedge clk); button = 0;
        tick(30);
        if (!ready || done || tx !== 1) $fatal(1, "Bounce triggered demo");
        press();
        expect_u();
        // Holding the button cannot retrigger, even long after completion.
        repeat (5000) begin
            tick(1);
            if (!ready || !done || tx !== 1) $fatal(1, "Held button retriggered");
        end
        release_button();
        press();
        if (done) $fatal(1, "Replay did not clear completion");
        expect_u();
        release_button();
        // Reset in the middle of a frame must abort, reload, and wait for a press.
        press();
        @(negedge tx); tick(100);
        @(negedge clk); reset = 1; button = 0;
        tick(8);
        if (tx !== 1 || done !== 0 || ready !== 0) $fatal(1, "Reset did not abort");
        @(negedge clk); reset = 0;
        wait(ready); tick(100);
        if (tx !== 1 || done !== 0) $fatal(1, "Reset unexpectedly restarted demo");
        press();
        expect_u();
        $display("PASS: ROM, boot, debounce, 434-cycle UART bits, held button, replay and reset (%0d frames)", frame_count);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "Timeout");
    end
endmodule
`default_nettype wire
