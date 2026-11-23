import colorsys
import math
import re
from typing import Tuple

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    match = re.match(r'^#?([A-Fa-f0-9]{6})$', hex_color)
    if not match:
        raise ValueError(f"Invalid hex color: {hex_color}")
    hex_digits = match.group(1)
    return tuple(int(hex_digits[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return '#{:02X}{:02X}{:02X}'.format(*rgb)


# The lamp takes a custom clock/effect color as one integer 0x01RRGGBB
# (the 0x01 flag byte marks it as an explicit color).
def rgb_to_argb(rgb) -> int:
    red, green, blue = (int(channel) & 0xFF for channel in rgb[:3])
    return 0x01000000 | (red << 16) | (green << 8) | blue


def argb_to_rgb(value: int) -> Tuple[int, int, int]:
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


# Channel math shared by the renderers. Each caller keeps its own rounding
# (Python's round() halves to even; round_half_up is JS Math.round's twin for
# the frames the cards draw too), so the helpers take it as a parameter.

def clamp8(value):
    """``value`` limited to 0-255 (not rounded)."""
    return max(0, min(255, value))


def round_half_up(value: float) -> int:
    """Halves rounded up, like JS Math.round (for frames the cards draw too)."""
    return math.floor(value + 0.5)


def lerp_rgb(start, end, amount: float, rounding=round) -> tuple:
    """``start`` moved ``amount`` of the way to ``end``, channel by channel,
    each channel through ``rounding``."""
    return tuple(rounding(a + (b - a) * amount) for a, b in zip(start, end))


def hsv_to_rgb8(hue: float, saturation: float = 1.0, value: float = 1.0, rounding=round) -> tuple:
    """colorsys.hsv_to_rgb as 0-255 channels, each ``channel * 255`` through
    ``rounding``. The hue is taken as it is (no wrap)."""
    return tuple(rounding(channel * 255) for channel in colorsys.hsv_to_rgb(hue, saturation, value))


def luma(red: float, green: float, blue: float) -> float:
    """Rec. 601 luma (0.299 R + 0.587 G + 0.114 B), not rounded."""
    return 0.299 * red + 0.587 * green + 0.114 * blue
