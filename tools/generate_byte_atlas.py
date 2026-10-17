from __future__ import annotations

import struct
from pathlib import Path


WIDTH = 256
HEIGHT = 64
TILE_WIDTH = 16
TILE_HEIGHT = 4


def generate(destination: Path) -> None:
    pixels = bytearray()
    for y in range(HEIGHT):
        tile_row = y // TILE_HEIGHT
        for x in range(WIDTH):
            tile_column = x // TILE_WIDTH
            value = tile_row * 16 + tile_column
            symbol_index = (x % TILE_WIDTH) // 4
            shift = 2 * (3 - symbol_index)
            symbol = (value >> shift) & 0x03
            channel = 255 - symbol * 85
            pixels.extend((channel, channel, channel, 255))

    header = struct.pack(
        "<BBBHHBHHHHBB",
        0,
        0,
        2,
        0,
        0,
        0,
        0,
        0,
        WIDTH,
        HEIGHT,
        32,
        0x28,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + pixels)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    generate(root / "addon" / "ForeverTranslatorProbe" / "Textures" / "QuadAtlas.tga")
