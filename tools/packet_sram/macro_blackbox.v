// Synthesis-only port declaration; function and timing come from pinned PDK views.
(* blackbox *) module RM_IHPSG13_1P_64x16_c2 (
    input A_CLK, A_MEN, A_WEN, A_REN,
    input [5:0] A_ADDR,
    input [15:0] A_DIN,
    input A_DLY,
    output [15:0] A_DOUT
);
endmodule
