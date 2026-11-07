# rgbctl

One place to control RGB lighting on this PC: a Python library (`rgbdevices/`), a CLI (`rgbctl.py`) and a Plasma 6 widget (`plasmoid/`).

| Device | id | How | Effects | Colours |
|---|---|---|---|---|
| Corsair ONE a600 front strips | `corsair` | USB HID `1b1c:0d18` via `a600hw.py` from the corsair-one-a600-linux project | off, static, breathing, strobing, color_cycle, rainbow, starry_night | any (static only) |
| ASUS PG39WCDM rear logo (OSD "Aura RGB") | `asus` | DDC/CI VCP `F2` via `ddcutil --model PG39WCDM` | off, static, breathing, strobing, color_cycle, rainbow | red, green, blue, cyan, magenta, yellow (nearest by hue) |
| Logitech G815 keyboard (keys + logo) | `g815` | HID++ 2.0 feature 0x8071 on `046d:c33f` interface 1 | off, static, breathing, color_cycle, wave, ripple (logo: wave → cycle, ripple → static) | any |
| Logitech G Pro Wireless (both zones) | `gpro` | HID++ 2.0 feature 0x8070 via receiver `046d:c53a` interface 2, slot 1 | off, static, breathing, color_cycle | any |

Logitech devices have no read-back of the active effect; status shows the last setting rgbctl sent (`~/.cache/rgbctl/state.json`). `tools/logitech_probe.py` lists their lighting features, zones and effects (read-only).

### Logitech access

Needs the udev rule (once):

```bash
sudo install -m 644 deploy/70-rgbctl-logitech.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw
```

## Global effects

Effects every device can show, used by `set all` and the widget's *All devices* effect menu (`rgbctl.py effects` prints the mapping):

| Global | Corsair | ASUS | G815 | G Pro |
|---|---|---|---|---|
| off | off | off | off | off |
| static (colour) | static | static (nearest preset) | static | static |
| breathing (colour) | breathing (own colours) | breathing | breathing | breathing |
| color_cycle | color_cycle | color_cycle | color_cycle | color_cycle |
| rainbow | rainbow | rainbow | wave | color_cycle |

Device-only effects (strobing, ripple, starry night) are set per device. With `set all <effect>`, a device that has nothing similar is skipped. A device's `equivalents` dict maps a global effect to its own one.

## CLI

```bash
./rgbctl.py status
./rgbctl.py set all static '#ff8000'
./rgbctl.py set asus breathing blue
./rgbctl.py set corsair rainbow
./rgbctl.py set all off
./rgbctl.py list
```

Add `--json` for machine-readable output (used by the widget). Calls are serialised with a lock in `$XDG_RUNTIME_DIR/rgbctl.lock`.

Optional config `~/.config/rgbctl/config.json`:

```json
{"disabled": [], "corsair": {"brightness": 100, "a600hw": "/path/to/a600hw.py"}, "asus": {"model": "PG39WCDM"}}
```

## Widget

Installed with `kpackagetool6 -t Plasma/Applet -i plasmoid/eu.martinschubert.rgbctl` (update: `-u` instead of `-i`). Add it via right-click on the desktop or panel → *Add Widgets…* → **RGB Lighting**. The CLI path is set at the top of `contents/ui/main.qml`.

## Safety notes

- **ASUS:** never write F2 effect index `1` (turns Aura Sync on, darkens the logo and locks the OSD until a factory reset) or values above 6. `encode_write()` refuses them; writes are at least 1 s apart and verified by decoding the read-back. ddcutil's "Verification failed" is expected. The stand light (LIGHT IN MOTION) can't be controlled.
- **Corsair:** the CoolerControl corsair-a600 plugin re-applies its own last lighting when its brightness setting changes or CoolerControl sends a lighting command; then the colour set here is replaced.

- **G815:** runs its onboard profile (0x8100 onboard mode) and ignores lighting commands until software control is claimed (0x8071 function 5, `01 03 05`). rgbctl sends the claim before every change; the onboard profile itself (G-keys etc.) stays active. After a power cycle the keyboard shows its profile lighting again until rgbctl sets something.

## Adding a device

1. Create `rgbdevices/<name>.py` with a `Device` subclass (see `base.py`): set `id`, `name`, `effects` (`Effect(id, label, uses_color)`), `palette` (dict of fixed colours or `None`), and implement `available()`, `read()` and `apply(effect_id, color)`.
2. Register it in `DEVICE_CLASSES` in `rgbdevices/__init__.py`. The CLI, `all` and the widget pick it up automatically.

Tests: `python3 -m unittest discover -s tests`.
