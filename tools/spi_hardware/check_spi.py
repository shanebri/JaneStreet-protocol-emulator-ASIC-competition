"""Verify Arty PIO master + Nano 33 BLE slave over their two USB serial ports."""
import argparse
from contextlib import ExitStack
from functools import reduce
import json
from operator import xor
from pathlib import Path
import sys
import time


class FrameParser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 2:
            if self.buffer[:2] != b"\xa5\x5a":
                del self.buffer[0]
                continue
            if len(self.buffer) < 7:
                break
            frame = bytes(self.buffer[:7])
            del self.buffer[:7]
            if reduce(xor, frame) != 0:
                raise ValueError(f"FPGA UART checksum error: {frame.hex(' ')}")
            frames.append(dict(sequence=frame[2], tx=frame[3], rx=frame[4], status=frame[5]))
        return frames


class Results:
    def __init__(self):
        self.fpga = []
        self.nano = []
        self.nano_done = False

    def accept_fpga(self, record):
        seq = len(self.fpga)
        if record["status"]:
            reason = {1: "MISO mismatch", 2: "PIO fault/missing RX", 3: "PIO timeout",
                      4: "Nano READY handshake timeout"}.get(record["status"], "unknown")
            raise ValueError(f"FPGA sequence {record['sequence']}: {reason}; RX={record['rx']:02X}")
        if seq >= 256 or record != dict(sequence=seq, tx=seq, rx=seq ^ 0xa5, status=0):
            raise ValueError(f"Unexpected FPGA record at sequence {seq}: {record}")
        self.fpga.append(record)

    def accept_nano(self, line):
        if line.startswith("ERROR"):
            raise ValueError(f"Nano: {line}")
        if line.startswith("RX "):
            fields = line.split()
            if len(fields) != 6:
                raise ValueError(f"Malformed Nano report: {line}")
            seq, received, sent, count, passed = map(int, fields[1:])
            expected_seq = len(self.nano)
            if expected_seq >= 256 or (seq, received, sent, count, passed) != (
                    expected_seq, expected_seq, expected_seq ^ 0xa5, 1, 1):
                raise ValueError(f"Nano MOSI/length/sequence failure: {line}")
            self.nano.append(dict(sequence=seq, rx=received, tx=sent, count=count))
        elif line.startswith("DONE "):
            if line != "DONE 256 0" or len(self.nano) != 256 or self.nano_done:
                raise ValueError(f"Incomplete/failed Nano batch: {line}")
            self.nano_done = True
        else:
            raise ValueError(f"Unexpected Nano message during test: {line}")

    @property
    def complete(self):
        return len(self.fpga) == len(self.nano) == 256 and self.nano_done


def wait_reply(port, command, expected, timeout=5):
    port.write((command + "\n").encode("ascii"))
    deadline = time.monotonic() + timeout
    line = bytearray()
    while time.monotonic() < deadline:
        byte = port.read(1)
        if byte == b"\n":
            reply = line.decode("ascii", errors="replace").strip()
            line.clear()
            if reply == expected:
                return
            if reply.startswith("ERROR"):
                raise ValueError(reply)
        elif byte:
            line.extend(byte)
            if len(line) > 512:
                raise ValueError("Oversized Nano response")
        else:
            time.sleep(0.005)
    raise TimeoutError(f"Nano did not answer {command!r}. Check sketch, port and Serial Monitor ownership.")


def run(args):
    import serial
    if args.fpga_port.lower() == args.nano_port.lower():
        raise ValueError("The FPGA and Nano need different USB COM ports")
    with ExitStack() as stack:
        fpga = stack.enter_context(serial.Serial(args.fpga_port, 115200, timeout=0, write_timeout=1))
        nano = stack.enter_context(serial.Serial(args.nano_port, 115200, timeout=0, write_timeout=1))
        log = stack.enter_context(args.log.open("w", encoding="utf-8")) if args.log else None
        time.sleep(1)
        nano.reset_input_buffer()
        wait_reply(nano, "PING", "PIO_SPI_NANO_V1")
        input("Press and release FPGA BTN0; wait for LD4 + LD7. Then press Enter here: ")
        fpga.reset_input_buffer()
        nano.reset_input_buffer()
        wait_reply(nano, "ARM", "ARMED 256 MODE0 MSB")
        print("Nano armed. Press FPGA BTN1 once now. Do not reset either board during the test.", flush=True)
        parser, results, nano_buffer = FrameParser(), Results(), bytearray()
        deadline = time.monotonic() + args.timeout
        last_progress = -1
        while time.monotonic() < deadline:
            for record in parser.feed(fpga.read(4096)):
                if log:
                    log.write(json.dumps(dict(source="fpga", **record)) + "\n")
                results.accept_fpga(record)
            nano_buffer.extend(nano.read(4096))
            while b"\n" in nano_buffer:
                raw, _, tail = nano_buffer.partition(b"\n")
                nano_buffer[:] = tail
                line = raw.decode("ascii", errors="strict").strip()
                if not line:
                    continue
                if log:
                    log.write(json.dumps(dict(source="nano", line=line)) + "\n")
                results.accept_nano(line)
            if len(nano_buffer) > 512:
                raise ValueError("Oversized/unterminated Nano message")
            progress = min(len(results.fpga), len(results.nano))
            if progress // 32 != last_progress:
                print(f"Verified: FPGA RX {len(results.fpga)}/256; Nano RX {len(results.nano)}/256", flush=True)
                last_progress = progress // 32
            if results.complete:
                print("PASS: all 256 byte values checked in both directions. FPGA LD5 should be on, LD6 off.")
                return
            time.sleep(0.002)
        raise TimeoutError(f"Only {len(results.fpga)} FPGA and {len(results.nano)} Nano reports received; "
                           f"Nano DONE={results.nano_done}. Check BTN1, wiring and selected bitstream.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List USB serial ports")
    parser.add_argument("--fpga-port", help="Arty PROG/UART port, e.g. COM3")
    parser.add_argument("--nano-port", help="Nano USB port, e.g. COM5")
    parser.add_argument("--timeout", type=float, default=90, help="Seconds allowed including the BTN1 press")
    parser.add_argument("--log", type=Path, help="Optional JSONL result log (overwrites this file)")
    args = parser.parse_args()
    if args.list:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(f"{port.device}: {port.description} [{port.hwid}]")
        return
    if not args.fpga_port or not args.nano_port or args.timeout <= 0:
        parser.error("provide --fpga-port and --nano-port, with a positive --timeout")
    try:
        run(args)
    except (OSError, ValueError, TimeoutError, KeyboardInterrupt) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
