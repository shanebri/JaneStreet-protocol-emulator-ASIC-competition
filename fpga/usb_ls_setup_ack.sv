`default_nettype none

// One USB-LS default-address SETUP transaction. The front end owns the
// electrical interface. There is no dependency on the host or PIO bus.
module usb_ls_setup_ack (
    input wire clk, reset,
    input wire [2:0] rx_pins,     // {RCV, VP, VM} from the USB transceiver
    output reg [1:0] tx_pins,   // {VPO, VMO} to the USB transceiver
    output wire tx_oe_n
);
    localparam [1:0] J = 2'b01, K = 2'b10, SE0 = 2'b00, SE1 = 2'b11;
    localparam [3:0] SINGLE_ENDED_QUALIFY = 4'd12;
    localparam [15:0] ACK = 16'hd280; // SYNC, PID (LSB first); no stuffing
    typedef enum logic [2:0] {DROP, IDLE, RECEIVE, EOP, TURN, TRANSMIT} state_t;

    (* ASYNC_REG = "TRUE" *) reg [2:0] rx_meta, rx_sync;
    reg [1:0] rx_history, line, previous_line;
    reg [3:0] single_ended_clocks;
    reg [7:0] idle_clocks;
    wire single_ended = rx_sync[1] == rx_sync[0];
    always @(posedge clk) begin
        if (reset) begin
            rx_meta <= 0;
            rx_sync <= 0;
            rx_history <= SE0;
            single_ended_clocks <= 0;
            line <= SE0;
            previous_line <= SE0;
            idle_clocks <= 0;
        end else begin
            rx_meta <= rx_pins;
            rx_sync <= rx_meta;
            rx_history <= rx_sync[1:0];
            // A low-speed differential crossover may look like SE0 on
            // VP/VM for up to 210 ns. Decode J/K with the differential
            // receiver and accept SE0/SE1 after 12 samples (240 ns).
            if (!single_ended) single_ended_clocks <= 0;
            else if (rx_sync[1:0] != rx_history) single_ended_clocks <= 1;
            else if (single_ended_clocks != SINGLE_ENDED_QUALIFY)
                single_ended_clocks <= single_ended_clocks + 1'b1;
            if (single_ended && rx_sync[1:0] == rx_history &&
                single_ended_clocks >= SINGLE_ENDED_QUALIFY - 1'b1)
                line <= rx_sync[1:0];
            else line <= rx_sync[2] ? K : J;
            previous_line <= line;
            if (line != J) idle_clocks <= 0;
            else if (idle_clocks != 255) idle_clocks <= idle_clocks + 1'b1;
        end
    end

    state_t state;
    reg [9:0] setup_clocks;
    reg expecting_data, data_packet, address_zero;
    reg [6:0] phase, received_bits, se0_clocks;
    reg [2:0] ones;
    reg [1:0] last_symbol;
    reg [7:0] header_byte;
    reg [4:0] crc5;
    reg [15:0] crc16;
    wire bit_in = line == last_symbol;
    wire [7:0] next_byte = {bit_in, header_byte[7:1]};
    wire token_valid = !data_packet && received_bits == 32 && address_zero && crc5 == 5'h06;
    wire data_valid = data_packet && received_bits == 96 && crc16 == 16'hb001;
    reg [6:0] tx_timer;
    reg [4:0] tx_bit;
    reg [1:0] tx_fraction;
    reg driving;
    assign tx_oe_n = reset || !driving;

    always @(posedge clk) begin
        if (reset) begin
            state <= DROP;
            setup_clocks <= 0;
            expecting_data <= 0;
            data_packet <= 0;
            address_zero <= 0;
            phase <= 0;
            received_bits <= 0;
            se0_clocks <= 0;
            ones <= 0;
            last_symbol <= J;
            header_byte <= 0;
            crc5 <= 5'h1f;
            crc16 <= 16'hffff;
            tx_timer <= 0;
            tx_bit <= 0;
            tx_fraction <= 0;
            tx_pins <= J;
            driving <= 0;
        end else begin
            if (setup_clocks != 0) setup_clocks <= setup_clocks - 1'b1;
            case (state)
                DROP: begin
                    setup_clocks <= 0;
                    if (line == J && (previous_line == SE0 || idle_clocks == 255))
                        state <= IDLE;
                end
                IDLE: begin
                    if (line == K && previous_line == J) begin
                        expecting_data <= setup_clocks != 0;
                        setup_clocks <= 0;
                        data_packet <= 0;
                        address_zero <= 1;
                        phase <= 0;
                        received_bits <= 0;
                        ones <= 0;
                        last_symbol <= J;
                        crc5 <= 5'h1f;
                        crc16 <= 16'hffff;
                        state <= RECEIVE;
                    end else if (line == SE0 || line == SE1) setup_clocks <= 0;
                end
                RECEIVE: begin
                    if (line == SE0) begin
                        se0_clocks <= {3'd0, SINGLE_ENDED_QUALIFY};
                        state <= EOP;
                    end else if (line == SE1) state <= DROP;
                    else if (line != previous_line) phase <= 0;
                    else begin
                        // Phase units are 1/100 bit. Increment 3 every core
                        // edge and sample on the crossing at half a bit.
                        if (phase >= 97) phase <= phase - 7'd97;
                        else phase <= phase + 2'd3;
                        if (phase >= 47 && phase < 50 && !single_ended) begin
                            last_symbol <= line;
                            if (ones == 6) begin
                                if (bit_in) state <= DROP;
                                ones <= 0;
                            end else if (received_bits == 96) state <= DROP;
                            else begin
                                received_bits <= received_bits + 1'b1;
                                ones <= bit_in ? ones + 1'b1 : 3'd0;
                                if (received_bits < 16) begin
                                    header_byte <= next_byte;
                                    if (received_bits == 7 && next_byte != 8'h80) state <= DROP;
                                    if (received_bits == 15) begin
                                        data_packet <= next_byte == 8'hc3;
                                        if (next_byte != 8'h2d && !(expecting_data && next_byte == 8'hc3))
                                            state <= DROP;
                                    end
                                end else if (data_packet) begin
                                    crc16 <= (crc16 >> 1) ^ ((crc16[0] ^ bit_in) ? 16'ha001 : 16'd0);
                                end else if (received_bits < 32) begin
                                    crc5 <= (crc5 >> 1) ^ ((crc5[0] ^ bit_in) ? 5'h14 : 5'd0);
                                    if (received_bits < 27 && bit_in) address_zero <= 0;
                                end
                            end
                        end
                    end
                end
                EOP: begin
                    if (line == SE0) begin
                        if (se0_clocks == 90) state <= DROP;
                        else se0_clocks <= se0_clocks + 1'b1;
                    end else if (line == J && se0_clocks >= 40 && ones != 6) begin
                        if (token_valid) setup_clocks <= 600;
                        if (data_valid) begin
                            state <= TURN;
                            tx_timer <= 119;
                        end else state <= IDLE;
                    end else state <= DROP;
                end
                TURN: begin
                    if (line != J) state <= DROP;
                    else if (tx_timer != 0) tx_timer <= tx_timer - 1'b1;
                    else begin
                        state <= TRANSMIT;
                        tx_pins <= K;
                        driving <= 1;
                        tx_bit <= 0;
                        tx_fraction <= 0;
                        tx_timer <= 32;
                    end
                end
                TRANSMIT: begin
                    if (tx_timer != 0) tx_timer <= tx_timer - 1'b1;
                    else if (tx_bit == 18) begin
                        driving <= 0;
                        state <= IDLE;
                    end else begin
                        tx_bit <= tx_bit + 1'b1;
                        tx_timer <= tx_fraction == 1 ? 7'd33 : 7'd32;
                        tx_fraction <= tx_fraction == 2 ? 2'd0 : tx_fraction + 1'b1;
                        if (tx_bit < 15) begin
                            if (!ACK[tx_bit[3:0] + 4'd1]) tx_pins <= ~tx_pins;
                        end else if (tx_bit < 17) tx_pins <= SE0;
                        else tx_pins <= J;
                    end
                end
                default: begin state <= DROP; driving <= 0; end
            endcase
        end
    end
endmodule

`default_nettype wire
