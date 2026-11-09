"""Length-delimited streams and FIFO-safe batching over the public host API."""
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_BYTES = (6, 7, 9, 10)
MAX_BYTES = 65536


def payload_words(payload, protocol, *, packed=True):
    payload = bytes(payload)
    if not 1 <= len(payload) <= MAX_BYTES:
        raise ValueError('payload length must be 1..65536')
    if protocol not in ('uart', 'spi'):
        raise ValueError('protocol must be uart or spi')
    size = 4 if packed else 1
    result = []
    for start in range(0, len(payload), size):
        group = payload[start:start+size]
        if protocol == 'uart':
            result.append(int.from_bytes(group, 'little'))
        else:
            result.append(int.from_bytes(group.ljust(4, b'\0'), 'big'))
    return [len(payload)-1, *result]


def receive_bytes(words, length, *, packed=True):
    if not 1 <= length <= MAX_BYTES:
        raise ValueError('invalid receive length')
    width = 4 if packed else 1
    expected = (length+width-1)//width
    if len(words) != expected:
        raise ValueError('RX word count does not match declared length')
    result = bytearray()
    for word in words:
        size = min(width, length-len(result))
        if not 0 <= word < (1 << (8*size)):
            raise ValueError('RX tail has unexpected high bits')
        result.extend(word.to_bytes(size, 'big'))
    return bytes(result)


def program(protocol, *, packed=True):
    if protocol not in ('uart', 'spi'):
        raise ValueError('unknown protocol')
    text = (ROOT/'examples'/f'{protocol}_packed_stream.asm').read_text()
    if packed:
        return text
    if protocol == 'uart':
        return text.replace('pull ifempty block', 'pull block')
    # Length-aware byte-per-word control, with the existing SPI frame schedule.
    return '''.sideset
pull block side 0
mov y, osr side 0
out null, 32 side 0
frame: pull block side 0
mov isr, null side 0
set x, 7 side 0
set pins, 0 side 0 [3]
bits: out pins, 1 side 0 [3]
in pins, 1 side 1 [7]
jmp x--, bits side 0 [3]
set pins, 1 side 0
push block side 0
jmp y--, frame side 0
halt side 0
'''


async def configure(engine, protocol, divider, *, packed=True, uart_pin=0,
                    spi_mosi=4, spi_clock=5, spi_cs=6,ready_pin=None):
    from pioasm import assemble
    if not 1 <= divider <= 65535:
        raise ValueError('divider must be 1..65535')
    if protocol=='uart' and not 0<=uart_pin<8:
        raise ValueError('UART output must be 0..7')
    if protocol=='spi' and (any(not 0<=n<8 for n in (spi_mosi,spi_clock,spi_cs))
                            or len({spi_mosi,spi_clock,spi_cs})!=3):
        raise ValueError('SPI outputs must be three distinct pins 0..7')
    source=program(protocol,packed=packed)
    if ready_pin is not None:
        if protocol!='spi' or not 0<=ready_pin<6:
            raise ValueError('READY requires a SPI input index 0..5')
        source=source.replace('    set pins, 0 side 0 [3]',
            f'    wait 1, gpio, {ready_pin} side 0\n    set pins, 0 side 0 [3]')
        if f'wait 1, gpio, {ready_pin}' not in source:
            raise ValueError('READY insertion point absent from program')
    words = assemble(source)
    if len(words) > 32:
        raise ValueError('program exceeds IMEM')
    await engine.write(0, 2 | 4 | 8)
    async with engine.transaction() as bus:
        await bus.write(2, 0)
        for word in words:
            await bus.write(3, word & 255)
            await bus.write(4, word >> 8)
    if protocol == 'uart':
        config = ((4,1<<uart_pin),(0x10,3),(0x11,0x03e0),
                  (0x12,uart_pin | (1<<3) | (uart_pin<<8) | (1<<11)))
    else:
        config = ((4,1<<spi_cs),(0x10,0),(0x11,0x83e0),
                  (0x12,spi_mosi | (1<<3) | (spi_cs<<8) | (1<<11) | (spi_clock<<17)))
    for selector,value in (*config,(0x13,divider)):
        await engine.write_word(selector,value)


@dataclass
class Stream:
    engine: object
    protocol: str
    payload: bytes
    packed: bool = True
    fifo_depth: int = 4
    tx_index: int = 0
    rx_words: list = field(default_factory=list)
    tx: list = field(init=False)
    service_calls: int = 0
    selector_writes: int = 0
    level_reads: int = 0
    data_reads: int = 0
    data_writes: int = 0

    def __post_init__(self):
        self.payload = bytes(self.payload)
        self.tx = payload_words(self.payload,self.protocol,packed=self.packed)
        if self.fifo_depth not in (4,8):
            raise ValueError('unsupported FIFO depth')

    @property
    def expected_rx_words(self):
        return 0 if self.protocol == 'uart' else (len(self.payload)+(3 if self.packed else 0))//(4 if self.packed else 1)

    @property
    def all_transferred(self):
        return self.tx_index == len(self.tx) and len(self.rx_words) == self.expected_rx_words

    async def service(self, *, batch=True, drain_rx=True):
        """One atomic bank visit, using conservative occupancy observed on entry."""
        async with self.engine.transaction() as bus:
            level = await bus.read(11)
            self.level_reads += 1
            tx_level,rx_level = level & 15,level >> 4
            if tx_level > self.fifo_depth or rx_level > self.fifo_depth:
                raise ValueError('FIFO capacity/count mismatch')
            reads = min(rx_level,self.expected_rx_words-len(self.rx_words)) if drain_rx else 0
            writes = min(self.fifo_depth-tx_level,len(self.tx)-self.tx_index)
            if not batch:
                reads,writes = min(reads,1),min(writes,1)
            if reads:
                await bus.write(5,9); self.selector_writes += 1
                for _ in range(reads):
                    value = 0
                    for i,address in enumerate(DATA_BYTES):
                        value |= (await bus.read(address)) << (8*i)
                    self.rx_words.append(value); self.data_reads += 1
            if writes:
                await bus.write(5,8); self.selector_writes += 1
                for _ in range(writes):
                    value = self.tx[self.tx_index]
                    for i,address in enumerate(DATA_BYTES):
                        await bus.write(address,(value>>(8*i)) & 255)
                    self.tx_index += 1; self.data_writes += 1
            self.service_calls += 1
        return reads,writes

    def received(self):
        return receive_bytes(self.rx_words,len(self.payload),packed=self.packed)

    def statistics(self):
        return dict(service_calls=self.service_calls,selector_writes=self.selector_writes,
                    level_reads=self.level_reads,data_reads=self.data_reads,data_writes=self.data_writes,
                    payload_bytes=len(self.payload),packed=self.packed)
