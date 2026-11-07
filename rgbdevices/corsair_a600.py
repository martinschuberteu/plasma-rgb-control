"""Corsair ONE a600 front light strips (lighting controller 1b1c:0d18, interface 2).

Reuses a600hw.py from the corsair-one-a600-linux project for device lookup and the set-state
packet. Reading the state (`01 81`) is done here; see that project's protocol-notes.md.

The CoolerControl corsair-a600 plugin also drives this controller. It re-applies its own last
lighting setting only when its brightness setting changes, or when CoolerControl sends it a
lighting command (e.g. from the CoolerControl UI). Otherwise the colour set here stays.
"""
import importlib.util
import os
import select
import time

from .base import Device, Effect, State, hex_color, parse_color

A600HW_CANDIDATES = [
    "/home/martin/Documents/Claude/Corsair One/coolercontrol-plugin/corsair-a600/a600hw.py",
    "/var/lib/coolercontrol/plugins/corsair-a600/a600hw.py",
]


def load_a600hw(path=None):
    for p in ([path] if path else []) + A600HW_CANDIDATES:
        if p and os.path.isfile(p):
            spec = importlib.util.spec_from_file_location("a600hw", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("a600hw.py not found (set corsair.a600hw in config.json)")


class CorsairA600(Device):
    def __init__(self, options=None):
        super().__init__(
            id="corsair",
            name="Corsair ONE a600",
            effects=(
                Effect("off", "Off", False),
                Effect("static", "Static", True),
                Effect("breathing", "Breathing (colour-changing)", False),
                Effect("strobing", "Strobing", False),
                Effect("color_cycle", "Colour cycle", False),
                Effect("rainbow", "Rainbow", False),
                Effect("starry_night", "Starry night", False),
            ),
            palette=None,
            options=options or {},
        )
        self.hw = load_a600hw(self.options.get("a600hw"))
        self.brightness_pct = int(self.options.get("brightness", 100))

    def _path(self):
        return self.hw.find_hidraw(self.hw.LIGHTING_HID_ID, self.hw.LIGHTING_INTERFACE)

    def available(self):
        return self._path() is not None

    def read(self):
        path = self._path()
        if not path:
            raise OSError("lighting controller 1b1c:0d18 not found")
        fd = os.open(path, os.O_RDWR)
        try:
            self.hw._drain(fd)
            os.write(fd, bytes([0x01, 0x81]) + bytes(62))
            deadline = time.monotonic() + 1.0
            while (left := deadline - time.monotonic()) > 0:
                if not select.select([fd], [], [], left)[0]:
                    break
                r = os.read(fd, 64)
                if r[:2] == b"\x01\x81" and len(r) >= 13:
                    return self._decode(r)
        finally:
            os.close(fd)
        raise OSError("no reply to lighting read-state")

    def _decode(self, r):
        code, brightness, rgb = r[6], r[8], tuple(r[10:13])
        by_code = {v: k for k, v in self.hw.EFFECTS.items()}
        effect = by_code.get(code)
        if brightness == 0:
            return State(effect="off")
        uses = effect and self.effect(effect).uses_color
        note = f"brightness {round(brightness * 100 / 255)} %"
        return State(effect=effect, color=hex_color(rgb) if uses else None, note=note)

    def apply(self, effect_id, color):
        eff = self.effect(effect_id)
        rgb = parse_color(color) if (eff.uses_color and color) else (255, 255, 255)
        if effect_id == "off":
            code, brightness = self.hw.EFFECTS["static"], 0
        else:
            code, brightness = self.hw.EFFECTS[effect_id], round(self.brightness_pct * 255 / 100)
        self.hw.Lighting.set(code, brightness, *rgb)
        time.sleep(0.1)
        return self.read()
