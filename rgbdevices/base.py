"""Common device interface and colour helpers for rgbctl.

A device module provides one subclass of Device. To add a device (e.g. a Logitech mouse or
keyboard), write a module with a Device subclass and register it in rgbdevices/__init__.py.
"""
import colorsys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Effect:
    id: str            # stable id used on the command line and by the widget
    name: str          # label shown in the widget
    uses_color: bool   # whether the device applies a colour for this effect


@dataclass
class State:
    effect: str | None = None      # effect id, or None if unknown
    color: str | None = None       # "#rrggbb", or None if the effect has no colour
    note: str | None = None        # anything worth showing (e.g. "Aura Sync is on")


@dataclass
class Device:
    """Base class. Subclasses set the class attributes and implement read() and apply()."""

    id: str = ""
    name: str = ""
    effects: tuple = ()
    # Fixed colours the device can show, as {"#rrggbb": label}, or None if any colour works.
    palette: dict | None = None
    options: dict = field(default_factory=dict)
    # Global effect id -> this device's closest effect, for global effects it lacks by name
    # (e.g. the G815 shows "rainbow" as its wave).
    equivalents: dict = field(default_factory=dict)

    def resolve(self, global_effect):
        """This device's effect id for a global effect, or None if it has nothing similar."""
        target = self.equivalents.get(global_effect, global_effect)
        return target if any(e.id == target for e in self.effects) else None

    def effect(self, effect_id):
        for e in self.effects:
            if e.id == effect_id:
                return e
        raise ValueError(f"{self.name}: unknown effect {effect_id!r} "
                         f"(have: {', '.join(e.id for e in self.effects)})")

    def available(self) -> bool:
        raise NotImplementedError

    def read(self) -> State:
        raise NotImplementedError

    def apply(self, effect_id: str, color: str | None) -> State:
        """Set the effect (and colour, where the effect uses one). Returns the new state."""
        raise NotImplementedError

    def describe(self):
        return {
            "id": self.id,
            "name": self.name,
            "effects": [{"id": e.id, "name": e.name, "color": e.uses_color} for e in self.effects],
            "palette": self.palette,
            "equivalents": self.equivalents,
        }


def parse_color(text):
    """Accepts '#rrggbb', 'rrggbb', '#rgb' or a basic name. Returns (r, g, b)."""
    names = {"red": "ff0000", "green": "00ff00", "blue": "0000ff", "cyan": "00ffff",
             "magenta": "ff00ff", "yellow": "ffff00", "white": "ffffff", "orange": "ff8000",
             "purple": "8000ff", "pink": "ff40a0"}
    t = text.strip().lower()
    t = names.get(t, t).lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) != 6 or any(c not in "0123456789abcdef" for c in t):
        raise ValueError(f"not a colour: {text!r}")
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))


def hex_color(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def nearest_by_hue(rgb, palette_hues):
    """Pick the palette entry whose hue is closest. palette_hues: {key: hue in degrees}."""
    h, _l, _s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    hue = h * 360

    def dist(k):
        d = abs(palette_hues[k] - hue) % 360
        return min(d, 360 - d)

    return min(palette_hues, key=dist)
