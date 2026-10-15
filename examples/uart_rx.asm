; Firmware UART RX, ui[6]. DIVIDER=1, SHIFTCTRL=3 (right IN).
; 16 clocks/bit. Result is packed in ISR[31:24], then pushed to RX FIFO.
; WAIT observes the two-flop synchronized input. Initial delay aims at bit 0 center.
    wait 0, pin, 0
    set x, 7 [22]
sample:
    in pins, 1 [14]
    jmp x--, sample
    wait 1, pin, 0
    push block
    halt
