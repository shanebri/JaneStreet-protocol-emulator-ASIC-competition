"""Independently validate saved bridge packets without replaying side effects."""
from collections import Counter
from functools import reduce
from operator import xor

from bringup.transport import WIDE_REPLIES


def summarize(records):
    pending, chunks, previous = None, bytearray(), None
    ops, peers = Counter(), Counter()
    complete, tx_bytes, rx_bytes, written = 0, 0, 0, False
    result = dict(status='FAIL', completed_commands=0)
    try:
        for record in records:
            direction, data = record['direction'], record['data']
            if direction == 'tx':
                if pending is not None:
                    raise ValueError('new command before the preceding response completed')
                packet = bytes.fromhex(data)
                if (len(packet) != 8 or packet[0] != 0xc3 or reduce(xor, packet)
                        or packet[3] > 15 or packet[6]):
                    raise ValueError('invalid saved bridge request')
                if previous is not None and packet[1] != (previous+1) & 255:
                    raise ValueError('bridge sequence gap/retry in saved traffic')
                previous, pending, written = packet[1], packet, False
                chunks.clear()
                tx_bytes += len(packet)
                ops[str(packet[2])] += 1
            elif direction == 'tx_result':
                if pending is None or written or data != dict(bytes_sent=8, requested=8):
                    raise ValueError('missing/short/duplicate bridge write result')
                written = True
            elif direction == 'rx_chunk':
                if pending is None or not written:
                    raise ValueError('response bytes without a written request')
                chunk = bytes.fromhex(data)
                chunks.extend(chunk)
                rx_bytes += len(chunk)
                if len(chunks) > 8:
                    raise ValueError('response exceeds eight bytes')
            elif direction == 'rx':
                reply = bytes.fromhex(data)
                if pending is None or not written or reply != bytes(chunks):
                    raise ValueError('saved full reply differs from received chunks')
                if (len(reply) != 8 or reply[0] != 0xc3 or reply[1] != pending[1]
                        or reduce(xor, reply) or reply[2]
                        or (pending[2] not in WIDE_REPLIES and any(reply[4:7]))):
                    raise ValueError('corrupt/stale/rejected saved response')
                complete += 1
                pending = None
            elif direction == 'rx_timeout':
                if data['partial_hex'] != chunks.hex():
                    raise ValueError('timeout partial bytes differ from received chunks')
                raise ValueError('recorded response timeout; no replay is permitted')
            elif direction.endswith('_rx'):
                peers[direction] += len(bytes.fromhex(data))
        if pending is not None or not complete:
            raise ValueError('incomplete or empty bridge traffic')
        result['status'] = 'PASS'
    except (ValueError, KeyError, TypeError) as exc:
        result['error'] = str(exc)
    result.update(completed_commands=complete, requested_bytes=tx_bytes, received_bytes=rx_bytes,
                  opcodes=dict(ops), peer_received_bytes=dict(peers),
                  pending_request_hex=pending.hex() if pending else None, partial_reply_hex=chunks.hex() if pending else '')
    return result
