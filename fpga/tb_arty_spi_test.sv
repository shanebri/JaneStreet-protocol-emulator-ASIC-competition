`timescale 1ns/1ps
`default_nettype none
module tb_arty_spi_test;
    reg clk = 0;
    always #10 clk = !clk;
    reg reset = 1, button = 0, slave_ready = 0, miso = 0;
    wire mosi, sclk, cs_n, uart_tx, ready, passed, failed, finished;
    arty_spi_test_host #(.SPI_DIVIDER(2), .DEBOUNCE_CYCLES(4),
        .TIMEOUT_CYCLES(5000), .UART_BIT_CYCLES(4)) dut (
        .clk(clk), .reset(reset), .button_run(button), .slave_ready(slave_ready),
        .miso(miso), .mosi(mosi), .sclk(sclk), .cs_n(cs_n), .uart_tx(uart_tx),
        .ready(ready), .passed(passed), .failed(failed), .finished(finished)
    );
    integer phase = 0, transactions = 0, reports = 0;
    reg [15:0] canonical [0:9];
    reg [7:0] response, captured;
    integer bit_number, i;
    reg [7:0] packet [0:6];

    task tick(input integer cycles);
        repeat (cycles) begin @(posedge clk); #1; end
    endtask
    task initialize;
        @(negedge clk); reset = 1; button = 0; slave_ready = 0;
        tick(5);
        transactions = 0; reports = 0;
        @(negedge clk); reset = 0;
        wait(ready); tick(5);
        if (cs_n !== 1 || sclk !== 0) $fatal(1, "Bad idle after boot");
    endtask
    task start_batch;
        @(negedge clk); button = 1;
        tick(12);
        @(negedge clk); button = 0;
    endtask
    task receive_uart(output reg [7:0] data);
        integer b;
        begin
            @(negedge uart_tx);
            #40; // Center of start bit: 4 core clocks per UART bit.
            if (uart_tx !== 0) $fatal(1, "UART start bit");
            for (b = 0; b < 8; b = b + 1) begin
                #80;
                data[b] = uart_tx;
            end
            #80;
            if (uart_tx !== 1) $fatal(1, "UART stop bit");
        end
    endtask

    // Independently emulate a mode-0 slave, delayed relative to SCLK edges.
    initial forever begin
        @(negedge cs_n);
        if (!reset) begin
            if (!slave_ready) $fatal(1, "Master selected an unready slave");
            response = transactions[7:0] ^ 8'ha5;
            if (phase == 1 && transactions == 3) response = response ^ 1;
            captured = 0;
            #25; miso = response[7];
            for (bit_number = 7; bit_number >= 0; bit_number = bit_number - 1) begin
                @(posedge sclk);
                if (cs_n !== 0) $fatal(1, "CS inactive on sampling edge");
                captured[bit_number] = mosi;
                @(negedge sclk);
                if (bit_number != 0) begin #25; miso = response[bit_number - 1]; end
            end
            @(posedge cs_n);
            if (captured !== transactions[7:0]) $fatal(1, "MOSI mismatch %0d: %h", transactions, captured);
            transactions = transactions + 1;
            slave_ready = 0;
            tick(40); // READY returns high BEFORE the report completes: latch must retain low.
            if (transactions < 256) slave_ready = 1;
        end
    end

    initial forever begin
        for (i = 0; i < 7; i = i + 1) receive_uart(packet[i]);
        if (packet[0] !== 8'ha5 || packet[1] !== 8'h5a ||
            (packet[0] ^ packet[1] ^ packet[2] ^ packet[3] ^ packet[4] ^ packet[5] ^ packet[6]) !== 0)
            $fatal(1, "UART report framing/checksum");
        if (phase < 2) begin
            if (packet[2] !== reports[7:0] || packet[3] !== reports[7:0]) $fatal(1, "Report sequence");
            if (packet[4] !== (reports[7:0] ^ 8'ha5 ^ ((phase == 1 && reports == 3) ? 8'd1 : 8'd0)))
                $fatal(1, "Report did not contain actual PIO RX");
            if (packet[5] !== ((phase == 1 && reports == 3) ? 8'd1 : 8'd0)) $fatal(1, "Wrong result code");
        end else if (packet[2] !== 0 || packet[5] !== 4) $fatal(1, "Missing READY timeout report");
        reports = reports + 1;
    end

    initial begin
        $readmemh("examples/spi_mode0.hex", canonical);
        for (integer w = 0; w < 10; w = w + 1)
            if (dut.program_word(w) !== canonical[w]) $fatal(1, "Loader ROM differs from assembly at %0d", w);
        initialize();
        slave_ready = 1;
        start_batch();
        wait(finished); tick(10);
        if (!passed || failed || reports != 256 || transactions != 256) $fatal(1, "Good batch failed");
        // A real MISO mismatch must set the sticky failure LED and be reported.
        phase = 1;
        initialize(); slave_ready = 1; start_batch();
        wait(finished); tick(10);
        if (passed || !failed || reports != 256 || transactions != 256) $fatal(1, "Bad batch passed");
        // A disconnected slave must time out, without clocking it or claiming success.
        phase = 2;
        initialize(); start_batch();
        wait(finished); tick(10);
        if (passed || !failed || reports != 1 || transactions != 0 || !cs_n || sclk)
            $fatal(1, "Missing slave not handled safely");
        $display("PASS: 512 PIO SPI transactions, UART reports, mismatch detection and missing-slave timeout");
        $finish;
    end
    initial begin #50000000; $fatal(1, "SPI hardware testbench timeout"); end
endmodule
`default_nettype wire
