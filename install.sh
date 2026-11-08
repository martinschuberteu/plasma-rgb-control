#!/bin/sh
# Installs rgbctl for the current user: links the CLI to ~/.local/bin/rgbctl and installs
# (or updates) the Plasma widget. Run again after pulling changes to update the widget.
set -e
cd "$(dirname "$(readlink -f "$0")")"

mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/rgbctl.py" "$HOME/.local/bin/rgbctl"
echo "CLI: $HOME/.local/bin/rgbctl -> $PWD/rgbctl.py"

widget=plasmoid/eu.martinschubert.rgbctl
if kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx eu.martinschubert.rgbctl; then
    kpackagetool6 -t Plasma/Applet -u "$widget"
else
    kpackagetool6 -t Plasma/Applet -i "$widget"
fi
echo "Widget installed. Restart Plasma to load changes: systemctl --user restart plasma-plasmashell"
echo "Logitech devices also need the udev rule, see README.md."
