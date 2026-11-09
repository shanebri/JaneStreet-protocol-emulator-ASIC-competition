"""RTL-only differential tests. Drive the production top exclusively through pins."""

from collections import Counter, deque
import os
from pathlib import Path
import random
import sys

import cocotb
from cocotb.triggers import Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pio_reference import ABORT, FIFO_CLEAR, RESUME, START, STOP, Chip, Op


CONTROL, STATUS, IMEM_ADDR, IMEM_LO, IMEM_HI, DATA_ADDR = range(6)
DATA = (6, 7, 9, 10)
IRQ, DEBUG, SELECT = 12, 13, 15
TX, RX, SHIFT, EXEC, PIN, DIVIDER, IRQ_SET = 8, 9, 0x10, 0x11, 0x12, 0x13, 0x14
ROUTE, DIRS, OD, FILTER, OWNER, GROUP = 0x16, 0x17, 0x18, 0x19, 0x1b, 0x1c


def ins(op, arg=0, delay=0, side=None):
    timing = delay if side is None else 16 | (side << 3) | delay
    return (op << 13) | (timing << 8) | arg


NOP, HALT = 0xa042, 0xc080


class Bench:
    """The only RTL-specific code is here. No hierarchy writes or RTL-fed predictions."""

    # Ignore stale storage (inactive EXEC word and FIFO slots outside the queue).
    REGISTERS = (
        "x", "y", "osr", "isr", "out_count", "in_count", "running", "fault",
        "pins", "directions", "open_drain", "filter_enable", "shiftctrl", "execctrl",
        "pinctrl", "route", "divider", "divider_left", "delay_left", "irq_waiting", "irq",
    )

    def __init__(self, dut):
        self.dut = dut
        self.model = Chip()
        self.cores = [dut.user_project.pio.engines[i].core for i in range(2)]
        self.registers = [[getattr(core, name) for name in self.REGISTERS] for core in self.cores]
        self.banks = [dut.user_project.pio.engines[i].bank for i in range(2)]
        self.io = dut.user_project.pio
        self.edge = 0
        self.inputs = 0
        self.case = "initial reset"
        self.history = deque(maxlen=10)
        self.attempts = Counter()

    def compare(self, pins):
        differences = {}

        def check(name, reference, signal, shift=0):
            value = signal.value
            actual = (int(value) << shift) if value.is_resolvable else str(value)
            if reference != actual:
                differences[name] = reference, actual

        check("uo", pins.uo, self.dut.uo_out)
        check("uio_out", pins.uio_out, self.dut.uio_out)
        check("uio_oe", pins.uio_oe, self.dut.uio_oe)
        check("selected", self.model.selected, self.io.selected_engine)
        check("owner", self.model.owner, self.io.owner)
        check("synchronized", self.model.sync, self.io.synchronized)
        check("qualified", self.model.qualified, self.io.qualified)
        for i, engine in enumerate(self.model.engines):
            core, bank = self.cores[i], self.banks[i]
            for name, signal in zip(self.REGISTERS, self.registers[i]):
                check(f"{i}.{name}", getattr(engine, name), signal,
                      8 if name in ("directions", "open_drain") else 0)
            check(f"{i}.pc", engine.pc, core.current_pc)
            check(f"{i}.debug", engine.debug, core.debug_flags)
            check(f"{i}.inputs", self.model.inputs(i), core.inputs_actual)
            check(f"{i}.exec_pending", engine.pending_exec is not None, core.exec_pending)
            if engine.pending_exec is not None:
                check(f"{i}.exec_word", engine.pending_exec, core.exec_instruction)
            for attr, signal in (("imem_address", bank.imem_address), ("imem_low", bank.imem_low),
                                 ("selector", bank.data_address), ("stage", bank.data_stage),
                                 ("snapshot", bank.data_snapshot)):
                check(f"{i}.host.{attr}", getattr(self.model.banks[i], attr), signal)
            for name, fifo in (("tx", core.tx_fifo), ("rx", core.rx_fifo)):
                queue = getattr(engine, name)
                check(f"{i}.{name}.level", len(queue), fifo.level)
                # Compare queue contents in dequeue order, independent of ring position.
                if queue:
                    head = int(fifo.read_ptr.value)
                    for offset, word in enumerate(queue):
                        check(f"{i}.{name}[{offset}]", word, fifo.words[(head + offset) % 4])
            if engine.imem[engine.pc] is not None:
                check(f"{i}.imem[{engine.pc}]", engine.imem[engine.pc], core.fetched_instruction)
        return differences

    def diagnostic(self, differences):
        mismatch = "\n".join(f"  {name}: model={want!r}, RTL={got!r}"
                             for name, (want, got) in differences.items())
        return (f"{self.case}, core edge {self.edge}\n{mismatch}\n"
                "Recent edges (edge, ui, uio, ena, rst_n, pre-PCs, attempts):\n"
                + "\n".join(map(str, self.history)))

    async def step(self, bus=0, nibble=0, *, ena=True, rst_n=True, baseline_difference=None):
        ui = bus | ((self.inputs & 3) << 6)
        uio = nibble | ((self.inputs >> 2) << 4)
        dut = self.dut
        dut.clk.value = 0
        dut.ui_in.value = ui
        dut.uio_in.value = uio
        dut.ena.value = ena
        dut.rst_n.value = rst_n
        await Timer(2, unit="ns")
        if self.edge:
            oe = self.model.pins(ui, ena=ena, rst_n=rst_n).uio_oe
            assert int(dut.uio_oe.value) == oe, f"{self.case}: OE before edge {self.edge + 1}"
        pcs = tuple(engine.pc for engine in self.model.engines)
        pins = self.model.step(ui, uio, ena=ena, rst_n=rst_n)
        self.edge += 1
        attempts = []
        for engine in self.model.engines:
            if engine.last_attempt:
                instruction, injected, result = engine.last_attempt
                action = result.stall or ("fault" if result.fault else "halt" if result.halt else "retire")
                self.attempts[instruction.op, injected, action] += 1
                attempts.append(f"{'EXEC ' if injected else ''}{instruction.word:04x} {action}")
            else:
                attempts.append("-")
        self.history.append((self.edge, f"{ui:02x}", f"{uio:02x}", ena, rst_n, pcs, attempts))
        dut.clk.value = 1
        await Timer(2, unit="ns")
        differences = self.compare(pins)
        if differences:
            diagnostic = self.diagnostic(differences)
            if os.getenv("PIO_REF_STRICT") or differences != baseline_difference:
                raise AssertionError(diagnostic)
            dut._log.warning("Known baseline discrepancy\n%s", diagnostic)

    async def idle(self, count=1, *, ena=True):
        for _ in range(count):
            await self.step(ena=ena)

    async def reset(self):
        await self.step(rst_n=False)
        await self.idle()

    async def write(self, address, data):
        await self.stage_byte(address, data)
        await self.step(address | 16, data >> 4)
        await self.step(address)

    async def stage_byte(self, address, data):
        await self.step(address | 16, data & 15)
        await self.step(address)

    async def read(self, address):
        await self.step(address | 32)
        await self.step(address)
        await self.step(address | 32)
        await self.step(address)

    async def stage_word(self, selector, word):
        await self.write(DATA_ADDR, selector)
        for i, address in enumerate(DATA[:-1]):
            await self.write(address, (word >> (i * 8)) & 255)

    async def write_word(self, selector, word):
        await self.stage_word(selector, word)
        await self.write(DATA[-1], word >> 24)

    async def read_word(self, selector):
        await self.write(DATA_ADDR, selector)
        for address in DATA:
            await self.read(address)

    async def load(self, words, start=0):
        await self.write(IMEM_ADDR, start)
        for word in words:
            await self.write(IMEM_LO, word & 255)
            await self.write(IMEM_HI, word >> 8)


