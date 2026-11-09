"""Independent executable specification of the dual PIO 0x21 digital ISA.

The contracts in docs/isa.md, docs/info.md and docs/dual_pio.md define the
expected results. This module only uses the Python standard library. It can
run a single Engine at the byte/word boundary or a Chip from pin samples.
"""

from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum


U32 = (1 << 32) - 1
FIFO_DEPTH = 4
DATA_BYTES = (6, 7, 9, 10)
START, STOP, FIFO_CLEAR, CLEAR_ERRORS, RESUME, ABORT = (1 << n for n in range(6))


class Op(IntEnum):
    JMP = 0
    WAIT = 1
    IN = 2
    OUT = 3
    FIFO = 4
    MOV = 5
    IRQ = 6
    SET = 7


def bits(value: int, first: int, width: int) -> int:
    return (value >> first) & ((1 << width) - 1)


@dataclass(frozen=True)
class Instruction:
    word: int
    sideset: bool = False

    @property
    def op(self):
        return Op(self.word >> 13)

    @property
    def arg(self):
        return self.word & 255

    @property
    def legal(self):
        arg = self.arg
        selector = arg >> 5
        match self.op:
            case Op.WAIT:
                source = selector & 3
                return source < 3 and (arg & 31) < (8 if source == 2 else 6)
            case Op.IN:
                return selector in (0, 1, 2, 3, 6, 7)
            case Op.FIFO:
                return (arg & 31) == 0
            case Op.MOV:
                return selector != 3 and bits(arg, 3, 2) != 3 and (arg & 7) != 4
            case Op.IRQ:
                return arg == 0x80 or (arg < 0x60 and (arg & 0x18) == 0)
            case Op.SET:
                return selector in (0, 1, 2, 4)
            case _:
                return True

    @property
    def delay(self):
        return bits(self.word, 8, 3 if self.sideset else 5)

    @property
    def side(self):
        if self.sideset and self.word & 0x1000:
            return bits(self.word, 11, 1)
        return None


@dataclass
class Outcome:
    """Instruction effects computed from pre-edge state, then committed atomically."""

    stall: str | None = None
    fault: bool = False
    halt: bool = False
    registers: dict[str, int] = field(default_factory=dict)
    target: int | None = None
    inject: int | None = None
    pop_tx: bool = False
    push_rx: int | None = None
    irq_set: int = 0
    irq_clear: int = 0
    begin_irq_wait: bool = False
    debug: int = 0


# Selector to state attribute and the bits accepted on stopped-state writes.
CONFIG = {
    0: ("x", U32), 1: ("y", U32), 2: ("osr", U32), 3: ("isr", U32),
    4: ("pins", 0xfff), 0x10: ("shiftctrl", 0x3fff), 0x11: ("execctrl", 0xffff),
    0x12: ("pinctrl", 0x1f7f7f), 0x13: ("divider", 0xffff),
    0x16: ("route", 0xfffffff), 0x17: ("directions", 0xf00),
    0x18: ("open_drain", 0xf00), 0x19: ("filter_enable", 15),
}


