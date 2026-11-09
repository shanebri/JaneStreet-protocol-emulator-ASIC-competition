`timescale 1ns/1ps
`default_nettype none

module usb_ls_setup_ack_tb;
    localparam [1:0] J = 2'b01, K = 2'b10, SE0 = 0;
    reg clk = 0, reset = 1;
    reg [1:0] host_line = J;
    wire [2:0] rx_pins;
    wire [1:0] tx_pins;
    wire tx_oe_n;
    reg crossover_test = 0;
    wire [1:0] bus_line = tx_oe_n ? host_line : tx_pins;
    wire [1:0] previous_bus_line;
    assign #210 previous_bus_line = bus_line;
    wire crossover = crossover_test &&
        ((bus_line == J && previous_bus_line == K) || (bus_line == K && previous_bus_line == J));
    // Independent delays approximate transceiver propagation/skew and echo.
    assign #4 rx_pins[0] = !crossover && bus_line[0];
    assign #4 rx_pins[1] = !crossover && bus_line[1];
    assign #11 rx_pins[2] = bus_line == K;
`ifdef USB_ROUTED_TOP
    reg clk100 = 0;
    wire locked_led;
    wire [3:0] unused_pads;
    always #5 clk100 = !clk100;
    arty_bringup_top dut (
        .clk100(clk100), .btn_reset(reset), .uart_rx(1'b1), .uart_tx(),
        .dedicated_in(2'b00), .dedicated_out(), .protocol_pad(unused_pads),
        .locked_led(locked_led), .usb_rx(rx_pins), .usb_tx(tx_pins),
        .usb_tx_oe_n(tx_oe_n)
    );
    localparam integer RESET_CHECK_NS = 61; // board button synchronizer
`else
    always #10 clk = !clk;
    usb_ls_setup_ack dut (.*);
    localparam integer RESET_CHECK_NS = 1;
