; Finite packed UART TX. Header = byte count - 1 (1..65536 bytes).
; Data words are little endian. SHIFTCTRL=3, UART timing is 14 ticks/bit.
; PINCTRL chooses one OUT and one SET pin. START initializes shift counters.
    pull block
    mov y, osr
    out null, 32
frame:
    pull ifempty block
    set x, 7
    set pins, 0 [13]
bits:
    out pins, 1 [12]
    jmp x--, bits
    set pins, 1 [13]
    jmp y--, frame
    halt