@dataclass
class Engine:
    """One engine. Directions and open drain use physical output bits 8–11."""

    imem: list[int | None] = field(default_factory=lambda: [None] * 32)
    pc: int = 0
    running: bool = False
    fault: bool = False
    x: int = 0
    y: int = 0
    osr: int = 0
    isr: int = 0
    out_count: int = 32
    in_count: int = 0
    pins: int = 0xf01
    directions: int = 0
    open_drain: int = 0
    filter_enable: int = 0
    shiftctrl: int = 3
    execctrl: int = 0x03e0
    pinctrl: int = 0
    route: int = 0
    divider: int = 1
    divider_left: int = 0
    delay_left: int = 0
    pending_exec: int | None = None
    irq_waiting: bool = False
    irq: int = 0
    debug: int = 0
    tx: deque[int] = field(default_factory=deque)
    rx: deque[int] = field(default_factory=deque)
    last_attempt: tuple[Instruction, bool, Outcome] | None = field(default=None, init=False)

    def read_imem(self, address):
        word = self.imem[address]
        if word is None:
            raise ValueError(f"Instruction memory at {address} has not been loaded")
        return word

    @property
    def levels(self):
        return len(self.tx) | (len(self.rx) << 4)

    def read_word(self, selector):
        if selector in CONFIG:
            value = getattr(self, CONFIG[selector][0])
            return value | 255 if selector == 0x17 else value
        return {
            5: self.out_count | (self.in_count << 8),
            9: self.rx[0] if self.rx else 0,
            0x14: self.irq,
            0x15: self.levels,
        }.get(selector, 0)

    def status(self, inputs):
        blocked = self.running and (self.delay_left or self.evaluate(self.instruction(), inputs).stall)
        flags = (self.running, blocked, self.fault, len(self.tx) == FIFO_DEPTH,
                 not self.rx, self.irq)
        return sum(bool(flag) << index for index, flag in enumerate(flags)) | ((self.debug & 3) << 6)

    def instruction(self):
        word = self.pending_exec if self.pending_exec is not None else self.read_imem(self.pc)
        return Instruction(word, bool(self.execctrl & 0x8000))

    @property
    def extended(self):
        return bool(self.route & 1)

    def _input_base(self):
        return bits(self.route, 17, 3) if self.extended else bits(self.pinctrl, 16, 1)

    def _map_output(self, value, immediate, directions):
        if self.extended:
            base = bits(self.route, 9 if immediate else 1, 4)
            width = bits(self.route, 13 if immediate else 5, 4)
            capacity = 12
        else:
            base = bits(self.pinctrl, 8 if immediate else 0, 3)
            width = bits(self.pinctrl, 11 if immediate else 3, 4)
            capacity = 8
        width = min(width or capacity, capacity)
        mask = (((1 << width) - 1) << base) & ((1 << capacity) - 1)
        if directions:
            mask &= 0xf00
        old = self.directions if directions else self.pins
        return (old & ~mask) | ((value << base) & mask)

    def _destination(self, effects, op, dest, value, width):
        if dest == 0 or (dest == 4 and op != Op.MOV):
            attribute = "pins" if dest == 0 else "directions"
            effects.registers[attribute] = self._map_output(value, op == Op.SET, dest == 4)
        elif dest in (1, 2):
            effects.registers["x" if dest == 1 else "y"] = value
        elif dest == 5:
            effects.target = value & 31
        elif dest == 6:
            effects.registers.update(isr=value, in_count=width if op == Op.OUT else 0)
        elif op == Op.MOV and dest == 7:
            effects.registers.update(osr=value, out_count=0)
        elif (op, dest) in ((Op.MOV, 4), (Op.OUT, 7)):
            effects.inject = value & 0xffff

    def evaluate(self, instruction: Instruction, inputs: int, host_rx_pop: bool = False) -> Outcome:
        """Interpret one attempted instruction without mutating architectural state."""
        if not instruction.legal:
            return Outcome(fault=True)
        op, arg = instruction.op, instruction.arg
        if op == Op.IRQ and arg == 0x80:
            return Outcome(halt=True)

        result = Outcome()
        selector, operand = arg >> 5, arg & 31
        width = operand or 32
        osr_empty = self.out_count >= (bits(self.shiftctrl, 4, 5) or 32)
        push_threshold = bits(self.shiftctrl, 9, 5) or 32
        rx_room = len(self.rx) < FIFO_DEPTH or host_rx_pop
        relative = inputs >> self._input_base()
        sources = (relative, self.x, self.y, 0, 0, self.levels, self.isr, self.osr)

        match op:
            case Op.JMP:
                jump = bits(self.route, 24, 3) if self.extended else bits(self.pinctrl, 20, 1)
                conditions = (True, self.x == 0, self.x != 0, self.y == 0, self.y != 0,
                              self.x != self.y, bits(inputs, jump, 1), not osr_empty)
                if conditions[selector]:
                    result.target = operand
                if selector in (2, 4):
                    name = "x" if selector == 2 else "y"
                    result.registers[name] = (getattr(self, name) - 1) & U32
            case Op.WAIT:
                source = selector & 3
                polarity = arg >> 7
                if bits((inputs, relative, self.irq)[source], operand, 1) != polarity:
                    result.stall = ("gpio", "pin", "wait_irq")[source]
                elif source == 2 and polarity:
                    result.irq_clear = 1 << operand
            case Op.IN:
                low = sources[selector] & ((1 << width) - 1)
                if self.shiftctrl & 2:
                    value = (self.isr >> width) | (low << (32 - width))
                else:
                    value = ((self.isr << width) | low) & U32
                count = min(self.in_count + width, 32)
                if self.shiftctrl & 8 and count >= push_threshold:
                    if not rx_room:
                        return Outcome(stall="autopush")
                    result.push_rx = value
                    value, count = 0, 0
                result.registers.update(isr=value, in_count=count)
            case Op.OUT:
                refill = bool(self.shiftctrl & 4 and osr_empty)
                if refill and not self.tx:
                    return Outcome(stall="autopull")
                word, count = (self.tx[0], 0) if refill else (self.osr, self.out_count)
                if self.shiftctrl & 1:
                    value, remainder = word & ((1 << width) - 1), word >> width
                else:
                    value, remainder = word >> (32 - width), (word << width) & U32
                result.pop_tx = refill
                result.registers.update(osr=remainder, out_count=min(count + width, 32))
                self._destination(result, op, selector, value, width)
            case Op.FIFO:
                pull, conditional, block = (bool(arg & mask) for mask in (128, 64, 32))
                if pull and (not conditional or osr_empty):
                    if block and not self.tx:
                        return Outcome(stall="pull")
                    result.pop_tx = bool(self.tx)
                    result.registers.update(osr=self.tx[0] if self.tx else self.x, out_count=0)
                    result.debug = 0 if self.tx else 8
                elif not pull and (not conditional or self.in_count >= push_threshold):
                    if block and not rx_room:
                        return Outcome(stall="push")
                    result.push_rx = self.isr if rx_room else None
                    result.registers.update(isr=0, in_count=0)
                    result.debug = 0 if rx_room else 4
            case Op.MOV:
                value = sources[arg & 7]
                operation = bits(arg, 3, 2)
                if operation == 1:
                    value ^= U32
                elif operation == 2:
                    value = int(f"{value:032b}"[::-1], 2)
                self._destination(result, op, selector, value, width)
            case Op.IRQ:
                mask = 1 << (arg & 7)
                if arg & 64:
                    result.irq_clear = mask
                elif arg & 32:
                    if not self.irq_waiting:
                        result.begin_irq_wait = True
                        result.irq_set = mask
                    if result.begin_irq_wait or self.irq & mask:
                        result.stall = "irq_ack"
                else:
                    result.irq_set = mask
            case Op.SET:
                self._destination(result, op, selector, operand, width)
        return result

    def _side_set(self, value):
        if value is None:
            return
        pin = bits(self.route, 20, 4) if self.extended else bits(self.pinctrl, 17, 3)
        direction = self.extended and bool(self.route & (1 << 27))
        if pin < 12 and (not direction or pin >= 8):
            name = "directions" if direction else "pins"
            setattr(self, name, (getattr(self, name) & ~(1 << pin)) | (value << pin))

    def step(self, inputs: int = 0, *, enabled: bool = True, control: int = 0,
             word_write: tuple[int, int] | None = None, irq_clear: int = 0,
             debug_clear: int = 0, rx_read: bool = False) -> None:
        """Advance one edge. Live host effects and CPU attempts use old FIFO/IRQ state."""
        self.last_attempt = None
        was_running = self.running
        selector, value = word_write if word_write is not None else (-1, 0)
        stop = bool(control & (STOP | ABORT))
        clear_fifos = bool(control & FIFO_CLEAR and (stop or not was_running))
        tx_push = selector == 8
        host_irq_set = value & 255 if selector == 0x14 else 0
        effects = Outcome()

        if stop:
            self.running = False
            if control & ABORT:
                self.directions = 0
        elif control & START:
            self.running, self.fault = True, False
            self.pc = bits(self.execctrl, 10, 5)
            self.x = self.y = self.isr = self.osr = 0
            self.out_count, self.in_count = 32, 0
            self.divider_left = self.delay_left = 0
            self.pending_exec, self.irq_waiting = None, False
        elif not was_running:
            self.running = bool(control & RESUME and not self.fault)
        elif enabled:
            if self.divider_left:
                self.divider_left -= 1
            else:
                self.divider_left = self.divider - 1
                if self.delay_left:
                    self.delay_left -= 1
                else:
                    instruction = self.instruction()
                    injected = self.pending_exec is not None
                    effects = self.evaluate(instruction, inputs, rx_read)
                    self.last_attempt = instruction, injected, effects
                    if effects.fault:
                        self.running, self.fault = False, True
                    else:
                        if effects.halt:
                            self.running = False
                        elif effects.stall:
                            self.irq_waiting |= effects.begin_irq_wait
                        else:
                            for name, result in effects.registers.items():
                                setattr(self, name, result)
                            if effects.target is not None:
                                self.pc = effects.target
                            elif not injected:
                                top, bottom = bits(self.execctrl, 5, 5), self.execctrl & 31
                                self.pc = bottom if self.pc == top else (self.pc + 1) & 31
                            self.pending_exec = effects.inject
                            self.irq_waiting = False
                            self.delay_left = instruction.delay
                        self._side_set(instruction.side)

        if not was_running and selector in CONFIG:
            name, mask = CONFIG[selector]
            setattr(self, name, ((value & mask) or 1) if name == "divider" else value & mask)
            if name == "osr":
                self.out_count = 0
            elif name == "isr":
                self.in_count = 0

        self.irq = ((self.irq & ~irq_clear) | host_irq_set | effects.irq_set) & ~effects.irq_clear
        self.debug &= ~(15 if control & CLEAR_ERRORS else debug_clear & 15)
        if clear_fifos:
            self.tx.clear()
            self.rx.clear()
        else:
            if effects.pop_tx:
                self.tx.popleft()
            if tx_push:
                if len(self.tx) == FIFO_DEPTH:
                    self.debug |= 1
                else:
                    self.tx.append(value)
            if rx_read:
                if self.rx:
                    self.rx.popleft()
                else:
                    self.debug |= 2
            if effects.push_rx is not None:
                self.rx.append(effects.push_rx)
            self.debug |= effects.debug