@cocotb.test()
async def reference_all_opcode_arguments(dut):
    """Every argument byte in all 8 opcode groups, including every reserved form."""
    b = Bench(dut)
    await b.reset()
    await b.write_word(EXEC, 0x83e0)
    await b.write_word(DIVIDER, 65535)
    rng = random.Random(0x21dec0de)
    cases = [(op, arg) for op in range(8) for arg in range(256)]
    rng.shuffle(cases)
    engine = b.model.engines[0]
    for op, arg in cases:
        # Toggle the current pin on every legal attempt. A faulty attempt must
        # leave that pin alone, even with the side enable bit set.
        word = ins(op, arg, rng.randrange(8), 1 ^ (engine.pins & 1))
        b.case = f"raw decode word={word:04x}"
        await b.load([word])
        await b.write(CONTROL, START)
        instruction, injected, outcome = engine.last_attempt
        assert instruction.word == word and not injected
        assert outcome.fault == (not instruction.legal)
        await b.write(CONTROL, STOP)
    assert sum(b.attempts.values()) == 2048
    assert sum(count for (_, _, action), count in b.attempts.items() if action == "fault") == 996


@cocotb.test()
async def reference_exec_and_threshold_boundaries(dut):
    b = Bench(dut)
    rng = random.Random(0x21e7ec)
    children = {
        "gpio": ins(Op.WAIT, 0x80, delay=7, side=1),
        "irq_ack": ins(Op.IRQ, 0x27, side=1),
        "taken branch": ins(Op.JMP, 5, side=1),
        "untaken branch": ins(Op.JMP, 0xa5, side=1),
        "pc write": ins(Op.MOV, 0xa3, side=1),  # MOV PC,NULL branches to 0.
        "halt": ins(Op.IRQ, 0x80, delay=7, side=1),
        "fault": ins(Op.SET, 0xff, delay=7, side=1),
    }
    for name, child in children.items():
        b.case = f"nested EXEC with {name}"
        b.inputs = 0
        await b.reset()
        engine = b.model.engines[0]
        # Wrap coincides with the originating OUT. The pending children see PC=2.
        await b.write_word(EXEC, 0x8000 | (1 << 5) | 2)
        await b.write_word(SHIFT, 3)
        await b.load([0x80a0, ins(Op.OUT, 0xf0, 3, 0), ins(Op.SET, 0x39), HALT, HALT, HALT])
        await b.write_word(TX, ins(Op.OUT, 0xf0, 2, 0) | (child << 16))
        await b.write(CONTROL, START)
        await b.idle(5)
        assert engine.pc == 2 and engine.pending_exec == child
        # STOP/RESUME and disable land inside the injected instruction's delay.
        await b.idle(2, ena=False)
        await b.idle()
        await b.write(CONTROL, STOP)
        await b.write(CONTROL, RESUME)
        if name == "gpio":
            b.inputs = 1
        elif name == "irq_ack":
            assert engine.irq == 0x80 and engine.irq_waiting
            await b.write(IRQ, 0x80)
        if name == "pc write":
            await b.write_word(TX, 0)  # Permit the branch-to-entry PULL once more.
        await b.idle(20)
        if name in ("fault", "halt"):
            assert engine.pc == 2 and engine.pending_exec == child
            assert engine.fault == (name == "fault") and not engine.running
            await b.write(CONTROL, RESUME)
            assert not engine.running
    assert b.attempts[Op.OUT, True, "retire"] >= len(children)
    for key in ((Op.WAIT, True, "gpio"), (Op.WAIT, True, "retire"),
                (Op.IRQ, True, "irq_ack"), (Op.IRQ, True, "retire"),
                (Op.IRQ, True, "halt"), (Op.SET, True, "fault")):
        assert b.attempts[key], key

    b.case = "MOV EXEC injects OUT EXEC, then injects itself once before HALT"
    await b.reset()
    engine = b.model.engines[0]
    await b.load([0x80a0, ins(Op.MOV, 0x87), HALT])
    out_exec = ins(Op.OUT, 0xf0)
    await b.write_word(TX, out_exec | (HALT << 16))
    await b.write(CONTROL, START)
    await b.idle(3)
    assert engine.pc == 2 and engine.pending_exec == HALT and engine.out_count == 32
    await b.idle()
    assert not engine.running and engine.pc == 2

    b.case = "START preempts a delayed EXEC without clearing a live IRQ"
    await b.reset()
    engine = b.model.engines[0]
    await b.load([0x80a0, ins(Op.OUT, 0xf0, delay=7), HALT])
    await b.write_word(TX, ins(Op.SET, 0x3f))
    await b.write_word(IRQ_SET, 128)
    await b.write(CONTROL, START)
    await b.idle()
    assert engine.pending_exec == ins(Op.SET, 0x3f)
    await b.write(CONTROL, START)
    assert engine.pc == 0 and engine.pending_exec is None and engine.irq == 128
    assert engine.last_attempt[2].stall == "pull"

    # Sweep all threshold encodings and rotate independently through both shift
    # directions. Include a one-bit threshold and both exact/overshooting totals.
    for threshold in range(1, 33):
        b.case = f"automatic transfer thresholds={threshold}"
        await b.reset()
        engine = b.model.engines[0]
        encoded = threshold & 31
        shift = (threshold % 4) | 12 | (encoded << 4) | (encoded << 9)
        await b.write_word(SHIFT, shift)
        before = max(threshold - 1, 1)
        after = 1 + (threshold & 1)
        await b.load([ins(Op.OUT, 0x20 | before), ins(Op.OUT, 0xc0 | after),
                      ins(Op.OUT, 0x20 | (threshold & 31)), ins(Op.MOV, 0xc1),
                      ins(Op.IN, 0x20 | before), ins(Op.IN, 0xe0 | after), HALT])
        for value in (0xffffffff, rng.getrandbits(32), 0x80000001):
            await b.write_word(TX, value)
        await b.write(CONTROL, START)
        await b.idle(8)
        assert not engine.running and not engine.fault and 1 <= len(engine.rx) <= 2
        await b.read_word(RX)


