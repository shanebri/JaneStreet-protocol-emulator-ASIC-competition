`default_nettype none

// Early V0: one 16-bit accumulator, 32 instruction words and eight data words.
module protocol_core (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    input  wire [3:0] host_address,
    input  wire       host_write_en,
    input  wire [7:0] host_write_data,
    output reg  [7:0] host_read_data,
    output reg  [6:0] gpio,
    output wire       uart_tx_pin
);
    localparam [11:0] GPIO_OUT = 12'h010;
    localparam [11:0] UART_DATA = 12'h011;
    localparam [11:0] UART_DIV = 12'h012;
    localparam [11:0] UART_STATUS = 12'h013;

    reg running;
    reg fault;
    reg [15:0] accumulator;
    reg [11:0] wait_left;
    reg [15:0] scratch [0:7];
    reg [7:0] uart_data;
    reg [15:0] uart_divider;
    wire uart_busy;

    reg [4:0] imem_address;
    reg [7:0] imem_low;
    reg [7:0] data_address;
    reg [7:0] data_low;
    wire control_write = host_write_en && host_address == 4'h0;
    wire stop = control_write && host_write_data[1];
    wire start = control_write && host_write_data[0] && !host_write_data[1];
    wire imem_write = host_write_en && host_address == 4'h4 && !running;
    wire host_data_write = host_write_en && host_address == 4'h7 && !running;

    wire [4:0] current_pc;
    wire [15:0] instruction;
    wire [15:0] imem_read_data;
    wire [11:0] immediate;
    wire [2:0] alu_op;
    wire reg_write, mem_read, mem_write, wait_cycles, wait_uart, halt, illegal;
    wire [1:0] branch;
    wire [15:0] alu_result;
    wire uart_stall = uart_busy && (wait_uart || (mem_write && immediate == UART_DATA));
    wire waiting = running && (wait_left != 0 || uart_stall);
    wire execute = enable && running && wait_left == 0 && !uart_stall && !start && !stop;
    wire retire = execute && !illegal && !halt;
    wire take_branch = branch == 2'd1 ||
                       (branch == 2'd2 && accumulator == 0) ||
                       (branch == 2'd3 && accumulator != 0);

    // Host accesses the same data map while stopped; CPU stores own it when running.
    wire cpu_data_write = retire && mem_write;
    wire data_write = cpu_data_write || host_data_write;
    wire [11:0] write_address = cpu_data_write ? immediate : {4'd0, data_address};
    wire [15:0] write_data = cpu_data_write ? accumulator : {host_write_data, data_low};
    wire uart_send = data_write && write_address == UART_DATA && !uart_busy;

    reg [15:0] cpu_read_data;
    reg [15:0] host_data_read;
    // Explicit combinational read ports react to changes at an unchanged address.
    always @* begin
        case (immediate)
            GPIO_OUT: cpu_read_data = {9'd0, gpio};
            UART_DATA: cpu_read_data = {8'd0, uart_data};
            UART_DIV: cpu_read_data = uart_divider;
            UART_STATUS: cpu_read_data = {15'd0, uart_busy};
            default: cpu_read_data = immediate < 8 ? scratch[immediate[2:0]] : 16'd0;
        endcase
        case ({4'd0, data_address})
            GPIO_OUT: host_data_read = {9'd0, gpio};
            UART_DATA: host_data_read = {8'd0, uart_data};
            UART_DIV: host_data_read = uart_divider;
            UART_STATUS: host_data_read = {15'd0, uart_busy};
            default: host_data_read = data_address < 8 ? scratch[data_address[2:0]] : 16'd0;
        endcase
    end

    instruction_fetch fetch (
        .clk(clk), .pc_addr(current_pc), .load_we(imem_write),
        .load_addr(imem_address), .load_data({host_write_data, imem_low}),
        .instr_out(instruction), .host_read_data(imem_read_data)
    );
    pc program_counter (
        .clk(clk), .rst(!rst_n), .restart(start), .advance(retire),
        .branch(take_branch), .target(immediate[4:0]), .pc_out(current_pc)
    );
    decoder decode (
        .instruction(instruction), .immediate(immediate), .alu_op(alu_op),
        .reg_write(reg_write), .mem_read(mem_read), .mem_write(mem_write),
        .branch(branch), .wait_cycles(wait_cycles), .wait_uart(wait_uart),
        .halt(halt), .illegal(illegal)
    );
    execution_unit execution (
        .accumulator(accumulator), .operand(mem_read ? cpu_read_data : {4'd0, immediate}),
        .alu_op(alu_op), .result(alu_result)
    );
    uart_tx transmitter (
        .clk(clk), .rst(!rst_n), .enable(enable), .cancel(start || stop),
        .send(uart_send), .data(write_data[7:0]), .clocks_per_bit(uart_divider),
        .tx(uart_tx_pin), .busy(uart_busy)
    );

    always @* begin
        case (host_address)
            4'h0: host_read_data = 8'd0;
            4'h1: host_read_data = {4'd0, waiting, fault, uart_busy, running};
            4'h2: host_read_data = {3'd0, imem_address};
            4'h3: host_read_data = imem_read_data[7:0];
            4'h4: host_read_data = imem_read_data[15:8];
            4'h5: host_read_data = data_address;
            4'h6: host_read_data = host_data_read[7:0];
            4'h7: host_read_data = host_data_read[15:8];
            4'h8: host_read_data = {3'd0, current_pc};
            4'h9: host_read_data = accumulator[7:0];
            4'ha: host_read_data = accumulator[15:8];
            default: host_read_data = 8'd0;
        endcase
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            imem_address <= 5'd0;
            imem_low <= 8'd0;
            data_address <= 8'd0;
            data_low <= 8'd0;
        end else if (host_write_en) begin
            case (host_address)
                4'h2: imem_address <= host_write_data[4:0];
                4'h3: if (!running) imem_low <= host_write_data;
                4'h4: if (!running) imem_address <= imem_address + 5'd1;
                4'h5: data_address <= host_write_data;
                4'h6: if (!running) data_low <= host_write_data;
                default: ;
            endcase
        end
    end

    integer i;
    always @(posedge clk) begin
        if (!rst_n) begin
            gpio <= 7'd0;
            uart_data <= 8'd0;
            uart_divider <= 16'd434;
            for (i = 0; i < 8; i = i + 1)
                scratch[i] <= 16'd0;
        end else if (data_write) begin
            if (write_address < 12'h008)
                scratch[write_address[2:0]] <= write_data;
            else begin
                case (write_address)
                    GPIO_OUT: gpio <= write_data[6:0];
                    UART_DATA: if (!uart_busy) uart_data <= write_data[7:0];
                    UART_DIV: uart_divider <= write_data == 0 ? 16'd1 : write_data;
                    default: ;
                endcase
            end
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            running <= 1'b0;
            fault <= 1'b0;
            accumulator <= 16'd0;
            wait_left <= 12'd0;
        end else if (stop) begin
            running <= 1'b0;
            wait_left <= 12'd0;
        end else if (start) begin
            running <= 1'b1;
            fault <= 1'b0;
            accumulator <= 16'd0;
            wait_left <= 12'd0;
        end else if (enable && running) begin
            if (wait_left != 0)
                wait_left <= wait_left - 12'd1;
            else if (execute) begin
                if (illegal) begin
                    fault <= 1'b1;
                    running <= 1'b0;
                end else if (halt) begin
                    running <= 1'b0;
                end else begin
                    if (reg_write)
                        accumulator <= alu_result;
                    if (wait_cycles)
                        wait_left <= immediate;
                end
            end
        end
    end
endmodule

`default_nettype wire
