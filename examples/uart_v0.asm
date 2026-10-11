; Reference listing for uart_v0.hex; words are loaded starting at PC 0.
; UART TX = uo[0], GPIO[0] = uo[1]. At 50 MHz: 434 clocks/bit ~ 115200 baud.
LDI     434
ST      0x012       ; UART_DIV
LDI     0x055       ; ASCII U
ST      0x000       ; scratch[0]
LD      0x000
ST      0x011       ; UART_DATA starts the 8N1 frame
WAIT_TX
LDI     1
ST      0x010       ; GPIO[0] marks completion
WAIT    16
HALT
