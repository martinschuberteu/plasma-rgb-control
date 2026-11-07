"""Minimal Logitech HID++ 2.0 over /dev/hidraw (enough for lighting).

Framing (from Solaar base.py): short report 0x10 = 7 bytes, long report 0x11 = 20 bytes,
[report_id, device_index, feature_index, (function << 4) | sw_id, params...].
Wired devices use device index 0xFF; devices on a receiver use their slot (1-6).
Error reply: [0x10/0x11, dev, 0xFF, feature_index, fn|sw, error_code].
"""
import glob
import os
import select
import time

SW_ID = 0x0B
LONG, SHORT = 0x11, 0x10

ERRORS = {1: "unknown", 2: "invalid argument", 3: "out of range", 4: "hardware error",
          5: "logitech error", 6: "invalid feature index", 7: "invalid function", 8: "busy",
          9: "unsupported"}

# Feature ids
ROOT = 0x0000
FEATURE_SET = 0x0001
DEVICE_NAME = 0x0005
COLOR_LED_EFFECTS = 0x8070
RGB_EFFECTS = 0x8071
PER_KEY_LIGHTING = 0x8081
BRIGHTNESS = 0x8040


class HidppError(OSError):
    pass


def find_hidraw(vid_pid, interface=None, name_contains=None):
    """vid_pid like '046D:C33F'. Returns all matching /dev/hidrawN paths."""
    vid, pid = vid_pid.upper().split(":")
    hid_id = f"0003:0000{vid}:0000{pid}"
    out = []
    for h in sorted(glob.glob("/sys/class/hidraw/hidraw*"), key=lambda p: int(p.rsplit("hidraw", 1)[1])):
        try:
            with open(os.path.join(h, "device/uevent")) as f:
                ev = f.read()
            if f"HID_ID={hid_id}" not in ev:
                continue
            if name_contains and name_contains not in ev:
                continue
            if interface is not None:
                with open(os.path.join(h, "device/../bInterfaceNumber")) as f:
                    if int(f.read().strip(), 16) != interface:
                        continue
        except OSError:
            continue
        out.append("/dev/" + os.path.basename(h))
    return out


class Hidpp:
    def __init__(self, path, device_index=0xFF):
        self.path = path
        self.dev = device_index
        self.fd = None
        self._features = {}

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR)
        return self

    def __exit__(self, *exc):
        os.close(self.fd)
        self.fd = None

    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 64)

    def request(self, feature_index, function, params=b"", timeout=1.0):
        params = bytes(params)
        if len(params) > 16:
            raise ValueError("params too long")
        report = bytes([LONG, self.dev, feature_index, (function << 4) | SW_ID]) + params
        report += bytes(20 - len(report))
        self._drain()
        os.write(self.fd, report)
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            if not select.select([self.fd], [], [], left)[0]:
                break
            r = os.read(self.fd, 64)
            if len(r) < 4 or r[0] not in (SHORT, LONG) or r[1] != self.dev:
                continue
            if r[2] == 0xFF and r[3] == feature_index and r[4] == ((function << 4) | SW_ID):
                code = r[5]
                raise HidppError(f"HID++ error {code} ({ERRORS.get(code, '?')}) "
                                 f"for feature index {feature_index:#04x} fn {function}")
            if r[2] == feature_index and r[3] == ((function << 4) | SW_ID):
                return r[4:]
        raise HidppError(f"no HID++ reply from {self.path} dev {self.dev:#04x}")

    def feature_index(self, feature_id):
        """IRoot getFeature. Returns the index, or None if the device lacks the feature."""
        if feature_id not in self._features:
            r = self.request(0x00, 0, bytes([feature_id >> 8, feature_id & 0xFF]))
            self._features[feature_id] = r[0] or None
        return self._features[feature_id]

    def protocol_version(self):
        r = self.request(0x00, 1, b"\x00\x00\x5a")
        return r[0], r[1]

    def name(self):
        idx = self.feature_index(DEVICE_NAME)
        if not idx:
            return None
        length = self.request(idx, 0)[0]
        name = b""
        while len(name) < length:
            name += self.request(idx, 1, bytes([len(name)]))[: length - len(name)]
        return name.decode(errors="replace")
