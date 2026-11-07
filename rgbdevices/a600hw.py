# SPDX-License-Identifier: GPL-3.0-or-later
"""Hardware access for the Corsair ONE a600 USB controllers (protocol: ../docs/corsair-a600-protocol.md).

Cooling controller 1b1c:0d27 and lighting controller 1b1c:0d18 (interface 2), both through
/dev/hidraw. Only commands seen from Corsair Dashboard are sent; curve uploads and the
flash commit are deliberately not implemented.
"""
import glob
import os
import select
import struct
import time

COOLING_HID_ID = "0003:00001B1C:00000D27"
LIGHTING_HID_ID = "0003:00001B1C:00000D18"
LIGHTING_INTERFACE = 2

MAX_FAN_RPM = 2100
# The pumps are not controllable and run at a fixed speed of about 3000 rpm.
PUMP_NOMINAL_RPM = 3000
FAN_CHANNELS = ["gpu1", "gpu2", "gpu3", "cpu1", "cpu2"]
MODES = {"quiet": 0, "balanced": 1}
MODE_NAMES = {0: "Quiet", 1: "Balanced", 2: "Custom"}

# Lighting effect codes, as Corsair Dashboard sends them.
EFFECTS = {
    "static": 0x03,
    "breathing": 0x04,
    "color_cycle": 0x02,
    "rainbow": 0x01,
    "starry_night": 0x0A,
    "strobing": 0x11,
}


def find_hidraw(hid_id, interface=None):
    for h in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(h, "device/uevent")) as f:
                if f"HID_ID={hid_id}" not in f.read():
                    continue
            if interface is not None:
                with open(os.path.join(h, "device/../bInterfaceNumber")) as f:
                    if int(f.read().strip(), 16) != interface:
                        continue
        except OSError:
            continue
        return "/dev/" + os.path.basename(h)
    return None


def _drain(fd):
    while select.select([fd], [], [], 0)[0]:
        os.read(fd, 64)


class Cooling:
    """Cooling controller: report ID 0x20 out, 0x21 in, 64-byte reports."""

    def __init__(self):
        self.fd = None
        self.path = None

    def open(self):
        self.path = find_hidraw(COOLING_HID_ID)
        if not self.path:
            raise OSError("cooling controller 1b1c:0d27 not found")
        self.fd = os.open(self.path, os.O_RDWR)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    @property
    def connected(self):
        return self.fd is not None

    def _transfer(self, payload):
        _drain(self.fd)
        os.write(self.fd, bytes([0x20]) + payload + bytes(64 - len(payload)))
        deadline = time.monotonic() + 1.0
        while (left := deadline - time.monotonic()) > 0:
            if not select.select([self.fd], [], [], left)[0]:
                break
            reply = os.read(self.fd, 64)
            if reply[:2] == bytes([0x21, payload[0]]):
                return reply
        raise OSError(f"no reply to cooling command {payload[0]:#04x}")

    def push_temps(self, gpu_c, cpu_c):
        self._transfer(temps_payload(gpu_c, cpu_c))

    def mode(self):
        reply = self._transfer(b"\x15")
        return reply[3] if len(reply) > 3 else 0

    def set_mode(self, mode):
        if mode not in MODES.values():
            raise ValueError("only Quiet or Balanced may be set")
        self._transfer(bytes([0x13, mode]))

    def status(self):
        """Returns ({channel: (target_rpm, actual_rpm)}, (pump_a_rpm, pump_b_rpm))."""
        return decode_status(self._transfer(b"\x01"))


def temps_payload(gpu_c, cpu_c):
    """Command 0x03: GPU temperature for fan channels 0-2, CPU temperature for 3-5."""
    for t in (gpu_c, cpu_c):
        if not 0 <= t <= 255:
            raise ValueError(f"temperature {t} out of range")
    return bytes([0x03, gpu_c, gpu_c, gpu_c, cpu_c, cpu_c, cpu_c])


def decode_status(reply):
    """Decode a `21 01` status reply (big-endian fields)."""
    if len(reply) < 44 or reply[:2] != b"\x21\x01":
        raise ValueError("not a status reply")
    fans = {}
    for i, name in enumerate(FAN_CHANNELS):
        _temp, _, target, actual = struct.unpack_from(">BBHH", reply, 4 + 6 * i)
        fans[name] = (target, actual)
    return fans, struct.unpack_from(">HH", reply, 40)


def lighting_packet(effect, brightness, r, g, b):
    """64-byte `01 83` set-state report for the lighting controller."""
    values = (effect, brightness, r, g, b)
    if not all(0 <= v <= 255 for v in values):
        raise ValueError("lighting values must be 0-255")
    packet = bytes([0x01, 0x83, 0x00, 0x00, 0x00, 0x13, 0x00, effect, brightness, 0x03, r, g, b])
    return packet + bytes(64 - len(packet))


class Lighting:
    """Lighting controller, interface 2: report ID 0x01, 64-byte reports. Opened per call."""

    @staticmethod
    def available():
        return find_hidraw(LIGHTING_HID_ID, LIGHTING_INTERFACE) is not None

    @staticmethod
    def set(effect, brightness, r, g, b):
        path = find_hidraw(LIGHTING_HID_ID, LIGHTING_INTERFACE)
        if not path:
            raise OSError("lighting controller 1b1c:0d18 not found")
        packet = lighting_packet(effect, brightness, r, g, b)
        fd = os.open(path, os.O_RDWR)
        try:
            os.write(fd, packet)
        finally:
            os.close(fd)
