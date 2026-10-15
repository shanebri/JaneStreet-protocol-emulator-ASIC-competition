`default_nettype none

// FPGA-only host for the unchanged Tiny Tapeout top. All bus traffic is 50 MHz.
module arty_demo #(
    parameter integer DEBOUNCE_CYCLES = 500000 // 10 ms at 50 MHz
) (
    input  wire clk,
    input  wire reset,
    input  wire button_run,
    output wire uart_tx,
    output wire ready,
    output wire done
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] run_sync;
    reg run_stable, run_pressed;
    localparam integer COUNT_WIDTH = (DEBOUNCE_CYCLES < 2) ? 1 : $clog2(DEBOUNCE_CYCLES);
    reg [COUNT_WIDTH-1:0] debounce_count;
    always @(posedge clk) begin
        if (reset) begin
            run_sync <= 0;
            run_stable <= 0;
            run_pressed <= 0;
            debounce_count <= 0;
        end else begin
            run_sync <= {run_sync[0], button_run};
            run_pressed <= 0;
            if (run_sync[1] == run_stable) debounce_count <= 0;
            else if (debounce_count == DEBOUNCE_CYCLES - 1) begin
                debounce_count <= 0;
                run_stable <= run_sync[1];
                run_pressed <= run_sync[1];
            end else debounce_count <= debounce_count + 1'b1;
        end
    end

    // Same words as examples/uart_v0.hex; default HALT fills unused memory.
    function automatic [15:0] demo_word(input [4:0] index);
        case (index)
            0: demo_word = 16'h80a0;
            1: demo_word = 16'he027;
            2: demo_word = 16'hed00;
            3: demo_word = 16'h6c01;
            4: demo_word = 16'h0043;
            5: demo_word = 16'hed01;
            6: demo_word = 16'he003;
            default: demo_word = 16'hc080;
        endcase
    endfunction

    localparam [3:0] RESET_CORE=0, SET_ADDR=1, ADDR_GAP=2,
        WRITE_LO=3, LO_GAP=4, WRITE_HI=5, HI_GAP=6,
        IDLE=7, START=8, START_GAP=9, CONFIG_WRITE=10, CONFIG_GAP=11;
    reg [3:0] state;
    reg [2:0] reset_count;
    reg [4:0] word_index;
    reg [3:0] config_index;
    reg run_after_load;
    reg [7:0] control, write_data;
    wire [15:0] word_data = demo_word(word_index);
    wire [7:0] outputs;
    wire core_reset_n = !reset && state != RESET_CORE;

    always @* begin
        control = 0;
        write_data = 0;
        case (state)
            SET_ADDR: begin control = 8'h12; write_data = 0; end
            WRITE_LO: begin control = 8'h13; write_data = word_data[7:0]; end
            WRITE_HI: begin control = 8'h14; write_data = word_data[15:8]; end
            START: begin control = 8'h10; write_data = 1; end
            CONFIG_WRITE: begin
                case (config_index)
                    0: begin control = 8'h15; write_data = 8'h13; end // Divider
                    1: begin control = 8'h16; write_data = 31; end
                    2, 7, 12: begin control = 8'h17; write_data = config_index == 7 ? 8'h10 : 0; end
                    3, 8, 13: control = 8'h19;
                    4, 9, 14: control = 8'h1a; // Atomic 32-bit commit
                    5: begin control = 8'h15; write_data = 8'h12; end // Pin mapping
                    6: begin control = 8'h16; write_data = 8'h08; end
                    10: begin control = 8'h15; write_data = 8'h08; end // TX FIFO
                    11: begin control = 8'h16; write_data = 8'h55; end
                    default: ;
                endcase
            end
            default: ;
        endcase
    end
    always @(posedge clk) begin
        if (reset) begin
            state <= RESET_CORE;
            reset_count <= 0;
            word_index <= 0;
            config_index <= 0;
            run_after_load <= 0;
        end else begin
            case (state)
                RESET_CORE: begin
                    if (reset_count == 7) begin
                        reset_count <= 0;
                        word_index <= 0;
                        state <= SET_ADDR;
                    end else reset_count <= reset_count + 1'b1;
                end
                SET_ADDR: state <= ADDR_GAP;
                ADDR_GAP: state <= WRITE_LO;
                WRITE_LO: state <= LO_GAP;
                LO_GAP: state <= WRITE_HI;
                WRITE_HI: state <= HI_GAP;
                HI_GAP: begin
                    if (word_index == 31) begin
                        config_index <= 0;
                        state <= CONFIG_WRITE;
                    end
                    else begin
                        word_index <= word_index + 1'b1;
                        state <= WRITE_LO;
                    end
                end
                CONFIG_WRITE: state <= CONFIG_GAP;
                CONFIG_GAP: begin
                    if (config_index == 14) state <= run_after_load ? START : IDLE;
                    else begin
                        config_index <= config_index + 1'b1;
                        state <= CONFIG_WRITE;
                    end
                end
                IDLE: if (run_pressed) begin
                    // Restart cleanly, clearing the completion LED and any frame.
                    run_after_load <= 1;
                    state <= RESET_CORE;
                end
                START: state <= START_GAP;
                START_GAP: state <= IDLE;
                default: state <= RESET_CORE;
            endcase
        end
    end

    tt_um_shanebri_top emulator (
        .clk(clk), .rst_n(core_reset_n), .ena(1'b1),
        .ui_in(control), .uio_in(write_data), .uo_out(outputs),
        .uio_out(), .uio_oe()
    );
    assign uart_tx = outputs[0];
    assign done = outputs[1];
    assign ready = !reset && state == IDLE;
endmodule

`default_nettype wire
