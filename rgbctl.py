#!/usr/bin/env python3
"""rgbctl: control RGB lighting of several devices through pluggable drivers.

  rgbctl.py list                         devices, effects, palettes
  rgbctl.py status [--json]              current state of every device
  rgbctl.py effects [--json]             global effects and each device's equivalent
  rgbctl.py set all static '#ff8000'     every device static (ASUS snaps to nearest preset)
  rgbctl.py set all rainbow              devices without rainbow use their closest effect
  rgbctl.py set asus breathing blue      one device, one effect
  rgbctl.py set corsair rainbow
  rgbctl.py restore g815                 set the last known state again (after a reconnect)

Config (optional): ~/.config/rgbctl/config.json ($RGBCTL_CONFIG overrides the path), e.g.
  {"disabled": ["asus"], "corsair": {"brightness": 80},
   "order": ["corsair", "asus"], "driver_dirs": ["~/my-rgb-drivers"]}
Drivers: built in (rgbdevices/) plus ~/.config/rgbctl/devices/*.py, see docs/writing-a-driver.md.
"""
import argparse
import contextlib
import fcntl
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import rgbdevices  # noqa: E402
from rgbdevices import GLOBAL_EFFECTS  # noqa: E402

__version__ = "0.1.2"  # keep in sync with plasmoid/.../metadata.json

CONFIG_PATH = os.environ.get("RGBCTL_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "rgbctl", "config.json")
LOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "rgbctl.lock")


