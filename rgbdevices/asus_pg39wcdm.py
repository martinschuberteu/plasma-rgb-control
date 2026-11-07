"""ASUS ROG Swift OLED PG39WCDM rear logo (OSD "Aura RGB") via DDC/CI VCP 0xF2, using ddcutil.

Mapped on 2026-11-07 by changing the OSD and reading F2, then single test writes.

Read format:  high byte = colour (1 R, 2 G, 3 B, 4 C, 5 M, 6 Y),
              low byte  = effect bit (00 off, 04 rainbow, 08 colour cycle, 10 static,
                          20 breathing, 40 strobing); bit 0x02 set = Aura Sync on.
Write format: high byte = colour 1-6, low byte = effect INDEX
              (0 off, 2 rainbow, 3 colour cycle, 4 static, 5 breathing, 6 strobing).

DANGER: writing effect index 1 turned Aura Sync on, which darkened the logo and locked the
whole OSD menu until a factory reset. Index 1 and anything above 6 are refused here, and
writes are spaced out. The stand light (OSD "LIGHT IN MOTION") is not reachable this way.
ddcutil always reports "Verification failed" for F2 because the read and write formats
differ; this module verifies by decoding the read-back value instead.
"""
import re
import subprocess
import time

from .base import Device, Effect, State, nearest_by_hue, parse_color

VCP = "F2"
MIN_WRITE_GAP_S = 1.0

COLORS = {  # code: (hex, label, hue)
    1: ("#ff0000", "Red", 0),
    2: ("#00ff00", "Green", 120),
    3: ("#0000ff", "Blue", 240),
    4: ("#00ffff", "Cyan", 180),
    5: ("#ff00ff", "Magenta", 300),
    6: ("#ffff00", "Yellow", 60),
}
# effect id: (write index, read bit)
EFFECT_CODES = {
    "off": (0, 0x00),
    "rainbow": (2, 0x04),
    "color_cycle": (3, 0x08),
    "static": (4, 0x10),
    "breathing": (5, 0x20),
    "strobing": (6, 0x40),
}
SAFE_WRITE_INDEXES = {0, 2, 3, 4, 5, 6}
AURA_SYNC_BIT = 0x02


def encode_write(effect_id, color_code):
    index = EFFECT_CODES[effect_id][0]
    if index not in SAFE_WRITE_INDEXES:
        raise ValueError(f"refusing unsafe effect index {index}")
    if color_code not in range(0, 7):
        raise ValueError(f"colour code {color_code} out of range")
    return (color_code << 8) | index


def decode_read(value):
    """Returns (effect_id or None, colour code, aura_sync_on)."""
    low, high = value & 0xFF, (value >> 8) & 0xFF
    sync = bool(low & AURA_SYNC_BIT)
    bit = low & ~AURA_SYNC_BIT
    effect = next((e for e, (_i, b) in EFFECT_CODES.items() if b == bit), None)
    return effect, high, sync


def nearest_color_code(rgb):
    return nearest_by_hue(rgb, {code: hue for code, (_h, _l, hue) in COLORS.items()})


class AsusPG39WCDM(Device):
    def __init__(self, options=None):
        super().__init__(
            id="asus",
            name="ASUS PG39WCDM logo",
            effects=(
                Effect("off", "Off", False),
                Effect("static", "Static", True),
                Effect("breathing", "Breathing", True),
                Effect("strobing", "Strobing", True),
                Effect("color_cycle", "Colour cycle", False),
                Effect("rainbow", "Rainbow", False),
            ),
            palette={hx: label for hx, label, _hue in COLORS.values()},
            options=options or {},
        )
        self.model = self.options.get("model", "PG39WCDM")
        self._last_write = 0.0

    def _ddcutil(self, *args):
        cmd = ["ddcutil", "--model", self.model, *args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    def _read_raw(self):
        r = self._ddcutil("getvcp", VCP, "--brief")
        m = re.search(r"VCP F2 CNC x([0-9a-f]{2}) x([0-9a-f]{2}) x([0-9a-f]{2}) x([0-9a-f]{2})",
                      r.stdout, re.I)
        if not m:
            raise OSError(f"could not read F2: {(r.stdout + r.stderr).strip()[:200]}")
        return (int(m.group(3), 16) << 8) | int(m.group(4), 16)

    def available(self):
        try:
            self._read_raw()
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def read(self):
        effect, code, sync = decode_read(self._read_raw())
        uses = effect and self.effect(effect).uses_color
        color = COLORS[code][0] if uses and code in COLORS else None
        note = "Aura Sync is on (logo waits for Armoury Crate)" if sync else None
        return State(effect=effect, color=color, note=note)

    def apply(self, effect_id, color):
        eff = self.effect(effect_id)
        code = 0
        if eff.uses_color:
            code = nearest_color_code(parse_color(color or "red"))
        value = encode_write(effect_id, code)
        wait = MIN_WRITE_GAP_S - (time.monotonic() - self._last_write)
        if wait > 0:
            time.sleep(wait)
        self._ddcutil("setvcp", VCP, hex(value))  # "Verification failed" is expected
        self._last_write = time.monotonic()
        time.sleep(0.5)
        state = self.read()
        if state.effect != effect_id or (eff.uses_color and state.color != COLORS[code][0]):
            raise OSError(f"monitor reports {state.effect} {state.color} after writing {value:#06x}")
        return state
