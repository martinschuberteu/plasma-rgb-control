"""Demo driver: a pretend RGB device that keeps its state in a file. No hardware needed.

Copy it to ~/.config/rgbctl/devices/ to try it, or use it as the starting point for a real
driver (see docs/writing-a-driver.md). Options (config.json, key "demo"):
  {"demo": {"state_file": "/tmp/rgbctl-demo.json"}}
"""
import json
import os

from rgbdevices.base import Device, Effect, State, hex_color, parse_color

DEFAULT_STATE_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "rgbctl-demo.json")


class DemoDevice(Device):
    def __init__(self, options=None):
        super().__init__(
            id="demo",
            name="Demo device",
            effects=(
                Effect("off", "Off", False),
                Effect("static", "Static", True),
                Effect("breathing", "Breathing", True),
                Effect("color_cycle", "Colour cycle", False),
            ),
            palette=None,                            # any colour works
            options=options or {},
            equivalents={"rainbow": "color_cycle"},  # global "rainbow" -> our colour cycle
        )
        self.state_file = self.options.get("state_file", DEFAULT_STATE_FILE)

    def available(self):
        return True

    def read(self):
        try:
            with open(self.state_file) as f:
                return State(**json.load(f))
        except FileNotFoundError:
            return State(effect="off")

    def apply(self, effect_id, color):
        effect = self.effect(effect_id)                 # raises for an unknown effect
        hexc = hex_color(parse_color(color or "#ffffff")) if effect.uses_color else None
        state = State(effect=effect_id, color=hexc, note="demo")
        with open(self.state_file, "w") as f:
            json.dump(vars(state), f)
        return state


DEVICES = {"demo": DemoDevice}
