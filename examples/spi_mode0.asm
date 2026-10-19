; Eight-bit SPI master: CPOL=0, CPHA=0, MSB-first, one byte per START.
; Default mapping: MOSI=uo[0], SCLK=uo[1], CS_n=uo[2], MISO=ui[6].
; Host setup while stopped:
;   PINS=0x04       (CS_n high, SCLK/MOSI low; reset PINS=1 is NOT SPI idle)
;   PINCTRL=0x20A08 (OUT width1/base0, SET width1/base2, side pin1, IN base0)
;   SHIFTCTRL=0    (OUT left, IN left, explicit FIFO transfers)
;   EXECCTRL=0x83E0 (optional side-set enabled, entry0, wrap0..31)
;   DIVIDER=4      (example: 781250 Hz SCLK with a 50 MHz core)
; Queue TX as byte << 24. RX contains the received byte in bits [7:0].
; SCLK high/low each last 8 SM ticks; period=16*DIVIDER core clocks.
; MISO must be valid through the rising edge AND early enough for the two-flop
; synchronizer. No board pins or Vivado wrapper are configured by this program.
.sideset
    pull block side 0       ; Wait with SCLK low and host-initialized CS_n high.
    mov isr, null side 0
    set x, 7 side 0
    set pins, 0 side 0 [3]  ; Assert CS_n; SET mapping is separate from MOSI.
bitloop:
    out pins, 1 side 0 [3]  ; Present next MSB during the low phase.
    in pins, 1 side 1 [7]   ; Rising edge: collect synchronized MISO, then hold high.
    jmp x--, bitloop side 0 [3] ; Falling edge; next OUT completes the low phase.
    set pins, 1 side 0      ; Deassert CS_n after the eighth falling edge.
    push block side 0      ; RX backpressure occurs with CS_n high, SCLK low.
    halt side 0
