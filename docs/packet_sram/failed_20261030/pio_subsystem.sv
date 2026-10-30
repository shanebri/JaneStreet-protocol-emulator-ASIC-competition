`default_nettype none
// Two independent execution/memory banks behind the existing byte transport.
module pio_subsystem (
    input wire clk, rst_n, enable,
    input wire [3:0] host_address,
    input wire host_write_en, host_read_en,
    input wire [7:0] host_write_data,
    input wire [5:0] pin_in,
    output wire [7:0] host_read_data,
    output wire [11:0] pins,
    output wire [3:0] directions, open_drain
);
    reg selected_engine;
    wire [5:0] synchronized;
    wire [3:0] qualified;
    wire [1:0] running;
    wire [7:0] bank_read [0:1];
    wire [7:0] data_address [0:1];
    wire [31:0] write_word [0:1];
    wire [1:0] word_write;
    wire [7:0] status [0:1];
    wire [7:0] irq [0:1];
    wire [11:0] values [0:1];
    wire [3:0] dirs [0:1];
    wire [3:0] od [0:1];
    wire [11:0] owner;
    wire [31:0] global_status = {irq[1], irq[0], status[1], status[0]};
    // word_write is already bank-qualified. Decode each source locally rather
    // than muxing an entire staged word through selected_engine a second time.
    wire [1:0] group_write, owner_write;
    wire [11:0] owner_word = ({12{owner_write[0]}} & write_word[0][11:0]) |
                            ({12{owner_write[1]}} & write_word[1][11:0]);

    always @(posedge clk) begin
        if (!rst_n) selected_engine <= 0;
        else if (host_write_en && host_address == 4'hf && host_write_data < 2)
            selected_engine <= host_write_data[0];
    end
    assign host_read_data = bank_read[selected_engine];
    pio_inputs inputs_shared (.clk(clk), .rst_n(rst_n), .pin_in(pin_in),
        .synchronized(synchronized), .qualified(qualified));


    wire [31:0] packet_read [0:1];
    packet_sram_portal packet (.clk(clk), .rst_n(rst_n), .enable(enable),
        .commit(|word_write), .selector(selected_engine ? data_address[1] : data_address[0]),
        .data(selected_engine ? write_word[1] : write_word[0]),
        .read_selector0(data_address[0]), .read_selector1(data_address[1]),
        .read0(packet_read[0]), .read1(packet_read[1]));
    genvar e;
    generate for (e=0; e<2; e=e+1) begin: engines
        wire selected = selected_engine == e;
        assign group_write[e] = word_write[e] && data_address[e] == 8'h1c;
        assign owner_write[e] = word_write[e] && data_address[e] == 8'h1b;
        wire byte_write = host_write_en && selected;
        wire byte_read = host_read_en && selected;
        wire [7:0] core_read_data;
        wire [15:0] imem_read_data, imem_write_data;
        wire [31:0] core_selected_data;
        reg [31:0] bank_selected_data;
        wire [4:0] imem_address;
        wire imem_write, snapshot_read;
        wire [5:0] local_control;
        wire [5:0] group_control =
            ({6{group_write[0]}} &
             {write_word[0][6+e], write_word[0][4+e], write_word[0][10+e],
              write_word[0][8+e], write_word[0][2+e], write_word[0][e]}) |
            ({6{group_write[1]}} &
             {write_word[1][6+e], write_word[1][4+e], write_word[1][10+e],
              write_word[1][8+e], write_word[1][2+e], write_word[1][e]});
        wire [7:0] selector = data_address[e];
        wire common_selector = selector >= 8'h1a && selector <= 8'h1e || (selector >= 8'h20 && selector <= 8'h24);
        always @* begin
            bank_selected_data = core_selected_data;
            case (selector)
                8'h1a: bank_selected_data = 32'h50490102;
                8'h1b: bank_selected_data = {20'd0, owner};
                8'h1c: bank_selected_data = 0;
                8'h1d: bank_selected_data = global_status;
                8'h1e: bank_selected_data = {31'd0, selected_engine};
                8'h20,8'h21,8'h22,8'h23,8'h24: bank_selected_data = packet_read[e];
                default: ;
            endcase
        end
        pio_host_bank bank (.clk(clk), .rst_n(rst_n), .running(running[e]),
            .address(host_address), .write_en(byte_write), .read_en(byte_read),
            .write_data(host_write_data), .core_read_data(core_read_data),
            .imem_read_data(imem_read_data), .selected_data(bank_selected_data),
            .read_data(bank_read[e]), .imem_address(imem_address),
            .imem_write(imem_write), .imem_write_data(imem_write_data),
            .data_address(data_address[e]), .word_write(word_write[e]),
            .snapshot_read(snapshot_read), .write_word(write_word[e]),
            .control_command(local_control));
        protocol_core core (.clk(clk), .rst_n(rst_n), .enable(enable),
            .host_address(host_address), .host_write_en(byte_write), .host_write_data(host_write_data),
            .host_read_data(core_read_data), .pins_sync(synchronized), .filtered(qualified),
            .control_command(local_control | group_control),
            .word_write(word_write[e] && !common_selector), .snapshot_read(snapshot_read),
            .imem_write(imem_write), .write_word(write_word[e]), .data_address(data_address[e]),
            .imem_address(imem_address), .imem_write_data(imem_write_data),
            .imem_read_data(imem_read_data), .selected_data(core_selected_data),
            .status(status[e]), .irq_flags(irq[e]), .running(running[e]),
            .pins(values[e]), .directions(dirs[e]), .open_drain(od[e]));
    end endgenerate

    pio_gpio_owner ownership (.clk(clk), .rst_n(rst_n), .write_en(|owner_write),
        .write_owner(owner_word), .running(running), .owner(owner),
        .values0(values[0]), .values1(values[1]), .dirs0(dirs[0]), .dirs1(dirs[1]),
        .od0(od[0]), .od1(od[1]), .values(pins), .directions(directions), .open_drain(open_drain));
endmodule
`default_nettype wire
