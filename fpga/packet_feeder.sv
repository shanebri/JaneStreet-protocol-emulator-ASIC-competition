`default_nettype none

// Single-clock, single-slot USB symbol TX prototype. The caller configures
// engine 0 before launch and gives this block exclusive host-bus ownership
// while slot_state is ACTIVE. Connect to byte_nibble_host without a new bus map.
module packet_feeder (
    input wire clk, reset,
    input wire cmd_valid,
    input wire [2:0] cmd,
    input wire [31:0] cmd_data,
    input wire [15:0] cmd_length_minus_one,
    output reg cmd_ready,
    output reg [2:0] slot_state,
    output reg [31:0] completion_sequence,
    output reg [1:0] result,
    output reg [5:0] words_sent,
    output reg [7:0] terminal_status, terminal_levels, terminal_errors,
    output reg [5:0] bus_request,
    output reg [7:0] bus_write_data,
    input wire [7:0] bus_read_data,
    input wire bus_done
);
    localparam [2:0] FREE = 0, HOST_FILL = 1, READY = 2, ACTIVE = 3, COMPLETE = 4;
    localparam [2:0] BEGIN_UPLOAD = 0, UPLOAD_WORD = 1, COMMIT = 2,
                     LAUNCH = 3, ABORT = 4, RELEASE = 5;
    localparam [1:0] OK = 0, ABORTED = 1, ENGINE_ERROR = 2;
    localparam [5:0] READ = 6'h20, WRITE = 6'h10;

    typedef enum logic [3:0] {
        SELECT_ENGINE, CLEAR_ENGINE, SELECT_TX, CHECK_LEVEL, WRITE_TX,
        START_ENGINE, CHECK_STATUS, READ_LEVELS, READ_ERRORS, CLEANUP, FINISH
    } step_t;
    step_t step;

    // The generated PIO header plus 29 payload words occupy at most 120 bytes.
    reg [31:0] payload [0:28];
    reg [6:0] length_minus_one;
    reg [5:0] payload_words, uploaded;
    reg [1:0] byte_index;
    reg started, abort_pending;
    wire all_sent = words_sent == payload_words + 6'd1;
    wire [31:0] tx_word = words_sent == 0 ? {25'b0, length_minus_one} :
                          payload[words_sent[4:0] - 5'd1];
    wire command_fire = cmd_valid && cmd_ready;

    always @* begin
        cmd_ready = 0;
        if (!reset) case (cmd)
            BEGIN_UPLOAD: cmd_ready = slot_state == FREE && cmd_length_minus_one < 16'd116;
            UPLOAD_WORD: cmd_ready = slot_state == HOST_FILL && uploaded < payload_words;
            COMMIT: cmd_ready = slot_state == HOST_FILL && uploaded == payload_words;
            LAUNCH: cmd_ready = slot_state == READY;
            ABORT: cmd_ready = slot_state == HOST_FILL || slot_state == READY ||
                               (slot_state == ACTIVE && !abort_pending && step != CLEANUP && step != FINISH);
            RELEASE: cmd_ready = slot_state == COMPLETE;
            default: cmd_ready = 0;
        endcase
    end

    reg [5:0] next_request;
    reg [7:0] next_data;
    always @* begin
        next_data = 0;
        case (step)
            SELECT_ENGINE: next_request = WRITE | 6'h0f;
            CLEAR_ENGINE: begin next_request = WRITE; next_data = 8'h0e; end
            SELECT_TX: begin next_request = WRITE | 6'h05; next_data = 8'h08; end
            CHECK_LEVEL, READ_LEVELS: next_request = READ | 6'h0b;
            WRITE_TX: begin
                case (byte_index)
                    0: next_request = WRITE | 6'h06;
                    1: next_request = WRITE | 6'h07;
                    2: next_request = WRITE | 6'h09;
                    3: next_request = WRITE | 6'h0a;
                endcase
                next_data = tx_word[byte_index * 8 +: 8];
            end
            START_ENGINE: begin next_request = WRITE; next_data = 8'h01; end
            CHECK_STATUS: next_request = READ | 6'h01;
            READ_ERRORS: next_request = READ | 6'h0d;
            CLEANUP: begin next_request = WRITE; next_data = 8'h24; end
            default: next_request = 0;
        endcase
    end

    always @(posedge clk) begin
        if (reset) begin
            slot_state <= FREE;
            completion_sequence <= 0;
            result <= OK;
            words_sent <= 0;
            terminal_status <= 0;
            terminal_levels <= 0;
            terminal_errors <= 0;
            length_minus_one <= 0;
            payload_words <= 0;
            uploaded <= 0;
            byte_index <= 0;
            started <= 0;
            abort_pending <= 0;
            step <= SELECT_ENGINE;
            bus_request <= 0;
            bus_write_data <= 0;
        end else begin
            if (command_fire) case (cmd)
                BEGIN_UPLOAD: begin
                    slot_state <= HOST_FILL;
                    completion_sequence <= cmd_data;
                    length_minus_one <= cmd_length_minus_one[6:0];
                    payload_words <= {1'b0, cmd_length_minus_one[6:2]} + 6'd1;
                    uploaded <= 0;
                end
                UPLOAD_WORD: begin
                    payload[uploaded[4:0]] <= cmd_data;
                    uploaded <= uploaded + 1'b1;
                end
                COMMIT: slot_state <= READY;
                LAUNCH: begin
                    slot_state <= ACTIVE;
                    step <= SELECT_ENGINE;
                    started <= 0;
                    words_sent <= 0;
                    result <= OK;
                    terminal_status <= 0;
                    terminal_levels <= 0;
                    terminal_errors <= 0;
                end
                ABORT: begin
                    if (slot_state == ACTIVE) abort_pending <= 1;
                    else slot_state <= FREE;
                end
                RELEASE: slot_state <= FREE;
                default: ;
            endcase

            if (slot_state == ACTIVE) begin
                if (bus_request != 0 && bus_done) begin
                    bus_request <= 0;
                    case (step)
                        SELECT_ENGINE: step <= CLEAR_ENGINE;
                        CLEAR_ENGINE: step <= SELECT_TX;
                        SELECT_TX: step <= CHECK_LEVEL;
                        CHECK_LEVEL: begin
                            if (bus_read_data[2:0] < 4) begin
                                step <= WRITE_TX;
                                byte_index <= 0;
                            end else if (started) step <= CHECK_STATUS;
                            else step <= START_ENGINE;
                        end
                        WRITE_TX: begin
                            if (byte_index == 3) begin
                                words_sent <= words_sent + 1'b1;
                                if (words_sent == payload_words) begin
                                    if (started) step <= CHECK_STATUS;
                                    else step <= START_ENGINE;
                                end else step <= CHECK_LEVEL;
                            end else byte_index <= byte_index + 1'b1;
                        end
                        START_ENGINE: begin
                            started <= 1;
                            if (all_sent) step <= CHECK_STATUS;
                            else step <= CHECK_LEVEL;
                        end
                        CHECK_STATUS: begin
                            terminal_status <= bus_read_data;
                            if (!bus_read_data[0] || bus_read_data[2]) step <= READ_LEVELS;
                            else if (!all_sent) step <= CHECK_LEVEL;
                        end
                        READ_LEVELS: begin
                            terminal_levels <= bus_read_data;
                            step <= READ_ERRORS;
                        end
                        READ_ERRORS: begin
                            terminal_errors <= bus_read_data;
                            if (!all_sent || terminal_status[2] || terminal_levels != 0 || bus_read_data != 0) begin
                                result <= ENGINE_ERROR;
                                step <= CLEANUP;
                            end else step <= FINISH;
                        end
                        CLEANUP: step <= FINISH;
                        default: ;
                    endcase
                end else if (bus_request == 0 && !bus_done) begin
                    // Wait for an issued byte to retire and the adapter to re-arm.
                    // Selection must retire even if ABORT immediately follows LAUNCH.
                    if (step != SELECT_ENGINE && (abort_pending || (command_fire && cmd == ABORT))) begin
                        abort_pending <= 0;
                        result <= ABORTED;
                        step <= CLEANUP;
                    end else if (step == FINISH) slot_state <= COMPLETE;
                    else begin
                        bus_request <= next_request;
                        bus_write_data <= next_data;
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
