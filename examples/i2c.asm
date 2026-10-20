; FIFO command dispatcher: command[4:0] PC, [8:5] bit-count minus one,
; [17:9] up to nine wire bits, first wire bit in bit9. OUT right, IN left.
; SDA OUT/SET base=8 width=1; IN base=2; SCL side-set=9; WAIT GPIO3.
; DIVIDER=24 Standard / 6 Fast at 50 MHz. See docs/i2c.md.
.sideset
dispatch: pull block
    out pc, 5
bits: out x, 4
bit: out pins, 1 side 0 [7]
    wait 1, gpio, 3 side 1 [7]
    in pins, 1
    jmp x--, bit side 0 [2]
    push block
    jmp dispatch
start: set pins, 1 [7]
    wait 1, gpio, 3 side 1 [7]
    wait 1, pin, 0 [7]
    set pins, 0 [7]
    nop
low: nop side 0 [2] ; also a command entry to prepare bus-clear's first low phase
    jmp dispatch
stop: set pins, 0 [7]
    wait 1, gpio, 3 side 1 [7]
    set pins, 1 [7]
    irq set, 0
    jmp dispatch
entry: wait 1, gpio, 3 [7]
    wait 1, pin, 0 [7]
    jmp dispatch
