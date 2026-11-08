"""Logitech G815 keyboard and G Pro Wireless mouse via HID++ 2.0 lighting features.

Probed 2026-11-07 (tools/logitech_probe.py):
  G815  (wired 046d:c33f, interface 1, device index 0xFF): feature 0x8071 RGB_EFFECTS,
        zone 0 = logo (off, static, cycle, breathe), zone 1 = keys (+ wave, ripple, 0x0c).
  G Pro Wireless (receiver 046d:c53a interface 2, slot 1): feature 0x8070 COLOR_LED_EFFECTS,
        zone 0 = primary, zone 1 = logo (off, static, cycle, breathe).

Set effect (Solaar / OpenRGB): 0x8070 function 3, 0x8071 function 1, params
[zone, effect slot, effect params at offset 2.., ..., byte 12 = 0x00 (8070) / 0x01 (8071)].
The effect *slot* is the position in the zone's effect list, looked up from the device.
Effect params: static colour@0; breathe colour@0 period@3 (BE ms) intensity@6;
cycle period@5 (BE ms) intensity@7; ripple colour@0 period@4; wave period@6 direction@9.
The G815 runs its onboard profile (0x8100 onboard mode 1) and ignores 0x8071 effects until
software control is claimed with 0x8071 function 5 [01 03 05] (tested 2026-11-07).
The devices have no read-back for the active effect here, so the state shown is the last one
rgbctl set (kept in ~/.cache/rgbctl/state.json).
"""
import json
import os

from . import hidpp
from .base import Device, Effect, State, parse_color

STATE_FILE = os.path.expanduser("~/.cache/rgbctl/state.json")

# effect id (rgbctl) -> HID++ effect id
HIDPP_EFFECT = {"off": 0x0000, "static": 0x0001, "color_cycle": 0x0003, "wave": 0x0004,
                "breathing": 0x000A, "ripple": 0x000B}
PERIOD_MS = 5000
INTENSITY = 100


def effect_params(effect_id, rgb):
    """10 effect-parameter bytes for the set-effect request."""
    p = bytearray(10)
    r, g, b = rgb
    period = PERIOD_MS.to_bytes(2, "big")
    if effect_id == "static":
        p[0:3] = bytes((r, g, b))
    elif effect_id == "breathing":
        p[0:3] = bytes((r, g, b))
        p[3:5] = period
        p[6] = INTENSITY
    elif effect_id == "color_cycle":
        p[5:7] = period
        p[7] = INTENSITY
    elif effect_id == "ripple":
        p[0:3] = bytes((r, g, b))
        p[4:6] = (20).to_bytes(2, "big")
    elif effect_id == "wave":
        p[6:8] = (2000).to_bytes(2, "big")
        p[9] = 1
    return bytes(p)


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(dev_id, effect, color):
    data = _load_state()
    data[dev_id] = {"effect": effect, "color": color}
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)