@cocotb.test()
async def reference_pc_writes_and_wrap(dut):
    b = Bench(dut)
    for right in (0, 1):
        for width in (5, 16, 32):
            b.case = f"OUT PC at wrap top, right={right} width={width}"
            await b.reset()
            e = b.model.engines[0]
            await b.write_word(SHIFT, right)
            await b.write_word(EXEC, (30 << 10) | (31 << 5) | 8)
            await b.load([0x80a0, ins(Op.OUT, 0xa0 | (width & 31))], start=30)
            target = 0 if right else 28
            await b.load([ins(Op.SET, 0x47), ins(Op.MOV, 0xa2)], start=target)
            await b.load([HALT], start=7)
            value = (0xb4ca6d80 | target) & ((1 << width) - 1)
            await b.write_word(TX, value if right else value << (32 - width))
            await b.write(CONTROL, START)
            assert e.pc == 31
            await b.idle()
            assert e.pc == target
            await b.idle(2)
            assert e.pc == 7 and e.y == 7
            await b.idle()
            assert not e.running


@cocotb.test()
async def reference_same_edge_host_arbitration(dut):
    b = Bench(dut)
    for full in (False, True):
        b.case = f"TX write concurrent with OUT autopull, full={full}"
        await b.reset()
        e = b.model.engines[0]
        await b.write_word(SHIFT, 5)
        await b.load([NOP | 0x0200, ins(Op.OUT, 0xc0), HALT])
        initial = [0x80000001, 0x76543210, 0x11223344, 0x55aa55aa] if full else []
        for word in initial:
            await b.write_word(TX, word)
        incoming = 0xfedcba98
        await b.stage_word(TX, incoming)
        await b.write(CONTROL, START)
        await b.stage_byte(DATA[-1], incoming >> 24)
        await b.step(DATA[-1] | 16, incoming >> 28)
        _, _, result = e.last_attempt
        if full:
            assert result.pop_tx and e.isr == initial[0] and list(e.tx) == initial[1:] + [incoming]
        else:
            assert result.stall == "autopull" and e.isr == 0 and list(e.tx) == [incoming]
        assert e.debug == 0
        await b.step(DATA[-1])
        if not full:
            assert e.isr == incoming and not e.tx

    for full in (False, True):
        b.case = f"RX read concurrent with IN autopush, full={full}"
        await b.reset()
        e = b.model.engines[0]
        if full:
            await b.load([ins(Op.SET, 0x2d), ins(Op.IN, 0x20), ins(Op.FIFO, 0x20), ins(Op.JMP, 1)])
            await b.write(CONTROL, START)
            await b.idle(16)
            await b.write(CONTROL, STOP)
            assert list(e.rx) == [13] * 4
        await b.write_word(SHIFT, 11)
        await b.load([ins(Op.SET, 0x3f), ins(Op.IN, 0x20), HALT])
        await b.write(DATA_ADDR, RX)
        await b.write(CONTROL, START)
        await b.step(6 | 32)
        _, _, result = e.last_attempt
        assert result.push_rx == 31
        assert b.model.banks[0].snapshot == (13 if full else 0)
        assert e.debug == (0 if full else 2)
        assert list(e.rx) == ([13, 13, 13, 31] if full else [31])
        # Held RD and then a different address abandon phase without a second pop.
        await b.step(6 | 32)
        await b.step(7)
        await b.read(7)

    for arg, opcode, initial, host_address, host_value, expected, stall in (
        (7, Op.IRQ, 128, IRQ, 128, 128, None),           # Firmware set wins clear.
        (0x27, Op.IRQ, 0, IRQ, 128, 128, "irq_ack"),   # IRQ WAIT's first set wins too.
        (0x47, Op.IRQ, 0, DATA[-1], 128, 0, None),      # Firmware clear wins set.
        (0xc7, Op.WAIT, 128, DATA[-1], 128, 0, None),   # WAIT 1 IRQ clears an old flag.
        (0xc7, Op.WAIT, 0, DATA[-1], 128, 128, "wait_irq"),  # No same-edge bypass.
        (0x47, Op.WAIT, 0, DATA[-1], 128, 128, None),   # WAIT 0 retires on old state.
    ):
        b.case = f"IRQ arbitration {opcode.name} arg={arg:02x} old={initial:02x}"
        await b.reset()
        e = b.model.engines[0]
        await b.write_word(IRQ_SET, initial)
        await b.load([NOP | 0x0200, ins(opcode, arg), HALT])
        data = host_value
        if host_address == DATA[-1]:
            await b.stage_word(IRQ_SET, host_value)
            data = 0
        await b.write(CONTROL, START)
        await b.stage_byte(host_address, data)
        await b.step(host_address | 16, data >> 4)
        _, _, result = e.last_attempt
        assert result.stall == stall and e.irq == expected
        await b.step(host_address)
        await b.read(IRQ)

    b.case = "sticky debug clear concurrent with nonblocking fallback"
    await b.reset()
    await b.load([NOP | 0x0200, ins(Op.FIFO, 0x80), HALT])
    await b.write(CONTROL, START)
    await b.write(DEBUG, 8)
    assert b.model.engines[0].debug == 8


