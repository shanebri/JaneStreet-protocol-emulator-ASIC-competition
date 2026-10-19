"""Desktop UART monitor for the Arty demo. Requires Python 3.9+ and pyserial."""

import argparse
from datetime import datetime
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    raise SystemExit("Install the dependency first: py -m pip install pyserial==3.5")


def open_port(port, baud):
    # Set control lines before opening; the demo needs neither flow control nor reset.
    connection = serial.serial_for_url(port, baudrate=baud, timeout=0,
                                       write_timeout=0.2, do_not_open=True,
                                       bytesize=8, parity="N", stopbits=1,
                                       xonxoff=False, rtscts=False, dsrdtr=False)
    connection.dtr = False
    connection.rts = False
    connection.open()
    return connection


def self_test():
    """Exercise the same serial settings and receive path without hardware."""
    payload = bytes(range(256))
    with open_port("loop://", 115200) as connection:
        assert connection.write(payload) == len(payload)
        received = bytearray()
        deadline = time.monotonic() + 2
        while len(received) < len(payload) and time.monotonic() < deadline:
            received.extend(connection.read(4096))
            time.sleep(0.01)
        if received != payload:
            raise SystemExit("FAIL: loopback bytes differed or timed out")
    print("PASS: all 256 byte values round-tripped through pyserial loopback.")