`endif

    real bit_ns = 666.667;
    realtime data_eop;
    realtime ack_sop;
    integer replies = 0;
    always @(negedge tx_oe_n) if (!reset) begin
        replies = replies + 1;
        ack_sop = $realtime;
    end

    // USB transmits the complemented remainder, most significant stage first.
    function automatic [4:0] token_crc(input [10:0] token);
        reg [4:0] remainder;
        integer bit_index;
        begin
            remainder = 5'h1f;
            for (bit_index = 0; bit_index < 11; bit_index = bit_index + 1)
                remainder = (remainder << 1) ^ ((remainder[4] ^ token[bit_index]) ? 5'h05 : 5'd0);
            for (bit_index = 0; bit_index < 5; bit_index = bit_index + 1)
                token_crc[bit_index] = !remainder[4-bit_index];
        end
    endfunction

    function automatic [15:0] data_crc(input [63:0] payload);
        reg [15:0] remainder;
        integer bit_index;
        begin
            remainder = 16'hffff;
            for (bit_index = 0; bit_index < 64; bit_index = bit_index + 1)
                remainder = (remainder << 1) ^ ((remainder[15] ^ payload[bit_index]) ? 16'h8005 : 16'd0);
            for (bit_index = 0; bit_index < 16; bit_index = bit_index + 1)
                data_crc[bit_index] = !remainder[15-bit_index];
        end
    endfunction

    task automatic packet(input [95:0] bits, input integer length,
                          input bit bad_stuff, input integer eop_cells);
        integer ones, index;
        reg [1:0] symbol;
        begin
            ones = 0;
            symbol = J;
            for (index = 0; index < length; index = index + 1) begin
                if (!bits[index]) symbol = ~symbol;
                host_line = symbol;
                #(bit_ns);
                ones = bits[index] ? ones + 1 : 0;
                if (ones == 6) begin
                    if (!bad_stuff) symbol = ~symbol;
                    host_line = symbol;
                    #(bit_ns);
                    ones = 0;
                end
            end
            host_line = SE0;
            #(eop_cells * bit_ns);
            host_line = J;
        end
    endtask

    task automatic setup(input [10:0] token = 0, input bit corrupt_crc = 0,
                         input [7:0] pid = 8'h2d);
        begin
            packet({64'd0, token_crc(token) ^ {4'd0, corrupt_crc}, token, pid, 8'h80}, 32, 0, 2);
            #(3 * bit_ns);
        end
    endtask

    task automatic data(input [63:0] payload = 64'hffff_ffff_ffff_ffff,
                        input bit corrupt_crc = 0, input bit corrupt_stuff = 0,
                        input [7:0] pid = 8'hc3, input integer eop_cells = 2,
                        input integer length = 96);
        begin
            packet({data_crc(payload) ^ {15'd0, corrupt_crc}, payload, pid, 8'h80},
                   length, corrupt_stuff, eop_cells);
            data_eop = $realtime;
        end
    endtask

    task automatic expect_ack;
        integer index, cell_ns;
        reg [1:0] symbol;
        reg [15:0] response;
        real turnaround;
        begin
            while (tx_oe_n && $realtime < data_eop + 4400) #1;
            if (tx_oe_n) $fatal(1, "Missing ACK at %f ns", $realtime);
            turnaround = ack_sop - data_eop;
            if (turnaround < 1333.333 || turnaround > 4333.333)
                $fatal(1, "ACK turnaround outside target: %f ns", turnaround);
            response = 16'hd280;
            symbol = J;
            #(10 - ($realtime - ack_sop));
            for (index = 0; index < 19; index = index + 1) begin
                if (index == 18) symbol = J;
                else if (index >= 16) symbol = SE0;
                else if (!response[index]) symbol = ~symbol;
                cell_ns = index % 3 == 2 ? 680 : 660;
                if (tx_oe_n !== 0 || tx_pins !== symbol)
                    $fatal(1, "Wrong ACK symbol %0d", index);
                #(cell_ns);
            end
            #1;
            if (tx_oe_n !== 1) $fatal(1, "Transceiver did not release after ACK");
            $display("ACK turnaround %0.3f ns at host bit period %0.3f ns", turnaround, bit_ns);
            #(2.2 * bit_ns);
        end
    endtask

    task automatic no_reply(input integer expected_replies);
        #5000;
        if (replies != expected_replies || tx_oe_n !== 1)
            $fatal(1, "Unexpected ACK: %0d vs %0d", replies, expected_replies);
    endtask

    initial begin
`ifdef USB_ROUTED_TOP
        wait (locked_led === 1'b1);
`endif
        #213;
        if (tx_oe_n !== 1) $fatal(1, "OE must be inactive in reset");
        reset = 0;
        #6000;

        setup(); data(); expect_ack();
        bit_ns = 656.814; // +1.5% frequency
        setup(); data(64'h0302_0100_0100_0680); expect_ack();
        bit_ns = 676.819; // -1.5% frequency
        crossover_test = 1;
        setup(); data(64'h0102_ffff_ffff_5678); expect_ack();
        crossover_test = 0;
        bit_ns = 666.667;

        data(); no_reply(3);
        setup(11'h001); data(); no_reply(3);
        setup(11'h080); data(); no_reply(3);
        setup(0, 1); data(); no_reply(3);
        setup(0, 0, 8'h3d); data(); no_reply(3);
        setup(); data(64'd0, 1); no_reply(3);
        setup(); data(64'hffff_ffff_ffff_ffff, 0, 1); no_reply(3);
        setup(); data(64'd0, 0, 0, 8'h4b); no_reply(3);
        setup(); data(64'd0, 0, 0, 8'hc3, 1); no_reply(3);
        setup(); data(64'd0, 0, 0, 8'hc3, 4); no_reply(3);
        setup(); data(64'd0, 0, 0, 8'hc3, 2, 88); no_reply(3);
        setup(); #14000; data(); no_reply(3);

        // New traffic before launch cancels the ACK and long SE0 clears state.
        setup(); data(); #1000; host_line = SE0; #15000; host_line = J;
        no_reply(3);
        setup(); host_line = SE0; #15000; host_line = J; #2000;
        data(); no_reply(3);

        // Reset cancels a queued reply, and releases OE during a driven reply.
        setup(); data(); #1000; reset = 1; #102; reset = 0; no_reply(3);
        setup(); data();
        @(negedge tx_oe_n);
        #17; reset = 1; #(RESET_CHECK_NS);
        if (tx_oe_n !== 1) $fatal(1, "Reset did not release OE");
        #103; reset = 0; #6000;
        data(); no_reply(4);
        setup(); data(); expect_ack();
        if (replies != 5) $fatal(1, "Wrong reply count");
        $display("USB-LS SETUP/ACK checks passed");
        $finish;
    end

    initial begin
        #5000000;
        $fatal(1, "Test timeout");
    end
endmodule

`default_nettype wire