def random_program(rng, entry, sideset):
    """Build a complete memory image with weighted, valid operands and short branches."""
    counts = (0, 1, 2, 7, 8, 15, 16, 17, 24, 30, 31)
    program = [0] * 32
    for slot in range(32):
        pc = (entry + slot) & 31
        op = rng.choice((Op.JMP, Op.WAIT, Op.IN, Op.IN, Op.OUT, Op.OUT,
                         Op.FIFO, Op.MOV, Op.MOV, Op.IRQ, Op.SET, Op.SET))
        if slot < 2:
            op = Op.SET  # Ensure initialized scratch state and a useful entry prefix.
        match op:
            case Op.JMP:
                arg = (rng.randrange(8) << 5) | ((pc + rng.randint(2, 4)) & 31)
            case Op.WAIT:
                source = rng.randrange(3)
                arg = (rng.randrange(2) << 7) | (source << 5) | rng.randrange(8 if source == 2 else 6)
            case Op.IN:
                arg = (rng.choice((0, 1, 2, 3, 6, 7)) << 5) | rng.choice(counts)
            case Op.OUT:
                arg = (rng.choice((0, 1, 2, 3, 4, 6)) << 5) | rng.choice(counts)
            case Op.FIFO:
                arg = rng.randrange(8) << 5
            case Op.MOV:
                arg = ((rng.choice((0, 1, 2, 6, 7)) << 5) | (rng.randrange(3) << 3)
                       | rng.choice((0, 1, 2, 3, 5, 6, 7)))
            case Op.IRQ:
                arg = (rng.randrange(3) << 5) | rng.randrange(8)
            case Op.SET:
                dest = slot + 1 if slot < 2 else rng.choice((0, 1, 2, 4))
                arg = (dest << 5) | rng.randrange(32)
        timing = rng.choice((0, 0, 0, 1, 2, 3, 7, 31))
        side = rng.choice((None, 0, 1)) if sideset else None
        program[pc] = ins(op, arg, timing & (7 if sideset else 31), side)
    return program


