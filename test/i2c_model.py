"""Resolved-wire I2C target and timing observer; no access to core internals."""
import cocotb
from cocotb.triggers import Timer, ReadWrite
from cocotb.utils import get_sim_time


class Bus:
    def __init__(self, dut, *, host, sda=0, scl=1, address=0x48, data=b"\x12\x34",
                 nack_address=False, nack_data=None, rise_ns=60, data_delay_ns=40,
                 stretches=None, rate=400_000, phase_ns=0):
        self.dut, self.sda, self.scl = dut, sda, scl
        self.host = host
        self.address, self.data = address, bytes(data)
        self.nack_address, self.nack_data = nack_address, nack_data
        self.rise_ns, self.data_delay_ns = rise_ns, data_delay_ns
        self.stretches = stretches or {}
        self.target_sda = self.target_scl = False
        self.stuck_sda = self.stuck_scl = False
        self.clear_after = None
        self.release_at = 0
        self.sda_event = None
        self.rise_at = [0]*4
        self.levels = [1]*4
        self.active = False
        self.bit = self.value = self.byte_index = self.read_index = 0
        self.reading = False
        self.ack = False
        self.bytes = []
        self.controller_acks = []
        self.starts = self.stops = self.rises = self.falls = 0
        self.last_rise = self.last_fall = self.last_sda = None
        self.start_at = self.stop_at = None
        self.highs, self.lows, self.setups, self.start_holds, self.stop_setups, self.start_setups = [], [], [], [], [], []
        self.periods = []
        self.rate = rate
        self.phase_ns = phase_ns
        self.task = cocotb.start_soon(self.run())

    def drive_sda(self, low, now):
        self.sda_event = (now + self.data_delay_ns, bool(low))

    def start(self, now):
        self.starts += 1
        self.active = True
        self.bit = self.value = self.byte_index = self.read_index = 0
        self.reading = False
        self.start_at = now
        if self.last_rise is not None and not self.stuck_sda:
            self.start_setups.append(now-self.last_rise)
        if self.stop_at is not None and not self.stuck_sda:
            assert now-self.stop_at >= (4700 if self.rate <= 100_000 else 1300), "bus free too short"

    def rising(self, sda, now):
        self.rises += 1
        if self.last_rise is not None:
            self.periods.append(now-self.last_rise)
        if self.clear_after and self.rises >= self.clear_after:
            # Recovery target releases only after this clock's falling edge.
            self.clear_after = -1
        if self.last_fall is not None:
            self.lows.append(now-self.last_fall)
        self.last_rise = now
        if not self.active:
            return
        if self.last_sda is not None:
            self.setups.append(now-self.last_sda)
        if (self.reading and self.bit < 8) or (not self.reading and self.bit == 8):
            assert not (int(self.dut.uio_oe.value) & (1 << (self.sda+4))), "controller did not release target-owned SDA"
        if self.bit < 8:
            self.value = (self.value << 1) | sda
        else:
            if self.reading:
                self.controller_acks.append(sda)
        self.bit += 1
        if self.bit == 8 and not self.reading:
            self.bytes.append(self.value)
            self.ack = ((self.value >> 1) == self.address and not self.nack_address) if self.byte_index == 0 else self.nack_data != self.byte_index-1

    def falling(self, now):
        self.falls += 1
        if self.clear_after == -1:
            self.stuck_sda = False
            self.clear_after = None
        if self.falls in self.stretches:
            self.release_at = now + self.stretches[self.falls]
        if self.start_at is not None:
            self.start_holds.append(now-self.start_at)
            self.start_at = None
        elif self.last_rise is not None:
            self.highs.append(now-self.last_rise)
        self.last_fall = now
        if not self.active:
            return
        if self.bit == 8:
            self.drive_sda(False if self.reading else self.ack, now)
        elif self.bit == 9:
            if self.reading and self.controller_acks[-1]:
                self.active = False
                self.drive_sda(False, now)
                return
            if self.byte_index == 0 and self.ack and self.value & 1:
                self.reading = True
            elif self.reading:
                self.read_index += 1
            self.byte_index += 1
            self.bit = self.value = 0
            self.drive_sda(self.reading and not ((self.data[self.read_index % len(self.data)] >> 7) & 1), now)
        elif self.reading:
            self.drive_sda(not ((self.data[self.read_index % len(self.data)] >> (7-self.bit)) & 1), now)

    async def run(self):
        if self.phase_ns:
            await Timer(self.phase_ns, unit="ns")
        while True:
            await Timer(5, unit="ns")
            await ReadWrite()
            now = float(get_sim_time(unit="ns"))
            if self.sda_event and now >= self.sda_event[0]:
                self.target_sda = self.sda_event[1]
                self.sda_event = None
            oe, out = int(self.dut.uio_oe.value) >> 4, int(self.dut.uio_out.value) >> 4
            # I2C owns only two selected pads. A high driver is always an error.
            mask = (1 << self.sda) | (1 << self.scl)
            assert not (oe & out & mask), "ASIC actively drove high on I2C"
            old_sda, old_scl = self.levels[self.sda], self.levels[self.scl]
            for p in range(4):
                low = bool(oe & (1 << p)) and not bool(out & (1 << p))
                if p == self.sda:
                    low |= self.target_sda or self.stuck_sda
                if p == self.scl:
                    low |= self.stuck_scl or now < self.release_at
                if low:
                    self.levels[p] = 0
                    self.rise_at[p] = now+self.rise_ns
                elif now >= self.rise_at[p]:
                    self.levels[p] = 1
            sda, scl = self.levels[self.sda], self.levels[self.scl]
            if old_scl and scl and old_sda != sda:
                if not sda:
                    self.start(now)
                else:
                    self.stops += 1
                    self.active = False
                    self.stop_at = now
                    if self.last_rise is not None:
                        self.stop_setups.append(now-self.last_rise)
                    self.target_sda = False
            if old_sda != sda:
                self.last_sda = now
            if not old_scl and scl:
                self.rising(sda, now)
            if old_scl and not scl:
                self.falling(now)
            incoming = self.host.host_data
            self.dut.uio_in.value = incoming | sum(v << (p+4) for p,v in enumerate(self.levels))

    def check_timing(self):
        standard = self.rate <= 100_000
        assert self.periods and min(self.periods) >= 1e9/self.rate, "SCL exceeds configured rate"
        for values, minimum, name in (
                (self.highs, 4000 if standard else 600, "high"),
                (self.lows, 4700 if standard else 1300, "low"),
                (self.setups, 250 if standard else 100, "data setup"),
                (self.start_holds, 4000 if standard else 600, "START hold"),
                (self.stop_setups, 4000 if standard else 600, "STOP setup")):
            assert values, f"no {name} measurements"
            assert min(values) >= minimum, (name, min(values), minimum)

        if self.starts > 1:
            assert self.start_setups and min(self.start_setups) >= (4700 if standard else 600)

    def close(self):
        self.task.cancel()
