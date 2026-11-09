from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from streaming.usb_ls import crc16,symbols,inspect,J,K
from pioasm import assemble


class USBToolsTests(unittest.TestCase):
    def test_known_crc_and_sync(self):
        self.assertEqual(crc16(b''),0)
        self.assertEqual(crc16(b'123456789'),0xb4c8)
        words,packet=symbols(b'')
        self.assertEqual(packet['expected_states'][:8],[K,J,K,J,K,J,K,K])
        self.assertEqual(words[0],packet['symbols']-1)
        root=Path(__file__).resolve().parents[1]
        code=assemble((root/'examples/usb_ls_tx_symbols.asm').read_text())
        self.assertLessEqual(len(code),32)
        self.assertEqual([int(s,16) for s in (root/'examples/usb_ls_tx_symbols.hex').read_text().split()],code)

    def test_stuffing_and_quantization(self):
        words,packet=symbols(bytes([255])*8)
        self.assertGreaterEqual(packet['stuffed_bits'],10)
        commands=b''.join(w.to_bytes(4,'little') for w in words[1:])[:packet['symbols']]
        durations=[(x>>2)+5 for x in commands]
        self.assertEqual(set(durations),{33,34})
        self.assertEqual(sum(durations),packet['total_clocks'])

    def test_malformed_and_oversize_rejected(self):
        with self.assertRaises(ValueError):symbols(bytes(9))
        with self.assertRaises(ValueError):inspect([2]*100)


if __name__=='__main__':unittest.main()
