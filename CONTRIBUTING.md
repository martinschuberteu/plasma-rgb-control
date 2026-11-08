# Contributing

Bug reports, device support and pull requests are welcome. Ask questions and suggest ideas with the *Question or idea* issue form; report security problems through [private reporting](SECURITY.md).

## Adding a device

Write a driver: see [docs/writing-a-driver.md](docs/writing-a-driver.md) and the hardware-free [demo driver](examples/demo_device.py). Test it in `~/.config/rgbctl/devices/` first; to contribute it, move it to `rgbdevices/` and in the same pull request:

- add a row to the device table in the README,
- note in the driver's docstring how the protocol was found and any values that must never be written,
- add unit tests for encoding logic that can be tested without the device (see `tests/test_encoding.py`).

Only send commands you have seen the manufacturer's software send, or that the device documents. A wrong command can leave a device in a state only a factory reset fixes.

## Before a pull request

```bash
python3 -m unittest discover -s tests
./install.sh && systemctl --user restart plasma-plasmashell   # widget changes
journalctl --user -b | grep rgbctl                            # no QML warnings
```

CI runs the tests on Python 3.10 and the current version. Keep the code free of third-party Python packages unless a driver can't work without one.

## Releases

Bump `__version__` in `rgbctl.py` and `Version` in `plasmoid/eu.martinschubert.rgbctl/metadata.json` (CI checks they match), then tag `vX.Y.Z` and publish a GitHub release.
