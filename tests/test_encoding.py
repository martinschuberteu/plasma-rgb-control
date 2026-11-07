import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rgbdevices.asus_pg39wcdm import decode_read, encode_write, nearest_color_code  # noqa: E402
from rgbdevices.base import parse_color  # noqa: E402


class AsusEncoding(unittest.TestCase):
    def test_writes_match_tested_values(self):
        self.assertEqual(encode_write("strobing", 1), 0x0106)  # tested: Strobing R
        self.assertEqual(encode_write("rainbow", 0), 0x0002)
        self.assertEqual(encode_write("off", 0), 0x0000)

    def test_never_index_one(self):
        for effect in ("off", "rainbow", "color_cycle", "static", "breathing", "strobing"):
            self.assertNotEqual(encode_write(effect, 0) & 0xFF, 1)

    def test_decode_captured_reads(self):
        self.assertEqual(decode_read(0x0004), ("rainbow", 0, False))
        self.assertEqual(decode_read(0x0008), ("color_cycle", 0, False))
        self.assertEqual(decode_read(0x0110), ("static", 1, False))
        self.assertEqual(decode_read(0x0610), ("static", 6, False))
        self.assertEqual(decode_read(0x0120), ("breathing", 1, False))
        self.assertEqual(decode_read(0x0340), ("strobing", 3, False))
        self.assertEqual(decode_read(0x0142), ("strobing", 1, True))

    def test_nearest(self):
        self.assertIn(nearest_color_code(parse_color("#ff8000")), (1, 6))  # orange: R or Y
        self.assertEqual(nearest_color_code((255, 0, 0)), 1)
        self.assertEqual(nearest_color_code((20, 0, 255)), 3)
        self.assertEqual(nearest_color_code((0x3d, 0xae, 0xe9)), 4)  # KDE blue -> cyan
        self.assertEqual(nearest_color_code((255, 230, 0)), 6)


if __name__ == "__main__":
    unittest.main()
