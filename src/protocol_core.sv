`default_nettype none

// One PIO-inspired state machine. There is no protocol-specific serializer.
// All ordinary instructions retire in one SM tick; stalls are explicit.
module protocol_core (
    input wire clk, rst_n, enable,
    input wire [3:0] host_address,
    input wire host_write_en,
    input wire [7:0] host_write_data,
    input wire [5:0] pins_sync,
    input wire [3:0] filtered,
    input wire [5:0] control_command,
    input wire word_write, snapshot_read, imem_write,
    input wire [31:0] write_word,
    input wire [7:0] data_address,
    input wire [4:0] imem_address,
    input wire [15:0] imem_write_data,
    output wire [15:0] imem_read_data,
    output reg [31:0] selected_data,
    output wire [7:0] status, irq_flags,
    output reg running,
    output reg [7:0] host_read_data,
    output reg [11:0] pins,
    output reg [3:0] directions, open_drain
);
    reg fault;
    reg [31:0] x, y, osr, isr;
    reg [5:0] out_count, in_count;
    reg [4:0] delay_left;
    reg [15:0] divider, divider_left;
    reg [13:0] shiftctrl;
    reg [15:0] execctrl;
    reg [20:0] pinctrl;
    reg [27:0] route;
    reg [3:0] filter_enable;
    wire [5:0] inputs_actual = {((filtered & filter_enable) |
        (pins_sync[5:2] & ~filter_enable)), pins_sync[1:0]};
    wire [2:0] input_base = route[0] ? route[19:17] : {2'b0, pinctrl[16]};
    wire [2:0] jump_pin = route[0] ? route[26:24] : {2'b0, pinctrl[20]};
    wire [3:0] side_pin = route[0] ? route[23:20] : {1'b0, pinctrl[19:17]};
    reg [7:0] irq;
    reg irq_waiting;
    reg [3:0] debug_flags;
    reg exec_pending;
    reg [15:0] exec_instruction;
    wire abort_release = control_command[5];
    wire stop = control_command[1] || abort_release;
    wire start = control_command[0] && !stop;
    wire resume = control_command[4] && !stop && !start && !fault;
    wire fifo_clear = control_command[2] && (!running || stop);
    wire clear_errors = control_command[3];
    wire config_write = word_write && !running;

    wire [4:0] current_pc;
    wire [15:0] fetched_instruction;
    wire [15:0] instruction = exec_pending ? exec_instruction : fetched_instruction;
    wire [2:0] opcode;
    wire [7:0] arg;
    wire [4:0] instruction_delay;
    wire [5:0] bit_count;
    wire side_write, side_value, illegal;
    wire halt = opcode == 6 && arg == 8'h80;
    wire sm_tick = enable && running && divider_left == 0 && !start && !stop;
    wire attempt = sm_tick && delay_left == 0;
    reg stall, branch;
    reg [4:0] branch_target;
    wire retire = attempt && !stall && !illegal && !halt;

    instruction_fetch fetch (
        .clk(clk), .pc_addr(current_pc),
        // IMEM has no reset branch: unlike architectural state/FIFO storage,
        // it must reject reset-edge intent explicitly to retain firmware.
        .load_we(imem_write && rst_n),
        .load_addr(imem_address), .load_data(imem_write_data),
        .instr_out(fetched_instruction), .host_read_data(imem_read_data)
    );
    pc program_counter (
        .clk(clk), .rst(!rst_n), .restart(start), .entry(execctrl[14:10]),
        .advance(retire && (!exec_pending || branch)), .branch(branch),
        .target(branch_target), .wrap_bottom(execctrl[4:0]),
        .wrap_top(execctrl[9:5]), .pc_out(current_pc)
    );
    decoder decode (
        .instruction(instruction), .sideset_enable(execctrl[15]),
        .opcode(opcode), .argument(arg), .delay_cycles(instruction_delay),
        .side_write(side_write), .side_value(side_value),
        .bit_count(bit_count), .illegal(illegal)
    );

    wire [5:0] pull_threshold = shiftctrl[8:4] == 0 ? 6'd32 : {1'b0, shiftctrl[8:4]};
    wire [5:0] push_threshold = shiftctrl[13:9] == 0 ? 6'd32 : {1'b0, shiftctrl[13:9]};
    wire osr_empty = out_count >= pull_threshold;
    wire [31:0] tx_data, rx_data;
    wire tx_full, tx_empty, rx_full, rx_empty;
    wire [2:0] tx_level, rx_level;
    wire host_tx_push = word_write && data_address == 8;
    wire host_rx_pop = snapshot_read && data_address == 9;
    reg tx_pop_request, rx_push_request;
    reg [31:0] rx_push_data;
    wire tx_pop = retire && tx_pop_request;
    wire rx_push = retire && rx_push_request;
    wire rx_room = !rx_full || (host_rx_pop && !rx_empty);
    pio_fifo tx_fifo (
        .clk(clk), .rst(!rst_n), .clear(fifo_clear),
        .push(host_tx_push), .pop(tx_pop), .write_data(write_word),
        .read_data(tx_data), .full(tx_full), .empty(tx_empty), .level(tx_level)
    );
    pio_fifo rx_fifo (
        .clk(clk), .rst(!rst_n), .clear(fifo_clear),
        .push(rx_push), .pop(host_rx_pop), .write_data(rx_push_data),
        .read_data(rx_data), .full(rx_full), .empty(rx_empty), .level(rx_level)
    );

    wire auto_pull = shiftctrl[2] && osr_empty;
    wire [31:0] out_osr = auto_pull ? tx_data : osr;
    wire [31:0] input_pins = {26'd0, inputs_actual} >> input_base;
    reg [31:0] source;
    always @* begin
        case (opcode == 5 ? arg[2:0] : arg[7:5])
            0: source = input_pins;
            1: source = x;
            2: source = y;
            3: source = 0;
            5: source = {24'd0, 1'b0, rx_level, 1'b0, tx_level};
            6: source = isr;
            7: source = osr;
            default: source = 0;
        endcase
    end
    wire [31:0] out_value, shifted_osr, shifted_isr;
    execution_unit shifts (
        .osr(out_osr), .isr(isr), .source(source), .count(bit_count),
        .out_right(shiftctrl[0]), .in_right(shiftctrl[1]),
        .out_value(out_value), .shifted_osr(shifted_osr), .shifted_isr(shifted_isr)
    );
    function automatic [5:0] count_add(input [5:0] old_count, amount);
        reg [6:0] sum;
        begin
            sum = {1'b0, old_count} + {1'b0, amount};
            count_add = sum >= 32 ? 6'd32 : sum[5:0];
        end
    endfunction
    wire [5:0] next_in_count = count_add(in_count, bit_count);
    reg [31:0] mov_value;
    integer b;
    always @* begin
        mov_value = source;
        if (arg[4:3] == 1) mov_value = ~source;
        for (b = 0; b < 32; b = b + 1)
            if (arg[4:3] == 2) mov_value[b] = source[31-b];
    end

    reg [31:0] next_x, next_y, next_osr, next_isr;
    reg [5:0] next_out_count, next_in;
    reg pin_write, dir_write, inject;
    reg [31:0] pin_value;
    reg [15:0] injected_word;
    reg [7:0] irq_set, irq_clear;
    reg wait_value;
    wire irq_wait_instruction = opcode == 6 && !arg[7] && arg[5] && !arg[6];
    always @* begin
        next_x = x; next_y = y; next_osr = osr; next_isr = isr;
        next_out_count = out_count; next_in = in_count;
        stall = 0; branch = 0; branch_target = arg[4:0];
        tx_pop_request = 0; rx_push_request = 0; rx_push_data = isr;
        pin_write = 0; dir_write = 0; pin_value = 0; inject = 0; injected_word = 0;
        irq_set = 0; irq_clear = 0; wait_value = 0;
        case (opcode)
            0: begin
                case (arg[7:5])
                    0: branch = 1;
                    1: branch = x == 0;
                    2: begin branch = x != 0; next_x = x - 1'b1; end
                    3: branch = y == 0;
                    4: begin branch = y != 0; next_y = y - 1'b1; end
                    5: branch = x != y;
                    6: branch = jump_pin < 6 ? inputs_actual[jump_pin] : 1'b0;
                    7: branch = !osr_empty;
                endcase
            end
            1: begin
                case (arg[6:5])
                    0: wait_value = arg[4:0] < 6 ? inputs_actual[arg[4:0]] : 1'b0;
                    1: wait_value = input_pins[arg[4:0]];
                    2: wait_value = irq[arg[2:0]];
                    default: wait_value = 0;
                endcase
                stall = wait_value != arg[7];
                if (arg[6:5] == 2 && arg[7]) irq_clear[arg[2:0]] = 1;
            end
            2: begin
                next_isr = shifted_isr;
                next_in = next_in_count;
                if (shiftctrl[3] && next_in_count >= push_threshold) begin
                    stall = !rx_room;
                    rx_push_request = 1; rx_push_data = shifted_isr;
                    next_isr = 0; next_in = 0;
                end
            end
            3: begin
                stall = auto_pull && tx_empty;
                tx_pop_request = auto_pull;
                next_osr = shifted_osr;
                next_out_count = count_add(auto_pull ? 6'd0 : out_count, bit_count);
                case (arg[7:5])
                    0: begin pin_write = 1; pin_value = out_value; end
                    4: begin dir_write = 1; pin_value = out_value; end
                    1: next_x = out_value;
                    2: next_y = out_value;
                    5: begin branch = 1; branch_target = out_value[4:0]; end
                    6: begin next_isr = out_value; next_in = bit_count; end
                    7: begin inject = 1; injected_word = out_value[15:0]; end
                    default: ;
                endcase
            end
            4: begin
                if (arg[7]) begin // PULL: conditional on OSR empty, block or X fallback.
                    if (!arg[6] || osr_empty) begin
                        stall = arg[5] && tx_empty;
                        tx_pop_request = !tx_empty;
                        next_osr = tx_empty ? x : tx_data;
                        next_out_count = 0;
                    end
                end else if (!arg[6] || in_count >= push_threshold) begin
                    stall = arg[5] && !rx_room;
                    rx_push_request = rx_room;
                    next_isr = 0; next_in = 0;
                end
            end
            5: begin
                case (arg[7:5])
                    0: begin pin_write = 1; pin_value = mov_value; end
                    1: next_x = mov_value;
                    2: next_y = mov_value;
                    4: begin inject = 1; injected_word = mov_value[15:0]; end
                    5: begin branch = 1; branch_target = mov_value[4:0]; end
                    6: begin next_isr = mov_value; next_in = 0; end
                    7: begin next_osr = mov_value; next_out_count = 0; end
                    default: ;
                endcase
            end
            6: if (!arg[7]) begin
                if (arg[6]) irq_clear[arg[2:0]] = 1;
                else if (arg[5]) stall = !irq_waiting || irq[arg[2:0]];
                else irq_set[arg[2:0]] = 1;
            end
            7: begin
                case (arg[7:5])
                    0: begin pin_write = 1; pin_value = {27'd0, arg[4:0]}; end
                    4: begin dir_write = 1; pin_value = {27'd0, arg[4:0]}; end
                    1: next_x = {27'd0, arg[4:0]};
                    2: next_y = {27'd0, arg[4:0]};
                    default: ;
                endcase
            end
        endcase
    end

    wire [3:0] pin_base = route[0] ? (opcode == 7 ? route[12:9] : route[4:1]) :
        {1'b0, (opcode == 7 ? pinctrl[10:8] : pinctrl[2:0])};
    wire [3:0] configured_count = route[0] ? (opcode == 7 ? route[16:13] : route[8:5]) :
        (opcode == 7 ? pinctrl[14:11] : pinctrl[6:3]);
    wire [3:0] capacity = route[0] ? 4'd12 : 4'd8;
    wire [3:0] pin_count = configured_count == 0 || configured_count > capacity ? capacity : configured_count;
    wire [11:0] pin_mask = ((12'hfff >> (4'd12 - pin_count)) << pin_base) &
        (route[0] ? 12'hfff : 12'h0ff);
    wire [11:0] aligned_pins = pin_value[11:0] << pin_base;
    wire [11:0] mapped_pins = (pins & ~pin_mask) | (aligned_pins & pin_mask);
    wire [3:0] mapped_dirs = (directions & ~pin_mask[11:8]) | (aligned_pins[11:8] & pin_mask[11:8]);

    always @* begin
        case (data_address)
            0: selected_data = x;
            1: selected_data = y;
            2: selected_data = osr;
            3: selected_data = isr;
            4: selected_data = {20'd0, pins};
            5: selected_data = {18'd0, in_count, 2'b0, out_count};
            9: selected_data = rx_data;
            8'h10: selected_data = {18'd0, shiftctrl};
            8'h11: selected_data = {16'd0, execctrl};
            8'h12: selected_data = {11'd0, pinctrl};
            8'h13: selected_data = {16'd0, divider};
            8'h14: selected_data = {24'd0, irq};
            8'h15: selected_data = {24'd0, 1'b0, rx_level, 1'b0, tx_level};
            8'h16: selected_data = {4'd0, route};
            8'h17: selected_data = {20'd0, directions, 8'hff};
            8'h18: selected_data = {20'd0, open_drain, 8'd0};
            8'h19: selected_data = {28'd0, filter_enable};
            default: selected_data = 0;
        endcase
        host_read_data = 0;
        case (host_address)
            1: host_read_data = status;
            8: host_read_data = {3'd0, current_pc};
            11: host_read_data = {1'b0, rx_level, 1'b0, tx_level};
            12: host_read_data = irq;
            13: host_read_data = {4'd0, debug_flags};
            14: host_read_data = {2'd0, inputs_actual};
            default: ;
        endcase
    end
    assign status = {debug_flags[1:0], |irq, rx_empty, tx_full, fault,
                     running && (delay_left != 0 || stall), running};
    assign irq_flags = irq;

    always @(posedge clk) begin
        if (!rst_n) begin
            running <= 0; fault <= 0;
            x <= 0; y <= 0; osr <= 0; isr <= 0;
            out_count <= 32; in_count <= 0;
            delay_left <= 0; divider <= 1; divider_left <= 0;
            shiftctrl <= 14'h0003; execctrl <= 16'h03e0; pinctrl <= 0;
            pins <= 12'hf01; directions <= 0; open_drain <= 0; route <= 0; filter_enable <= 0; irq <= 0; irq_waiting <= 0;
            debug_flags <= 0; exec_pending <= 0; exec_instruction <= 0;
        end else begin
            // Host IRQ clears are live; firmware sets win simultaneous clears.
            if (host_write_en && host_address == 12) irq <= irq & ~host_write_data;
            if (word_write && data_address == 8'h14) irq <= irq | write_word[7:0];
            if (clear_errors) debug_flags <= 0;
            if (host_write_en && host_address == 13) debug_flags <= debug_flags & ~host_write_data[3:0];
            if (!fifo_clear) begin
                if (host_tx_push && tx_full && !tx_pop) debug_flags[0] <= 1;
                if (host_rx_pop && rx_empty) debug_flags[1] <= 1;
                if (retire && opcode == 4 && !arg[7] && !arg[5] &&
                    (!arg[6] || in_count >= push_threshold) && !rx_room) debug_flags[2] <= 1;
                if (retire && opcode == 4 && arg[7] && !arg[5] &&
                    (!arg[6] || osr_empty) && tx_empty) debug_flags[3] <= 1;
            end
            if (config_write) begin
                case (data_address)
                    0: x <= write_word;
                    1: y <= write_word;
                    2: begin osr <= write_word; out_count <= 0; end
                    3: begin isr <= write_word; in_count <= 0; end
                    4: pins <= write_word[11:0];
                    8'h16: route <= write_word[27:0];
                    8'h17: directions <= write_word[11:8];
                    8'h18: open_drain <= write_word[11:8];
                    8'h19: filter_enable <= write_word[3:0];
                    8'h10: shiftctrl <= write_word[13:0];
                    8'h11: execctrl <= write_word[15:0];
                    8'h12: pinctrl <= write_word[20:0] & 21'h1f7f7f;
                    8'h13: divider <= write_word[15:0] == 0 ? 16'd1 : write_word[15:0];
                    default: ;
                endcase
            end
            if (abort_release) begin running <= 0; directions <= 0; end
            else if (stop) running <= 0; // Freeze exact state; outputs retain firmware levels.
            else if (start) begin
                running <= 1; fault <= 0;
                x <= 0; y <= 0; osr <= 0; isr <= 0;
                out_count <= 32; in_count <= 0;
                delay_left <= 0; divider_left <= 0;
                exec_pending <= 0; irq_waiting <= 0;
            end else if (resume) running <= 1;
            else if (enable && running) begin
                if (divider_left != 0) divider_left <= divider_left - 1'b1;
                else begin
                    divider_left <= divider - 1'b1;
                    if (delay_left != 0) delay_left <= delay_left - 1'b1;
                    else if (illegal) begin fault <= 1; running <= 0; end
                    else begin
                        if (retire) begin
                            x <= next_x; y <= next_y; osr <= next_osr; isr <= next_isr;
                            out_count <= next_out_count; in_count <= next_in;
                            delay_left <= instruction_delay;
                            exec_pending <= inject;
                            if (inject) exec_instruction <= injected_word;
                            if (pin_write) pins <= mapped_pins;
                            if (dir_write) directions <= mapped_dirs;
                            if (|irq_set || |irq_clear)
                                irq <= ((irq & ~(host_write_en && host_address == 12 ? host_write_data : 8'd0)) |
                                    (word_write && data_address == 8'h14 ? write_word[7:0] : 8'd0) | irq_set) & ~irq_clear;
                            irq_waiting <= 0;
                        end
                        if (halt) running <= 0;
                        if (irq_wait_instruction && !irq_waiting) begin
                            irq[arg[2:0]] <= 1;
                            irq_waiting <= 1;
                        end
                        // Side-set occurs even on a blocked instruction and wins pin overlap.
                        if (side_write && side_pin < 12) begin
                            if (route[27]) begin
                                if (side_pin >= 8) directions[side_pin - 4'd8] <= side_value;
                            end else pins[side_pin] <= side_value;
                        end
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
