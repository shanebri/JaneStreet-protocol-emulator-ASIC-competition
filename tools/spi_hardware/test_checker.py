"""Offline tests: framing damage and missing/incorrect endpoints must not pass."""
import unittest
from check_spi import FrameParser, Results


def packet(seq, rx=None, status=0):
    rx = seq ^ 0xa5 if rx is None else rx
    return bytes((0xa5, 0x5a, seq, seq, rx, status, 0xff ^ rx ^ status))


class CheckerTests(unittest.TestCase):
    def test_every_split_and_noise(self):
        for split in range(8):
            parser = FrameParser()
            data = packet(0xa5)
            records = parser.feed(b"noise" + data[:split]) + parser.feed(data[split:])
            self.assertEqual(records, [dict(sequence=0xa5, tx=0xa5, rx=0, status=0)])

    def test_checksum_damage(self):
        data = bytearray(packet(0))
        data[4] ^= 1
        with self.assertRaises(ValueError):
            FrameParser().feed(data)

    def test_two_complete_endpoints_required(self):
        result = Results()
        for n in range(256):
            result.accept_fpga(FrameParser().feed(packet(n))[0])
        self.assertFalse(result.complete)
        for n in range(256):
            result.accept_nano(f"RX {n} {n} {n ^ 0xa5} 1 1")
        self.assertFalse(result.complete)
        result.accept_nano("DONE 256 0")
        self.assertTrue(result.complete)

    def test_wrong_data_status_sequence_or_length(self):
        for data in (packet(0, rx=0), packet(1), packet(0, status=4)):
            with self.assertRaises(ValueError):
                Results().accept_fpga(FrameParser().feed(data)[0])
        for line in ("RX 0 1 165 1 1", "RX 0 0 165 2 1", "RX 1 1 164 1 1",
                     "DONE 256 0", "ERROR cs_active_reset_fpga_first"):
            with self.assertRaises(ValueError):
                Results().accept_nano(line)

    def test_duplicate(self):
        result = Results()
        record = FrameParser().feed(packet(0))[0]
        result.accept_fpga(record)
        with self.assertRaises(ValueError):
            result.accept_fpga(record)


if __name__ == "__main__":
    unittest.main()
