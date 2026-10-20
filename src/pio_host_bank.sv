`default_nettype none
// One context per engine. Only complete accepted byte transactions enter here.
module pio_host_bank (
    input wire clk, rst_n, running,
    input wire [3:0] address,
    input wire write_en, read_en,
    input wire [7:0] write_data, core_read_data,
    input wire [15:0] imem_read_data,
    input wire [31:0] selected_data,
    output reg [7:0] read_data,
    output reg [4:0] imem_address,
    output wire imem_write,
    output wire [15:0] imem_write_data,
    output reg [7:0] data_address,
    output wire word_write, snapshot_read,
    output wire [31:0] write_word,
    output wire [5:0] control_command
);
    reg [7:0] imem_low;
    reg [23:0] data_stage;
    reg [31:0] data_snapshot;
    assign imem_write = write_en && address == 4 && !running;
    assign imem_write_data = {write_data, imem_low};
    assign word_write = write_en && address == 4'ha;
    assign write_word = {write_data, data_stage};
    assign snapshot_read = read_en && address == 6;
    assign control_command = write_en && address == 0 ? write_data[5:0] : 6'd0;
    always @* begin
        read_data = core_read_data;
        case (address)
            0: read_data = 0;
            2: read_data = {3'd0, imem_address};
            3: read_data = imem_read_data[7:0];
            4: read_data = imem_read_data[15:8];
            5: read_data = data_address;
            6: read_data = selected_data[7:0];
            7: read_data = data_snapshot[15:8];
            9: read_data = data_snapshot[23:16];
            10: read_data = data_snapshot[31:24];
            15: read_data = 8'h21;
            default: ;
        endcase
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            imem_address <= 0; imem_low <= 0; data_address <= 0;
            data_stage <= 0; data_snapshot <= 0;
        end else begin
            if (snapshot_read) data_snapshot <= selected_data;
            if (write_en) begin
                case (address)
                    2: imem_address <= write_data[4:0];
                    3: if (!running) imem_low <= write_data;
                    4: if (!running) imem_address <= imem_address + 1'b1;
                    5: data_address <= write_data;
                    6: data_stage[7:0] <= write_data;
                    7: data_stage[15:8] <= write_data;
                    9: data_stage[23:16] <= write_data;
                    default: ;
                endcase
            end
        end
    end
endmodule
`default_nettype wire
