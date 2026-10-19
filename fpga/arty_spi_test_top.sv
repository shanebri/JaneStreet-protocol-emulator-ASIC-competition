`default_nettype none

// Separate SPI test top: BTN0 resets; BTN1 runs one 256-byte test batch.
module arty_spi_test_top (
    input  wire       clk100,
    input  wire       btn_reset,
    input  wire       btn_run,
    input  wire       spi_miso,
    input  wire       nano_ready,
    output wire       spi_mosi, spi_sclk, spi_cs_n,
    output wire       uart_tx,
    output wire [3:0] led
);
    wire clk50, clk50_raw, feedback, feedback_buffered, locked;
    // 100 MHz * 10 / 20 = 50 MHz; the MMCM VCO runs at 1 GHz.
    MMCME2_BASE #(
        .CLKIN1_PERIOD(10.0), .DIVCLK_DIVIDE(1),
        .CLKFBOUT_MULT_F(10.0), .CLKOUT0_DIVIDE_F(20.0),
        .STARTUP_WAIT("FALSE")
    ) clock_manager (
        .CLKIN1(clk100), .CLKFBIN(feedback_buffered),
        .CLKFBOUT(feedback), .CLKOUT0(clk50_raw), .LOCKED(locked),
        .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(),
        .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
        .CLKOUT4(), .CLKOUT5(), .CLKOUT6(),
        .PWRDWN(1'b0), .RST(1'b0)
    );
    BUFG feedback_buf (.I(feedback), .O(feedback_buffered));
    BUFG core_clock_buf (.I(clk50_raw), .O(clk50));

    // Assert even when the clock stops; release only after four good edges.
    (* ASYNC_REG = "TRUE" *) reg [3:0] reset_pipe = 4'b1111;
    always @(posedge clk50 or negedge locked) begin
        if (!locked) reset_pipe <= 4'b1111;
        else reset_pipe <= {reset_pipe[2:0], 1'b0};
    end
    // Synchronize the human reset separately, avoiding a LUT on async reset pins.
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_button_sync = 0;
    always @(posedge clk50) begin
        reset_button_sync <= {reset_button_sync[0], btn_reset};
    end
    wire reset = reset_pipe[3] || reset_button_sync[1];

    arty_spi_test_host tester (
        .clk(clk50), .reset(reset), .button_run(btn_run),
        .slave_ready(nano_ready), .miso(spi_miso),
        .mosi(spi_mosi), .sclk(spi_sclk), .cs_n(spi_cs_n),
        .uart_tx(uart_tx), .ready(led[0]), .passed(led[1]),
        .failed(led[2]), .finished()
    );
    assign led[3] = locked;
endmodule

`default_nettype wire