@dataclass
class Bank:
    imem_address: int = 0
    imem_low: int = 0
    selector: int = 0
    stage: int = 0
    snapshot: int = 0


@dataclass
class Transport:
    """Low-nibble-first host framing and byte capture."""

    armed: bool = False
    pending: tuple[int, int] | None = None
    low: int = 0
    captured: int = 0
    output: int = 0
    valid_read: bool = False

    def step(self, ui, nibble, read_byte):
        address, strobe = ui & 15, bits(ui, 4, 2)
        if self.pending is not None:
            previous_address, previous_strobe = self.pending
            if address != previous_address or (strobe and strobe != previous_strobe):
                self.pending = None
        if strobe == 3:
            self.armed, self.valid_read, self.pending = False, False, None
        elif strobe == 0:
            self.armed, self.valid_read = True, False
        elif self.armed:
            high = self.pending is not None
            self.pending = None if high else (address, strobe)
            self.armed = False
            if strobe == 1:
                if high:
                    return self.low | (nibble << 4)
                self.low = nibble
            else:
                if not high:
                    self.captured = read_byte(address)
                self.output = bits(self.captured, 4 if high else 0, 4)
                self.valid_read = True
        return None


@dataclass(frozen=True)
class Pins:
    uo: int
    uio_out: int
    uio_oe: int


