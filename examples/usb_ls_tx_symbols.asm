; Digital-only USB-LS symbol timing prototype. No USB electrical interface.
; Header = symbol count - 1; TX words contain four little-endian commands.
; Command: line state[1:0], loop count[7:2]; duration = loop count + 5 clocks.
; Logical states: J=2, K=1, SE0=0. Side-set pin is a TX-enable test marker.
; SHIFTCTRL=3, DIVIDER=1, EXECCTRL=0x83e0. OUT width2, side pin2.
.sideset
    pull block side 0
    mov y, osr side 0
    out null, 32 side 0
symbol:
    pull ifempty block side 1
    out pins, 2 side 1
    out x, 6 side 1
delay:
    jmp x--, delay side 1
    jmp y--, symbol side 1
    mov x, x side 1
    halt side 0