@contextlib.contextmanager
def device_lock():
    """One rgbctl at a time talks to the devices (widget clicks, refreshes, scripts)."""
    with open(LOCK_PATH, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def load_drivers(config):
    """{device id: class} in display order, and {driver: error} for drivers that failed."""
    classes, errors = rgbdevices.discover(
        builtin=config.get("builtin_drivers", True),
        folders=[rgbdevices.USER_DRIVER_DIR] + list(config.get("driver_dirs", [])))
    order = config.get("order", [])
    ids = sorted(classes, key=lambda i: (order.index(i) if i in order else len(order)))
    return {i: classes[i] for i in ids}, errors


def make_devices(config, only=None):
    classes, errors = load_drivers(config)
    devices = []
    if only:
        errors = {}
    for dev_id, cls in classes.items():
        if dev_id in config.get("disabled", []) or (only and dev_id not in only):
            continue
        try:
            devices.append(cls(config.get(dev_id, {})))
        except Exception as e:  # a missing helper file must not break the other devices
            errors[dev_id] = str(e)
    return devices, errors


def state_dict(dev, state=None, error=None):
    d = dev.describe() if not isinstance(dev, str) else {"id": dev}
    d["state"] = vars(state) if state else None
    d["error"] = error
    return d


def read_state(dev):
    try:
        return state_dict(dev, dev.read())
    except Exception as e:
        return state_dict(dev, error=str(e))


def cmd_status(args, config):
    devices, errors = make_devices(config)
    with device_lock():
        out = [read_state(dev) for dev in devices]
    out += [state_dict(i, error=e) for i, e in errors.items()]
    emit(out, args.json)


def cmd_list(args, config):
    devices, errors = make_devices(config)
    out = [d.describe() for d in devices] + [{"id": i, "error": e} for i, e in errors.items()]
    if args.json:
        print(json.dumps(out, indent=1))
        return
    for d in out:
        if "error" in d:
            print(f"{d['id']}: unavailable ({d['error']})")
            continue
        print(f"{d['id']}: {d['name']}")
        for e in d["effects"]:
            print(f"  {e['id']:<13} {e['name']}{'  (colour)' if e['color'] else ''}")
        if d["palette"]:
            print("  colours:", ", ".join(f"{v} {k}" for k, v in d["palette"].items()))


def select_devices(device, config):
    """Devices for a command's `all`/<id> argument; exits on an unknown id."""
    only = None if device == "all" else [device]
    classes, _errors = load_drivers(config)
    if only and device not in classes:
        sys.exit(f"unknown device {device!r} (have: all, {', '.join(classes)})")
    return make_devices(config, only)


def cmd_set(args, config):
    only = None if args.device == "all" else [args.device]
    devices, errors = select_devices(args.device, config)
    if not only and devices and all(dev.resolve(args.effect) is None for dev in devices):
        known = ", ".join(g.id for g in GLOBAL_EFFECTS)
        sys.exit(f"no device has an effect like {args.effect!r} (global effects: {known})")
    out = [state_dict(i, error=e) for i, e in errors.items()]
    with device_lock():
        for dev in devices:
            effect = dev.resolve(args.effect)
            if effect is None:
                if only:
                    out.append(state_dict(dev, error=f"no effect like {args.effect!r}"))
                else:  # "all": a device without anything similar keeps its current effect
                    out.append(dict(read_state(dev), skipped=f"has no {args.effect}"))
                continue
            try:
                out.append(state_dict(dev, dev.apply(effect, args.color)))
            except Exception as e:
                out.append(state_dict(dev, error=str(e)))
    emit(out, args.json)
    if any(d["error"] for d in out):
        sys.exit(1)


def restore_one(dev, deadline):
    """Apply dev's current/last known state again; retry until deadline (device starting up)."""
    while True:
        try:
            state = dev.read()
            if not state.effect:
                return dict(state_dict(dev, state), skipped="no known state to restore")
            return state_dict(dev, dev.apply(state.effect, state.color))
        except Exception as e:
            if time.monotonic() >= deadline:
                return state_dict(dev, error=str(e))
            time.sleep(0.5)


def cmd_restore(args, config):
    """Set every (or one) device to its last known state again, e.g. after a KVM switch."""
    devices, errors = select_devices(args.device, config)
    out = [state_dict(i, error=e) for i, e in errors.items()]
    deadline = time.monotonic() + args.wait
    with device_lock():
        out += [restore_one(dev, deadline) for dev in devices]
    emit(out, args.json)
    if any(d["error"] for d in out):
        sys.exit(1)


def cmd_effects(args, config):
    """Global effects and what each device uses for them."""
    devices, _errors = make_devices(config)
    out = []
    for g in GLOBAL_EFFECTS:
        out.append({"id": g.id, "name": g.name, "color": g.uses_color,
                    "devices": {d.id: d.resolve(g.id) for d in devices}})
    if args.json:
        print(json.dumps(out))
        return
    for g in out:
        mapping = ", ".join(f"{k}={v or '-'}" for k, v in g["devices"].items())
        print(f"{g['id']:<12} {mapping}")


def emit(out, as_json):
    if as_json:
        print(json.dumps(out))
        return
    for d in out:
        name = d.get("name", d["id"])
        if d.get("skipped"):
            print(f"{name}: skipped ({d['skipped']})")
            continue
        if d["error"]:
            print(f"{name}: ERROR {d['error']}")
            continue
        s = d["state"]
        bits = [s["effect"] or "unknown"] + [x for x in (s["color"], s["note"]) if x]
        print(f"{name}: {', '.join(bits)}")


def main():
    p = argparse.ArgumentParser(description="Control RGB lighting.")
    p.add_argument("--version", action="version", version=f"rgbctl {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("list", "status", "effects"):
        sp = sub.add_parser(name)
        sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("set")
    sp.add_argument("device", help="all, or a device id from `list`")
    sp.add_argument("effect")
    sp.add_argument("color", nargs="?", help="#rrggbb or a name (red, orange, ...)")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("restore", help="set the last known state again (e.g. after a reconnect)")
    sp.add_argument("device", nargs="?", default="all", help="all (default) or a device id")
    sp.add_argument("--wait", type=float, default=0, metavar="SECONDS",
                    help="keep retrying a device that does not answer yet for this long")
    sp.add_argument("--json", action="store_true")
    args = p.parse_args()
    config = load_config()
    {"list": cmd_list, "status": cmd_status, "set": cmd_set,
     "restore": cmd_restore, "effects": cmd_effects}[args.cmd](args, config)


if __name__ == "__main__":
    main()