@dataclass
class Chip:
    """Dual-engine PIO, shared input qualification, host transport and pad boundary."""

    engines: tuple[Engine, Engine] = field(default_factory=lambda: (Engine(), Engine()))
    banks: tuple[Bank, Bank] = field(default_factory=lambda: (Bank(), Bank()))
    selected: int = 0
    owner: int = 0
    transport: Transport = field(default_factory=Transport)
    sync: int = 0
    qualified: int = 0
    _input_delay: int = 0
    _history: deque[int] = field(default_factory=lambda: deque([0] * 4, maxlen=4))

    def inputs(self, index):
        mask = self.engines[index].filter_enable << 2
        return (self.sync & ~mask) | ((self.qualified << 2) & mask)

    def read_word(self, selector):
        if selector == 0x1d:
            a, b = self.engines
            return a.status(self.inputs(0)) | (b.status(self.inputs(1)) << 8) | (a.irq << 16) | (b.irq << 24)
        common = {0x1a: 0x50490102, 0x1b: self.owner, 0x1c: 0, 0x1e: self.selected}
        if selector in common:
            return common[selector]
        return self.engines[self.selected].read_word(selector)

    def pins(self, ui: int = 0, *, ena: bool = True, rst_n: bool = True) -> Pins:
        a, b = self.engines
        value = (a.pins & ~self.owner) | (b.pins & self.owner)
        dirs = (a.directions & ~self.owner) | (b.directions & self.owner)
        od = (a.open_drain & ~self.owner) | (b.open_drain & self.owner)
        protocol_oe = (dirs & ~(od & value)) >> 4 if rst_n else 0
        host_read = bits(ui, 4, 2) == 2 and ena and rst_n
        host_oe = 15 if host_read and (self.transport.armed or self.transport.valid_read) else 0
        return Pins(value & 255, ((value & ~od & 0xf00) >> 4) | self.transport.output,
                    protocol_oe | host_oe)

    def step(self, ui: int = 0, uio: int = 0, *, ena: bool = True, rst_n: bool = True) -> Pins:
        """Sample external pins at a rising edge and return settled output pins."""
        if not rst_n:
            self.__init__(engines=(Engine(imem=self.engines[0].imem), Engine(imem=self.engines[1].imem)))
            return self.pins(ui, ena=ena, rst_n=rst_n)

        index = self.selected
        engine, bank = self.engines[index], self.banks[index]
        events = [{}, {}]

        def read_byte(address):
            if address == 1:
                return engine.status(self.inputs(index))
            if address == 2:
                return bank.imem_address
            if address in (3, 4):
                return bits(engine.read_imem(bank.imem_address), (address - 3) * 8, 8)
            if address == 5:
                return bank.selector
            if address in DATA_BYTES:
                if address == 6:
                    bank.snapshot = self.read_word(bank.selector)
                    events[index]["rx_read"] = bank.selector == 9
                return bits(bank.snapshot, DATA_BYTES.index(address) * 8, 8)
            return {8: engine.pc, 11: engine.levels, 12: engine.irq, 13: engine.debug,
                    14: self.inputs(index), 15: 0x21}.get(address, 0)

        if ena:
            byte = self.transport.step(ui, uio & 15, read_byte)
            if byte is not None:
                address = ui & 15
                if address == 0:
                    events[index]["control"] = byte
                elif address == 2:
                    bank.imem_address = byte & 31
                elif address == 3 and not engine.running:
                    bank.imem_low = byte
                elif address == 4 and not engine.running:
                    engine.imem[bank.imem_address] = bank.imem_low | (byte << 8)
                    bank.imem_address = (bank.imem_address + 1) & 31
                elif address == 5:
                    bank.selector = byte
                elif address in DATA_BYTES[:-1]:
                    shift = DATA_BYTES.index(address) * 8
                    bank.stage = (bank.stage & ~(255 << shift)) | (byte << shift)
                elif address == 10:
                    self._write_word(bank.selector, bank.stage | (byte << 24), events)
                elif address == 12:
                    events[index]["irq_clear"] = byte
                elif address == 13:
                    events[index]["debug_clear"] = byte
                elif address == 15 and byte < 2:
                    self.selected = byte
        else:
            self.transport = Transport()

        for index, engine in enumerate(self.engines):
            engine.step(self.inputs(index), enabled=ena, **events[index])
        self._history.append(self.sync >> 2)
        for pin in range(4):
            mask = 1 << pin
            levels = [sample & mask for sample in self._history]
            if all(levels):
                self.qualified |= mask
            elif not any(levels):
                self.qualified &= ~mask
        self.sync, self._input_delay = self._input_delay, ((uio >> 4) << 2) | (ui >> 6)
        return self.pins(ui, ena=ena, rst_n=rst_n)

    def _write_word(self, selector, value, events):
        if selector == 0x1b:
            a, b = self.engines
            changing = (self.owner ^ value) & (a.directions | b.directions)
            if not (a.running or b.running or changing):
                self.owner = value & 0xfff
        elif selector == 0x1c:
            for index in range(2):
                commands = (START, STOP, RESUME, ABORT, FIFO_CLEAR, CLEAR_ERRORS)
                events[index]["control"] = sum(command for pos, command in enumerate(commands)
                                                if value & (1 << (2 * pos + index)))
        elif selector not in (0x1a, 0x1d, 0x1e):
            events[self.selected]["word_write"] = selector, value