class LogitechHidppDevice(Device):
    """Shared logic. Subclasses set vid_pid, interface, device_index, feature."""

    vid_pid = ""
    interface = None
    device_index = 0xFF
    feature = hidpp.RGB_EFFECTS
    # Effect to use in a zone that lacks the requested one (e.g. wave on the G815 logo).
    zone_fallback = {"wave": "color_cycle", "ripple": "static"}

    def _paths(self):
        return hidpp.find_hidraw(self.vid_pid, interface=self.interface)

    def _open(self):
        paths = self._paths()
        if not paths:
            raise OSError(f"{self.name}: device {self.vid_pid} not found")
        return hidpp.Hidpp(paths[0], self.device_index)

    def available(self):
        try:
            with self._open() as h:
                return bool(h.feature_index(self.feature))
        except OSError:
            return False

    def _zone_effects(self, h, idx):
        """{zone: {hidpp_effect_id: slot}} read from the device."""
        if self.feature == hidpp.RGB_EFFECTS:
            zones = h.request(idx, 0, b"\xff\xff\x00")[2]
            info = lambda z, s: h.request(idx, 0, bytes([z, s, 0]))  # noqa: E731
            count = lambda z: h.request(idx, 0, bytes([z, 0xFF, 0]))[4]  # noqa: E731
        else:
            zones = h.request(idx, 0)[0]
            info = lambda z, s: h.request(idx, 2, bytes([z, s, 0]))  # noqa: E731
            count = lambda z: h.request(idx, 1, bytes([z, 0xFF, 0]))[3]  # noqa: E731
        out = {}
        for z in range(zones):
            slots = {}
            for s in range(count(z)):
                r = info(z, s)
                slots[(r[2] << 8) | r[3]] = s
            out[z] = slots
        return out

    def read(self):
        if not self._paths():
            raise OSError(f"{self.name}: device {self.vid_pid} not found")
        s = _load_state().get(self.id)
        if not s:
            return State(note="not set by rgbctl yet")
        return State(effect=s["effect"], color=s["color"], note="last set by rgbctl")

    def apply(self, effect_id, color):
        eff = self.effect(effect_id)
        rgb = parse_color(color) if (eff.uses_color and color) else (255, 255, 255)
        with self._open() as h:
            idx = h.feature_index(self.feature)
            if not idx:
                raise OSError(f"{self.name}: lighting feature {self.feature:#06x} missing")
            if self.feature == hidpp.RGB_EFFECTS:
                fn, tail = 1, 0x01
                # Take lighting over from the onboard profile (otherwise the G815 keeps its
                # stored effect). Same bytes as OpenRGB; the device echoes them back.
                # Not persistent across power cycles, so it is sent every time.
                h.request(idx, 5, bytes([0x01, 0x03, 0x05]))
            else:
                fn, tail = 3, 0x00
            for zone, slots in self._zone_effects(h, idx).items():
                use = effect_id
                if HIDPP_EFFECT[use] not in slots:
                    use = self.zone_fallback.get(use, "static")
                if HIDPP_EFFECT[use] not in slots:
                    continue
                params = bytes([zone, slots[HIDPP_EFFECT[use]]]) + effect_params(use, rgb)
                params += bytes([tail])
                h.request(idx, fn, params)
        hexc = "#%02x%02x%02x" % rgb if eff.uses_color else None
        _save_state(self.id, effect_id, hexc)
        return State(effect=effect_id, color=hexc, note="last set by rgbctl")


class LogitechG815(LogitechHidppDevice):
    vid_pid = "046D:C33F"
    interface = 1
    device_index = 0xFF
    feature = hidpp.RGB_EFFECTS

    def __init__(self, options=None):
        super().__init__(
            id="g815", name="Logitech G815",
            effects=(
                Effect("off", "Off", False),
                Effect("static", "Static", True),
                Effect("breathing", "Breathing", True),
                Effect("color_cycle", "Colour cycle", False),
                Effect("wave", "Wave (keys; logo cycles)", False),
                Effect("ripple", "Ripple (keys; logo static)", True),
            ),
            palette=None, options=options or {},
            equivalents={"rainbow": "wave"},
        )


class LogitechGPro(LogitechHidppDevice):
    vid_pid = "046D:C53A"
    interface = 2
    feature = hidpp.COLOR_LED_EFFECTS

    def __init__(self, options=None):
        super().__init__(
            id="gpro", name="Logitech G Pro Wireless",
            effects=(
                Effect("off", "Off", False),
                Effect("static", "Static", True),
                Effect("breathing", "Breathing", True),
                Effect("color_cycle", "Colour cycle", False),
            ),
            palette=None, options=options or {},
            equivalents={"rainbow": "color_cycle"},
        )
        self.device_index = int(self.options.get("receiver_slot", 1))


DEVICES = {"g815": LogitechG815, "gpro": LogitechGPro}
