`default_nettype none

// FPGA-only test host. Loads the unmodified ASIC through its real byte bus.
// One BTN1 press tests TX=0..255, expecting RX=(TX xor A5) from the Nano.
module arty_spi_test_host #(
    parameter integer SPI_DIVIDER = 32, // 50 MHz / (16*32) = 97.65625 kHz
    parameter integer DEBOUNCE_CYCLES = 500000,
    parameter integer TIMEOUT_CYCLES = 100000000, // 2 seconds at 50 MHz
    parameter integer UART_BIT_CYCLES = 434
) (
    input wire clk, reset, button_run, slave_ready, miso,
    output wire mosi, sclk, cs_n, uart_tx,
    output wire ready, passed,
    output reg failed,
    output reg finished
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] run_sync, ready_sync;
    reg run_stable, run_pressed;
    reg [31:0] debounce_count;
    always @(posedge clk) begin
        if (reset) begin
            run_sync <= 0; ready_sync <= 0; run_stable <= 0;
            run_pressed <= 0; debounce_count <= 0;
        end else begin
            run_sync <= {run_sync[0], button_run};
            ready_sync <= {ready_sync[0], slave_ready};
            run_pressed <= 0;
            if (run_sync[1] == run_stable) debounce_count <= 0;
            else if (debounce_count == DEBOUNCE_CYCLES - 1) begin
                debounce_count <= 0;
                run_stable <= run_sync[1];
                run_pressed <= run_sync[1];
            end else debounce_count <= debounce_count + 1'b1;
        end
    end

    // Canonical examples/spi_mode0.hex; the simulation checks all ten words.
    function automatic [15:0] program_word(input [4:0] index);
        case (index)
            0: program_word = 16'h90a0;
            1: program_word = 16'hb0c3;
            2: program_word = 16'hf027;
            3: program_word = 16'hf300;
            4: program_word = 16'h7301;
            5: program_word = 16'h5f01;
            6: program_word = 16'h1344;
            7: program_word = 16'hf001;
            8: program_word = 16'h9020;
            9: program_word = 16'hd080;
            default: program_word = 16'hc080;
        endcase
    endfunction
    function automatic [7:0] config_selector(input integer index);
        case (index)
            0: config_selector = 4;
            1: config_selector = 8'h10;
            2: config_selector = 8'h11;
            3: config_selector = 8'h12;
            default: config_selector = 8'h13;
        endcase
    endfunction
    function automatic [31:0] config_word(input integer index);
        case (index)
            0: config_word = 4;
            1: config_word = 0;
            2: config_word = 32'h83e0;
            3: config_word = 32'h20a08;
            default: config_word = SPI_DIVIDER;
        endcase
    endfunction
    function automatic [3:0] byte_address(input integer index);
        case (index)
            0: byte_address = 6;
            1: byte_address = 7;
            2: byte_address = 9;
            default: byte_address = 10;
        endcase
    endfunction

    localparam [4:0] BOOT_WRITE=0, BOOT_GAP=1, IDLE=2, WAIT_READY=3,
        TX_WRITE=4, TX_GAP=5, GO=6, GO_GAP=7, POLL=8, POLL_SAMPLE=9,
        POLL_GAP=10, RX_SELECT=11, RX_SEL_GAP=12, RX_READ=13, RX_SAMPLE=14,
        REPORT_START=15, REPORT_WAIT=16, WAIT_LOW=17, COMPLETE=18, ABORT=19;
    reg [4:0] state;
    reg [6:0] boot_index;
    reg [2:0] tx_index, report_index;
    reg [7:0] sequence_number, received, result_code;
    reg [31:0] timeout_count;
    reg booted, saw_ready_low, watch_ready, aborted;
    reg [5:0] control;
    reg [7:0] write_data;
    wire [7:0] core_pins, read_data;
    wire uart_busy;
    wire [7:0] expected = sequence_number ^ 8'ha5;
    reg [7:0] report_data;
    integer config_number, config_byte;
    reg [15:0] instruction_word;

    always @* begin
        control = 0; write_data = 0;
        config_number = 0; config_byte = 0; instruction_word = 0;
        case (state)
            BOOT_WRITE: begin
                if (boot_index == 0) control = 6'h12;
                else if (boot_index < 65) begin
                    instruction_word = program_word((boot_index - 1) >> 1);
                    control = boot_index[0] ? 6'h13 : 6'h14;
                    write_data = boot_index[0] ? instruction_word[7:0] : instruction_word[15:8];
                end else begin
                    config_number = (boot_index - 65) / 5;
                    config_byte = (boot_index - 65) % 5;
                    if (config_byte == 0) begin
                        control = 6'h15;
                        write_data = config_selector(config_number);
                    end else begin
                        control = 6'h10 | byte_address(config_byte - 1);
                        write_data = config_word(config_number) >> (8 * (config_byte - 1));
                    end
                end
            end
            TX_WRITE: begin
                if (tx_index == 0) begin control = 6'h15; write_data = 8; end
                else begin
                    control = 6'h10 | byte_address(tx_index - 1);
                    write_data = tx_index == 4 ? sequence_number : 0;
                end
            end
            GO: begin control = 6'h10; write_data = 1; end
            POLL: control = 6'h21;
            RX_SELECT: begin control = 6'h15; write_data = 9; end
            RX_READ: control = 6'h26;
            ABORT: begin control = 6'h10; write_data = 2; end
            default: ;
        endcase
        // A5 5A sequence transmitted received result XOR(first six bytes).
        case (report_index)
            0: report_data = 8'ha5;
            1: report_data = 8'h5a;
            2, 3: report_data = sequence_number;
            4: report_data = received;
            5: report_data = result_code;
            default: report_data = 8'hff ^ received ^ result_code;
        endcase
    end

    always @(posedge clk) begin
        if (reset) begin
            state <= BOOT_WRITE; boot_index <= 0; booted <= 0;
            tx_index <= 0; report_index <= 0; sequence_number <= 0;
            received <= 0; result_code <= 0; timeout_count <= 0;
            failed <= 0; finished <= 0; aborted <= 0;
            saw_ready_low <= 0; watch_ready <= 0;
        end else begin
            if (watch_ready && !ready_sync[1]) saw_ready_low <= 1;
            case (state)
                BOOT_WRITE: state <= BOOT_GAP;
                BOOT_GAP: begin
                    if (boot_index == 89) begin booted <= 1; state <= IDLE; end
                    else begin boot_index <= boot_index + 1'b1; state <= BOOT_WRITE; end
                end
                IDLE: if (run_pressed) begin timeout_count <= 0; state <= WAIT_READY; end
                WAIT_READY: begin
                    if (ready_sync[1]) begin
                        tx_index <= 0; saw_ready_low <= 0; watch_ready <= 1;
                        received <= 0; result_code <= 0; state <= TX_WRITE;
                    end else if (timeout_count == TIMEOUT_CYCLES - 1) begin
                        result_code <= 4; received <= 0; failed <= 1; state <= ABORT;
                    end else timeout_count <= timeout_count + 1'b1;
                end
                TX_WRITE: state <= TX_GAP;
                TX_GAP: begin
                    if (tx_index == 4) state <= GO;
                    else begin tx_index <= tx_index + 1'b1; state <= TX_WRITE; end
                end
                GO: begin timeout_count <= 0; state <= GO_GAP; end
                GO_GAP: state <= POLL;
                POLL: state <= POLL_SAMPLE;
                POLL_SAMPLE: begin
                    if (read_data[2]) begin result_code <= 2; failed <= 1; state <= ABORT; end
                    else if (!read_data[0]) begin
                        if (read_data[4]) begin result_code <= 2; failed <= 1; state <= ABORT; end
                        else state <= RX_SELECT;
                    end else if (timeout_count >= TIMEOUT_CYCLES - 3) begin
                        result_code <= 3; failed <= 1; state <= ABORT;
                    end else begin timeout_count <= timeout_count + 3; state <= POLL_GAP; end
                end
                POLL_GAP: state <= POLL;
                RX_SELECT: state <= RX_SEL_GAP;
                RX_SEL_GAP: state <= RX_READ;
                RX_READ: state <= RX_SAMPLE;
                RX_SAMPLE: begin
                    received <= read_data;
                    result_code <= read_data == expected ? 0 : 1;
                    if (read_data != expected) failed <= 1;
                    report_index <= 0; state <= REPORT_START;
                end
                ABORT: begin
                    aborted <= 1; report_index <= 0; watch_ready <= 0;
                    state <= REPORT_START;
                end
                REPORT_START: if (!uart_busy) state <= REPORT_WAIT;
                REPORT_WAIT: if (!uart_busy) begin
                    if (report_index != 6) begin
                        report_index <= report_index + 1'b1; state <= REPORT_START;
                    end else if (aborted || sequence_number == 255) begin
                        finished <= 1; watch_ready <= 0; state <= COMPLETE;
                    end else begin timeout_count <= 0; state <= WAIT_LOW; end
                end
                WAIT_LOW: begin
                    if (saw_ready_low) begin
                        sequence_number <= sequence_number + 1'b1;
                        watch_ready <= 0; timeout_count <= 0; state <= WAIT_READY;
                    end else if (timeout_count == TIMEOUT_CYCLES - 1) begin
                        // Duplicate sequence with an error report makes a missed handshake explicit.
                        result_code <= 4; failed <= 1; state <= ABORT;
                    end else timeout_count <= timeout_count + 1'b1;
                end
                COMPLETE: ; // Reset both test endpoints before running again.
                default: begin failed <= 1; result_code <= 2; state <= ABORT; end
            endcase
        end
    end
    tt_um_shanebri_top emulator (
        .clk(clk), .rst_n(!reset), .ena(1'b1),
        .ui_in({1'b0, miso, control}), .uio_in(write_data),
        .uo_out(core_pins), .uio_out(read_data), .uio_oe()
    );
    spi_test_uart_tx #(.BIT_CYCLES(UART_BIT_CYCLES)) reporter (
        .clk(clk), .reset(reset), .start(state == REPORT_START && !uart_busy),
        .data(report_data), .tx(uart_tx), .busy(uart_busy)
    );
    // Prevent reset/loading artifacts from selecting or clocking the slave.
    assign cs_n = !booted || aborted || reset ? 1'b1 : core_pins[2];
    assign sclk = !booted || aborted || reset ? 1'b0 : core_pins[1];
    assign mosi = booted && !reset ? core_pins[0] : 1'b0;
    assign ready = booted && state == IDLE;
    assign passed = finished && !failed;
endmodule
`default_nettype wire
