"""Device registry for rgbctl. Add new device classes to DEVICE_CLASSES."""
from .base import Effect

# Effects offered for all devices at once. A device without an effect of the same id uses
# its `equivalents` entry (G815 rainbow -> wave, G Pro rainbow -> colour cycle).
GLOBAL_EFFECTS = (
    Effect("off", "Off", False),
    Effect("static", "Static", True),
    Effect("breathing", "Breathing", True),
    Effect("color_cycle", "Colour cycle", False),
    Effect("rainbow", "Rainbow / wave", False),
)
from .asus_pg39wcdm import AsusPG39WCDM
from .corsair_a600 import CorsairA600
from .logitech import LogitechG815, LogitechGPro

# id -> class. Order is the order shown in the widget.
DEVICE_CLASSES = {
    "corsair": CorsairA600,
    "asus": AsusPG39WCDM,
    "g815": LogitechG815,
    "gpro": LogitechGPro,
}