@cocotb.test()
async def reference_randomized_dual_programs(dut):
    b = Bench(dut)
    first_seed = int(os.getenv("PIO_REF_SEED", "0x21c0ffee"), 0)
    seeds = int(os.getenv("PIO_REF_SEEDS", "16"))
    assert seeds > 0
    for seed in range(first_seed, first_seed + seeds):
        rng = random.Random(seed)
        b.case = f"seed={seed:#x} setup"
        b.inputs = rng.randrange(64)
        await b.reset()
        await b.write_word(OWNER, rng.randrange(4096))
        memories = []
        for engine in range(2):
            await b.write(SELECT, engine)
            entry = rng.choice((0, 1, 16, 30, 31))
            sideset = bool(rng.randrange(2))
            program = random_program(rng, entry, sideset)
            memories.append(program)
            await b.load(program)
            await b.write_word(EXEC, rng.randrange(1024) | (entry << 10) | (int(sideset) << 15))
            await b.write_word(DIVIDER, rng.choice((0, 1, 1, 2, 3, 5, 7)))
            await b.write_word(SHIFT, rng.randrange(16) | (rng.randrange(32) << 4) | (rng.randrange(32) << 9))
            await b.write_word(PIN, rng.getrandbits(32))
            route = (rng.getrandbits(27) | 1 | (rng.getrandbits(1) << 27)) if rng.randrange(2) else 0
            await b.write_word(ROUTE, route)
            for selector in (DIRS, OD, FILTER, TX, TX):
                await b.write_word(selector, rng.getrandbits(32))

        await b.write_word(GROUP, 3)
        assert all(engine.running for engine in b.model.engines)
        for index in range(32):
            b.case = f"seed={seed:#x} action={index}"
            b.inputs ^= rng.choice((0, 1, 2, 4, 8, 16, 32, 63))
            await b.idle(rng.randrange(1, 8))
            engine = rng.randrange(2)
            await b.write(SELECT, engine)
            action = rng.randrange(12)
            if action <= 1:
                await b.write_word(TX, rng.getrandbits(32))
            elif action <= 3:
                await b.read_word(RX)
            elif action == 4:
                await b.write_word(IRQ_SET, rng.randrange(256))
            elif action == 5:
                await b.write(IRQ, rng.randrange(256))
            elif action == 6:
                await b.read_word(rng.choice((0, 1, 2, 3, 4, 5, 0x15, 0x1d, 0x1e, 255)))
            elif action == 7:
                await b.write_word(GROUP, (1 << (engine + 2)) | (rng.randrange(4) << 8))
                await b.idle(rng.randrange(5))
                await b.write_word(GROUP, (1 << (engine + 4)) | (rng.randrange(4) << 10))
            elif action == 8:
                # Configuration and IMEM commits targeting a running bank are ignored.
                await b.write_word(PIN, rng.getrandbits(32))
                await b.load([rng.getrandbits(16)], rng.randrange(32))
                await b.write_word(OWNER, rng.getrandbits(12))
            elif action == 9:
                # Discard a partially captured byte on disable or RD+WR, then re-arm.
                address = rng.choice((STATUS, IRQ, DEBUG, SELECT))
                await b.step(address | 32)
                await b.step(address | 32)
                if rng.randrange(2):
                    await b.step(address | 32, ena=False)
                else:
                    await b.step(address | 48)
                await b.idle()
                await b.read(address)
            elif action == 10:
                await b.write(CONTROL, ABORT | rng.choice((0, FIFO_CLEAR, START, RESUME)))
                await b.write(CONTROL, START)
            else:
                # A fresh START of one running engine leaves the peer undisturbed.
                await b.write_word(GROUP, 1 << engine)
        b.case = f"seed={seed:#x} reset during staged IMEM write"
        await b.write_word(GROUP, 3 << 2)
        await b.write(IMEM_ADDR, 31)
        await b.write(IMEM_LO, 0xff)
        await b.stage_byte(IMEM_HI, 0xff)
        await b.step(IMEM_HI | 16, 15, rst_n=False)
        await b.idle()
        for engine in range(2):
            assert b.model.engines[engine].imem == memories[engine]
            await b.write(SELECT, engine)
            await b.write(IMEM_ADDR, 31)
            await b.read(IMEM_LO)
            await b.read(IMEM_HI)
    dut._log.info("Compared %d edges for %d seeds from %#x. Instruction attempts: %s",
                  b.edge, seeds, first_seed, dict(b.attempts))


