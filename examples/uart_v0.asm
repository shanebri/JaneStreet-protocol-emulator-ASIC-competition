; Firmware UART TX: configure DIVIDER=31, PINCTRL=0x1008, SHIFTCTRL=3.
; Enqueue 0x55 into TX FIFO, then START. No UART hardware exists.
; 14 SM ticks x 31 clocks = 434 clocks/bit at 50 MHz (~115200 baud).
; OUT covers uo[0]; SET covers uo[1:0]. uo[1] marks completed stop bit.
    pull block
    set x, 7
    set pins, 0 [13]
bitloop:
    out pins, 1 [12]
    jmp x--, bitloop
    set pins, 1 [13]
    set pins, 3
    halt
