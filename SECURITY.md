# Security policy

## Supported versions

Only the [latest release](https://github.com/martinschuberteu/plasma-rgb-control/releases/latest) gets fixes.

## Reporting a vulnerability

Report it privately through [GitHub's vulnerability reporting](https://github.com/martinschuberteu/plasma-rgb-control/security/advisories/new), not in a public issue. Include what is affected, how to reproduce it and what an attacker could do.

This is a hobby project maintained in spare time: expect a reply within about two weeks. Once a fix is released, the report is published as a security advisory, with credit if you want it.

## Scope

Things worth reporting include:

- the widget passing user-controlled text to the shell (`rgbctl` is started through the Plasma executable engine),
- drivers sending device commands that can damage or lock up hardware (for example the ASUS monitor's effect index 1, which `encode_write()` refuses),
- the udev rules (`deploy/70-rgbctl-*.rules`) giving access to more than the lighting interfaces they are meant for.

Drivers in `~/.config/rgbctl/devices/` are code you install yourself and run with your user's rights; problems in third-party drivers belong to their authors.