@cocotb.test()
async def reference_maximum_divider_and_delay(dut):
    b = Bench(dut)
    b.case = "maximum divider rollover, including a disabled interval"
    await b.reset()
    e = b.model.engines[0]
    await b.write_word(DIVIDER, 65535)
    await b.load([ins(Op.SET, 0x21), ins(Op.SET, 0x42), HALT])
    await b.write(CONTROL, START)
    assert e.x == 1 and e.divider_left == 65534 and e.y == 0
    await b.idle(65533)
    await b.idle(4, ena=False)
    assert e.divider_left == 1
    await b.idle()
    assert e.divider_left == 0 and e.y == 0
    await b.idle()
    assert e.y == 2 and e.divider_left == 65534

    b.case = "maximum delay after a taken branch at wrap top"
    await b.reset()
    e = b.model.engines[0]
    await b.write_word(EXEC, (31 << 10) | (31 << 5) | 1)
    await b.load([ins(Op.JMP, 0, delay=31), ins(Op.SET, 0x27), HALT], start=31)
    await b.write(CONTROL, START)
    assert e.pc == 0 and e.delay_left == 31
    await b.idle(31)
    assert e.x == 0
    await b.idle()
    assert e.x == 7


@cocotb.test()
async def reference_legacy_route_side_set(dut):
    """Exact baseline counterexample. PIO_REF_STRICT=1 makes it a test error."""
    b = Bench(dut)
    b.case = "legacy SET PINDIRS clips at dedicated output 7"
    await b.reset()
    await b.write_word(PIN, 7 << 8)
    await b.load([ins(Op.SET, 0x9f), HALT])
    await b.write(CONTROL, START)
    assert b.model.engines[0].directions == 0

    b.case = "legacy side-set with ROUTE bit 27 set and extended routing disabled"
    await b.reset()
    await b.write_word(ROUTE, 1 << 27)
    await b.write_word(EXEC, 0x83e0)
    await b.load([ins(Op.MOV, 0x42, side=0), HALT])
    await b.stage_byte(CONTROL, START)
    await b.step(CONTROL | 16)
    await b.step(CONTROL, baseline_difference={"uo": (0, 1), "0.pins": (0xf00, 0xf01)})


@cocotb.test()
async def reference_live_resume_atomicity(dut):
    """Exact baseline counterexample. PIO_REF_STRICT=1 makes it a test error."""
    b = Bench(dut)
    b.case = "RESUME issued to a running engine on a PULL retirement edge"
    await b.reset()
    await b.load([NOP | 0x0200, ins(Op.FIFO, 0xa0), HALT])
    await b.write_word(TX, 0x12345678)
    await b.write(CONTROL, START)
    await b.stage_byte(CONTROL, RESUME)
    await b.step(CONTROL | 16, RESUME >> 4, baseline_difference={
        "0.osr": (0x12345678, 0), "0.out_count": (0, 32),
    })
    await b.reset()
