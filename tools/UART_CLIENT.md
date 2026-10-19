# Windows UART test client

Copy `uart_client.py` and `uart-requirements.txt` into a folder on your PC.
Install Python 3.9 or newer with Tcl/Tk support (included in the standard Windows
Python installer). From PowerShell in that folder, run:

```powershell
py -m pip install -r uart-requirements.txt
py uart_client.py
```

If your Python installation uses `python` instead of `py`, substitute that command.
The only extra package is pyserial; the GUI uses Python's built-in Tkinter.

1. Close the old serial monitor so it releases the COM port.
2. Plug a USB **data** cable into the Arty PROG/UART connector and program the FPGA.
3. Click **Refresh ports**, select the board's COM port, leave baud at **115200**,
   and click **Connect**. Port descriptions appear in the log. If several ports
   appear, compare the list with the board unplugged and plugged back in.
4. Wait for **LD4** and **LD7**, then press **BTN1** for at least 10 ms.
5. Look for `RX HEX: 55 TEXT: b'U'` and an increasing expected-byte counter.
   Release BTN1 for at least 10 ms between presses. Holding it does not repeat.

The client uses 8N1 with all flow control disabled and DTR/RTS deasserted.
It displays every received byte in hex and escaped text, including nonprinting
bytes. **Save log** exports the currently retained timestamped log. The display
retains approximately the latest 2,000–2,500 lines to limit memory use. Counters
reset on Connect or Clear. A disconnect/unplug error is logged; reconnect manually
after restoring the cable.

The current FPGA wrapper is transmit-only. **Send U** is for software or external
adapter loopback testing; the Arty image will not echo it or accept commands.
Receiving `55` verifies reception of the expected demo byte, not precise UART
timing or a complete bidirectional hardware test.

## Test the client without hardware

```powershell
py uart_client.py --self-test
py uart_client.py --port loop://
```

The first command checks all 256 byte values using pyserial's software loopback.
For the second, click Connect and **Send U**; an RX `55` should appear.
Neither test validates the USB cable, driver, or FPGA.

## Troubleshooting

- **No ports:** check Windows Device Manager under Ports (COM & LPT), the USB
  data cable, board power, and the board's USB serial driver.
- **Access denied:** another application has the port open, or the selected
  port is unavailable. Close other serial terminals and reconnect.
- **Connected but no bytes:** the demo is silent until BTN1. Check the ready and
  clock LEDs, programmed image, and COM port. Reprogram after power cycling.
- **Bytes other than 55:** verify 115200 baud and the intended demo bitstream.
- **No tkinter module:** repair/install Python with Tcl/Tk support.

From the repository root, use `py tools/uart_client.py` after installing
`tools/uart-requirements.txt`.
