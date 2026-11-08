"""Device drivers for rgbctl, found automatically.

A driver is a Python module that defines `DEVICES = {"<id>": <Device subclass>}`. Modules are
loaded from this package and from user driver folders (default ~/.config/rgbctl/devices/).
A module that fails to import is reported as an error and does not affect the others.
See docs/writing-a-driver.md.
"""
import importlib
import importlib.util
import os
import pkgutil
import sys

from .base import Effect

# Effects offered for all devices at once. A device without an effect of the same id uses
# its `equivalents` entry (e.g. a keyboard that shows "rainbow" as its "wave").
GLOBAL_EFFECTS = (
    Effect("off", "Off", False),
    Effect("static", "Static", True),
    Effect("breathing", "Breathing", True),
    Effect("color_cycle", "Colour cycle", False),
    Effect("rainbow", "Rainbow / wave", False),
)

USER_DRIVER_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "rgbctl", "devices")


def _builtin_modules():
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if not info.name.startswith("_") and info.name != "base":
            yield info.name, lambda name=info.name: importlib.import_module(f"{__name__}.{name}")


def _folder_modules(folder):
    if not os.path.isdir(folder):
        return
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(folder, fname)
        name = f"rgbctl_driver_{fname[:-3]}"

        def load(path=path, name=name):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            return mod

        yield path, load


def discover(builtin=True, folders=None):
    """Find device classes.

    Returns (classes, errors): classes is {device id: class} in load order, errors is
    {module name or path: message} for modules that could not be loaded.
    """
    folders = [USER_DRIVER_DIR] if folders is None else folders
    sources = list(_builtin_modules()) if builtin else []
    for folder in folders:
        sources += list(_folder_modules(os.path.expanduser(folder)))

    classes, errors = {}, {}
    for label, load in sources:
        try:
            mod = load()
        except Exception as e:  # missing library, syntax error, ...: only this driver fails
            errors[label] = f"driver failed to load: {type(e).__name__}: {e}"
            continue
        for dev_id, cls in (getattr(mod, "DEVICES", None) or {}).items():
            if dev_id in classes:
                errors[label] = f"device id {dev_id!r} is already used by another driver"
                continue
            classes[dev_id] = cls
    return classes, errors
