#!/usr/bin/env python3
"""Read-only probe: which HID++ lighting features, zones and effects the Logitech devices report.

Sends only IRoot/feature lookups and the GET_INFO functions of 0x8070 / 0x8071 / 0x8081 / 0x8040.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from rgbdevices import hidpp  # noqa: E402

EFFECT_NAMES = {0x00: "disabled", 0x01: "static", 0x02: "pulse", 0x03: "cycle", 0x04: "wave",
                0x08: "boot", 0x09: "demo", 0x0A: "breathe", 0x0B: "ripple",
                0x0E: "decomposition", 0x0F: "signature1", 0x10: "signature2",
                0x15: "cycle(sat)", 0x16: "wave(sat)", 0x17: "ripple(sat)"}


def probe(label, path, dev):
    print(f"== {label}: {path} device index {dev:#04x}")
    try:
        with hidpp.Hidpp(path, dev) as h:
            print("  protocol", h.protocol_version(), "name", repr(h.name()))
            for fid in (hidpp.COLOR_LED_EFFECTS, hidpp.RGB_EFFECTS, hidpp.PER_KEY_LIGHTING,
                        hidpp.BRIGHTNESS):
                print(f"  feature {fid:#06x}: index {h.feature_index(fid)}")
            if idx := h.feature_index(hidpp.COLOR_LED_EFFECTS):
                zones = h.request(idx, 0)[0]
                print(f"  0x8070 zones: {zones}")
                for z in range(zones):
                    zi = h.request(idx, 1, bytes([z, 0xFF, 0]))
                    print(f"   zone {z}: raw {zi[:8].hex(' ')}")
                    for slot in range(zi[3] if len(zi) > 3 else 0):
                        ei = h.request(idx, 2, bytes([z, slot, 0]))
                        eid = (ei[2] << 8) | ei[3]
                        print(f"     slot {slot}: effect {eid:#06x} {EFFECT_NAMES.get(eid, '?')} raw {ei[:10].hex(' ')}")
            if idx := h.feature_index(hidpp.RGB_EFFECTS):
                info = h.request(idx, 0, b"\xff\xff\x00")
                print(f"  0x8071 info raw {info[:10].hex(' ')}")
                zones = info[2]
                for z in range(zones):
                    zi = h.request(idx, 0, bytes([z, 0xFF, 0]))
                    print(f"   zone {z}: raw {zi[:10].hex(' ')}")
                    for slot in range(zi[4] if len(zi) > 4 else 0):
                        ei = h.request(idx, 0, bytes([z, slot, 0]))
                        eid = (ei[2] << 8) | ei[3]
                        print(f"     slot {slot}: effect {eid:#06x} {EFFECT_NAMES.get(eid, '?')} raw {ei[:12].hex(' ')}")
    except OSError as e:
        print("  ERROR", e)


def main():
    for p in hidpp.find_hidraw("046D:C33F", interface=1):
        probe("G815", p, 0xFF)
    receivers = hidpp.find_hidraw("046D:C53A", interface=2)
    for p in receivers:
        for slot in range(1, 7):
            try:
                with hidpp.Hidpp(p, slot) as h:
                    h.protocol_version()
            except OSError:
                continue
            probe(f"receiver slot {slot}", p, slot)


if __name__ == "__main__":
    main()
