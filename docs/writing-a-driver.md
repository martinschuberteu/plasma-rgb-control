# Writing a driver

A driver teaches rgbctl one kind of RGB device. The CLI, `set all` and the Plasma widget pick
it up automatically: effects, colours and hints in the widget all come from the driver's data.

## Where drivers live

- **Built in:** `rgbdevices/*.py` in this repository.
- **Your own:** `~/.config/rgbctl/devices/*.py`, or any folder listed in `driver_dirs` in
  `~/.config/rgbctl/config.json`. No changes to this repository needed.

A file is a driver if it defines `DEVICES`. Files starting with `_` are skipped. If a driver
fails to import (missing library, typo), `status` and the widget show it as an error and all
other devices keep working.

## Minimal driver

Start from [`examples/demo_device.py`](../examples/demo_device.py), a working driver for a
pretend device. To try it:

```bash
mkdir -p ~/.config/rgbctl/devices
cp examples/demo_device.py ~/.config/rgbctl/devices/
rgbctl status
rgbctl set demo static '#ff8000'
```

The shape of every driver:

```python
from rgbdevices.base import Device, Effect, State, hex_color, parse_color

class MyLightbar(Device):
    def __init__(self, options=None):
        super().__init__(
            id="lightbar",                      # used on the command line: rgbctl set lightbar ...
            name="My light bar",                # shown in the widget
            effects=(
                Effect("off", "Off", False),    # (id, label, uses a colour?)
                Effect("static", "Static", True),
                Effect("color_cycle", "Colour cycle", False),
            ),
            palette=None,                       # or {"#ff0000": "Red", ...} if only fixed colours work
            options=options or {},              # this device's section of config.json
            equivalents={"rainbow": "color_cycle"},
        )

    def available(self) -> bool: ...          # is the device connected and usable?
    def read(self) -> State: ...               # current effect/colour, read from the device
    def apply(self, effect_id, color) -> State: ...   # set it; return the new state

DEVICES = {"lightbar": MyLightbar}
```

## The contract

| Part | Meaning |
|---|---|
| `id` | Unique, lowercase, stable. Must match the key in `DEVICES`. |
| `effects` | Everything the device can do. Use the global ids (`off`, `static`, `breathing`, `color_cycle`, `rainbow`) where the effect matches, so `set all` works without mapping. |
| `equivalents` | Global effect id → your effect id, for global effects you have under another name or only something close to (e.g. `{"rainbow": "wave"}`). A global effect with no match is skipped for your device on `set all`. |
| `palette` | `None` if any colour works. Otherwise `{"#rrggbb": "Label"}`: the widget shows these as buttons and tells the user the closest one is used. |
| `options` | The device's section of `config.json` (`{"lightbar": {...}}`), for ports, brightness, model names. |
| `read()` | Return a `State(effect=..., color="#rrggbb" or None, note=...)`. If the hardware can't report its state, store what you last sent and return that with `note="last set by rgbctl"` (see `rgbdevices/logitech.py`). |
| `apply(effect_id, color)` | `color` is whatever the user typed (`"#ff8000"`, `"orange"`) or `None`; use `parse_color()` to get `(r, g, b)`. Raise an exception with a clear message on failure; it is shown in the widget. |

Exceptions in `read()` or `apply()` only affect that device. Calls are serialised with a lock,
so you don't need your own locking for widget clicks.

## Imports

Drivers in your own folder import helpers as `from rgbdevices.base import ...` (and
`from rgbdevices import hidpp` for Logitech HID++). Built-in drivers use relative imports
(`from .base import ...`).

## Testing

`tests/test_drivers.py` runs the CLI against the demo driver only, without touching hardware.
Pure encoding logic (packet building, value mapping) is worth a unit test of its own, like
`tests/test_encoding.py` for the ASUS monitor. Run all tests with:

```bash
python3 -m unittest discover -s tests
```

To add a driver to this repository, put it in `rgbdevices/`, add a row to the device table
in the README and note any safety rules (values that must never be written) in its docstring.