def run_gui(initial_port, initial_baud):
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    class Monitor:
        def __init__(self, root):
            self.root = root
            self.connection = None
            self.total = self.expected = 0
            root.title("Arty UART Test Client")
            root.geometry("940x580")
            root.minsize(740, 420)
            panel = ttk.Frame(root, padding=12)
            panel.pack(fill="both", expand=True)
            top = ttk.Frame(panel)
            top.pack(fill="x")
            ttk.Label(top, text="Port:").pack(side="left")
            self.port = ttk.Combobox(top, width=16)
            self.port.pack(side="left", padx=6)
            ttk.Button(top, text="Refresh ports", command=self.refresh).pack(side="left")
            ttk.Label(top, text="Baud:").pack(side="left", padx=(16, 4))
            self.baud = ttk.Combobox(top, values=(9600, 57600, 115200, 230400), width=9)
            self.baud.set(str(initial_baud))
            self.baud.pack(side="left")
            self.connect_button = ttk.Button(top, text="Connect", command=self.toggle)
            self.connect_button.pack(side="left", padx=10)
            ttk.Label(panel, text="8 data bits / no parity / 1 stop bit / no flow control").pack(anchor="w", pady=(8, 0))
            ttk.Label(panel, text="Arty demo: wait for LD4 + LD7, then press BTN1. Each press sends U (hex 55).\n"
                      "Release BTN1 before pressing again. This FPGA image does not receive PC commands.").pack(anchor="w", pady=8)
            self.status = tk.StringVar(value="Disconnected")
            ttk.Label(panel, textvariable=self.status).pack(anchor="w")
            self.counts = tk.StringVar()
            ttk.Label(panel, textvariable=self.counts).pack(anchor="w", pady=4)
            self.log = scrolledtext.ScrolledText(panel, wrap="word", font=("Consolas", 10), state="disabled")
            self.log.pack(fill="both", expand=True)
            bottom = ttk.Frame(panel)
            bottom.pack(fill="x", pady=(8, 0))
            ttk.Button(bottom, text="Clear", command=self.clear).pack(side="left")
            ttk.Button(bottom, text="Save log…", command=self.save).pack(side="left", padx=6)
            ttk.Button(bottom, text="Send U (loopback test)", command=self.send).pack(side="right")
            self.refresh()
            if initial_port:
                self.port.set(initial_port)
            self.update_counts()
            root.protocol("WM_DELETE_WINDOW", self.close)
            root.after(30, self.poll)

        def record(self, text):
            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.log.configure(state="normal")
            self.log.insert("end", f"{stamp}  {text}\n")
            # Bound memory use during long sessions.
            if int(self.log.index("end-1c").split(".")[0]) > 2500:
                self.log.delete("1.0", "501.0")
            self.log.see("end")
            self.log.configure(state="disabled")

        def refresh(self):
            try:
                ports = list(list_ports.comports())
            except (OSError, serial.SerialException) as error:
                self.record(f"Port enumeration failed: {error}")
                return
            self.port["values"] = [port.device for port in ports]
            if not self.port.get() and ports:
                self.port.set(ports[0].device)
            for port in ports:
                self.record(f"PORT {port.device}: {port.description}")
            if not ports:
                self.record("No COM ports found. Check USB data cable and USB serial driver, then Refresh ports.")

        def toggle(self):
            if self.connection is not None:
                self.disconnect()
                return
            try:
                baud = int(self.baud.get())
                if baud <= 0 or not self.port.get().strip():
                    raise ValueError("Select a port and a positive baud rate.")
                self.connection = open_port(self.port.get().strip(), baud)
            except (ValueError, OSError, serial.SerialException) as error:
                messagebox.showerror("Cannot open UART", f"{error}\n\nClose any other serial monitor using this COM port.\nCheck the port, USB data cable, and driver.")
                return
            self.total = self.expected = 0
            self.update_counts()
            self.port.configure(state="disabled")
            self.baud.configure(state="disabled")
            self.connect_button.configure(text="Disconnect")
            self.status.set(f"Connected to {self.port.get()} at {baud}. Waiting for bytes…")
            self.record("CONNECTED. Press BTN1 on the programmed board; no startup byte is expected.")

        def disconnect(self):
            connection, self.connection = self.connection, None
            if connection is not None:
                try:
                    connection.close()
                except (OSError, serial.SerialException) as error:
                    self.record(f"Close error: {error}")
                self.record("DISCONNECTED")
            self.port.configure(state="normal")
            self.baud.configure(state="normal")
            self.connect_button.configure(text="Connect")
            self.status.set("Disconnected")

        def update_counts(self):
            self.counts.set(f"RX bytes: {self.total}    Expected U (55): {self.expected}    Other bytes: {self.total - self.expected}")

        def poll(self):
            if self.connection is not None:
                try:
                    data = self.connection.read(4096)
                    if data:
                        self.total += len(data)
                        self.expected += data.count(b"U")
                        self.update_counts()
                        for start in range(0, len(data), 32):
                            chunk = data[start:start + 32]
                            self.record(f"RX  HEX: {chunk.hex(' ').upper()}  TEXT: {chunk!r}")
                        self.status.set("Received U (55): expected demo byte observed." if self.total == self.expected
                                        else "Other bytes received: check selected port, baud rate, and FPGA image.")
                except (OSError, serial.SerialException) as error:
                    self.record(f"READ ERROR: {error}")
                    self.disconnect()
            self.root.after(30, self.poll)

        def send(self):
            if self.connection is None:
                messagebox.showinfo("Not connected", "Connect to a port first.")
                return
            try:
                if self.connection.write(b"U") != 1:
                    raise serial.SerialTimeoutException("Incomplete write")
                self.record("TX  HEX: 55  TEXT: b'U' (the current FPGA demo does not echo)")
            except (OSError, serial.SerialException) as error:
                self.record(f"WRITE ERROR: {error}")
                self.disconnect()

        def clear(self):
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")
            self.total = self.expected = 0
            self.update_counts()

        def save(self):
            path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text log", "*.txt")])
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as output:
                        output.write(self.log.get("1.0", "end-1c"))
                except OSError as error:
                    messagebox.showerror("Cannot save log", str(error))

        def close(self):
            self.disconnect()
            self.root.destroy()

    root = tk.Tk()
    Monitor(root)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Preselect COM port, e.g. COM5; loop:// for software loopback")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--self-test", action="store_true", help="Run software serial loopback without opening the GUI")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        run_gui(args.port, args.baud)


if __name__ == "__main__":
    main()
