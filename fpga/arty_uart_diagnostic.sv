`default_nettype none

// Standalone board/USB test: 100 MHz / 868 = 115207 baud, 8N1.
// Repeated U frames bypass the PIO engine, loader and MMCM entirely.
module arty_uart_diagnostic #(
    parameter integer GAP_CYCLES = 50000000
) (
    input wire clk100,
    input wire btn_reset,
    input wire btn_run,
    output wire uart_tx,
    output wire [3:0] led
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_sync = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] run_sync = 0;
    always @(posedge clk100) begin
        reset_sync <= {reset_sync[0], btn_reset};
        run_sync <= {run_sync[0], btn_run};
    end

    reg [25:0] gap = 0;
    reg [25:0] heartbeat = 0;
    reg [9:0] baud_count = 0;
    reg [9:0] frame = 10'h3ff;
    reg [3:0] remaining = 0;
    reg sent_toggle = 0;
    always @(posedge clk100) begin
        if (reset_sync[1]) begin
            gap <= 0;
            heartbeat <= 0;
            baud_count <= 0;
            frame <= 10'h3ff;
            remaining <= 0;
            sent_toggle <= 0;
        end else begin
            heartbeat <= heartbeat + 1'b1;
            if (remaining != 0) begin
                if (baud_count == 867) begin
                    baud_count <= 0;
                    frame <= {1'b1, frame[9:1]};
                    remaining <= remaining - 1'b1;
                    if (remaining == 1) sent_toggle <= !sent_toggle;
                end else baud_count <= baud_count + 1'b1;
            end else if (gap == GAP_CYCLES - 1) begin
                gap <= 0;
                baud_count <= 0;
                frame <= {1'b1, 8'h55, 1'b0};
                remaining <= 10;
            end else gap <= gap + 1'b1;
        end
    end
    assign uart_tx = frame[0];
    assign led = {1'b1, heartbeat[25], sent_toggle, run_sync[1]};
endmodule

`default_nettype wire
