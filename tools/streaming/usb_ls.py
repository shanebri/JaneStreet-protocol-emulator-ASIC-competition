"""USB-LS digital DATA packet preparation and independent waveform inspection.

This is a laboratory timing prototype; it supplies no USB PHY or device stack.
"""
from fractions import Fraction

J,K,SE0=2,1,0


def crc16(payload):
    value=0xffff
    for byte in payload:
        value^=byte
        for _ in range(8):
            value=(value>>1) ^ (0xa001 if value&1 else 0)
    return value ^ 0xffff


def symbols(payload,*,data1=False):
    payload=bytes(payload)
    if len(payload)>8: raise ValueError('low-speed prototype payload is limited to eight bytes')
    packet=bytes((0x80,0x4b if data1 else 0xc3))+payload+crc16(payload).to_bytes(2,'little')
    bits=[];ones=0
    for byte in packet:
        for n in range(8):
            bit=(byte>>n)&1;bits.append(bit)
            ones=ones+1 if bit else 0
            if ones==6:
                bits.append(0);ones=0
    state=J;line=[]
    for bit in bits:
        if not bit: state=K if state==J else J
        line.append(state)
    line.extend((SE0,SE0,J))
    commands=[]
    for i,state in enumerate(line):
        duration=((i+1)*100)//3-(i*100)//3
        commands.append(((duration-5)<<2)|state)
    words=[len(commands)-1]
    words.extend(int.from_bytes(bytes(commands[i:i+4]).ljust(4,b'\0'),'little') for i in range(0,len(commands),4))
    return words,dict(symbols=len(line),stuffed_bits=len(bits)-len(packet)*8,
        total_clocks=(len(line)*100)//3,expected_states=line,
        payload_hex=payload.hex(),data1=data1,crc16=crc16(payload))


def inspect(samples):
    """Decode observed outputs at rational bit centers, independent of commands."""
    active=[i for i,s in enumerate(samples) if s&4]
    if not active: raise ValueError('missing TX marker')
    first=next((i for i in active if samples[i]&3==K),None)
    if first is None: raise ValueError('missing SOP')
    stop=next((i for i in range(first,len(samples)) if not samples[i]&4),None)
    if stop is None: raise ValueError('missing marker release')
    line=[]
    for n in range(200):
        center=first+((2*n+1)*100)//6
        if center>=stop: break
        line.append(samples[center]&3)
    if len(line)<35 or line[-3:]!=[SE0,SE0,J]: raise ValueError('bad EOP')
    # Check every sample, not only centers, against the rational symbol schedule.
    edge_errors=[]
    for n,state in enumerate(line):
        begin=first+(n*100)//3;end=first+((n+1)*100)//3
        if any((s&3)!=state for s in samples[begin:end]):
            raise ValueError('symbol duration/phase mismatch')
        edge_errors.append(float(Fraction((n*100)//3)-Fraction(n*100,3)))
    if stop-first!=(len(line)*100)//3: raise ValueError('packet duration mismatch')
    raw=[];previous=J
    for state in line[:-3]:
        if state not in (J,K): raise ValueError('invalid differential symbol')
        raw.append(int(state==previous));previous=state
    bits=[];ones=0
    for bit in raw:
        if ones==6:
            if bit: raise ValueError('bit stuffing error')
            ones=0;continue
        bits.append(bit);ones=ones+1 if bit else 0
    if ones==6: raise ValueError('missing final stuffed bit')
    if len(bits)%8: raise ValueError('non-byte packet')
    data=bytes(sum(bits[i+n]<<n for n in range(8)) for i in range(0,len(bits),8))
    if data[0]!=0x80: raise ValueError('bad SYNC')
    if data[1] not in (0xc3,0x4b): raise ValueError('bad DATA PID')
    payload=data[2:-2]
    # Polynomial division using a left-shifting register is deliberately separate
    # from the reflected packet-preparation implementation.
    remainder=0xffff
    for byte in payload:
        for n in range(8):
            feedback=((remainder>>15)^((byte>>n)&1))&1
            remainder=(remainder<<1)&0xffff
            if feedback: remainder^=0x8005
    reverse=int(f'{remainder:016b}'[::-1],2)^0xffff
    if int.from_bytes(data[-2:],'little')!=reverse: raise ValueError('CRC16 mismatch')
    return dict(payload_hex=payload.hex(),data1=data[1]==0x4b,symbols=len(line),
                first_symbol_clock=first,total_clocks=stop-first,
                edge_quantization_min_clocks=min(edge_errors),
                edge_quantization_max_clocks=max(edge_errors))
