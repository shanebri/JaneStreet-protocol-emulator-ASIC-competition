; Finite packed SPI mode 0, one CS interval per byte. Header = byte count - 1.
; TX: first byte in bits31:24. RX: four bytes/word; final tail right-aligned.
; SHIFTCTRL=0, EXECCTRL=0x83e0. Default PINCTRL=0x20a08, PINS=4.
; RX backpressure occurs only after CS release. No empty RX word after a full group.
.sideset
    pull block side 0
    mov y, osr side 0
    out null, 32 side 0
frame:
    pull ifempty block side 0
    set x, 7 side 0
    set pins, 0 side 0 [3]
bits:
    out pins, 1 side 0 [3]
    in pins, 1 side 1 [7]
    jmp x--, bits side 0 [3]
    set pins, 1 side 0
    jmp !osre, partial side 0
    push block side 0
    jmp y--, frame side 0
    halt side 0
partial:
    mov x, x side 0
    jmp y--, frame side 0
    push block side 0
    halt side 0
