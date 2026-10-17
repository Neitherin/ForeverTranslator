from __future__ import annotations

import struct
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.generate_byte_atlas import generate


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "addon" / "ForeverTranslatorProbe" / "Textures" / "QuadAtlas.tga"
HEADER = struct.Struct("<BBBHHBHHHHBB")


class QuadAtlasTests(unittest.TestCase):
    def test_shipped_atlas_matches_generator(self) -> None:
        with TemporaryDirectory() as temporary:
            generated = Path(temporary) / "QuadAtlas.tga"
            generate(generated)
            self.assertEqual(ATLAS.read_bytes(), generated.read_bytes())

    def test_every_byte_tile_contains_four_expected_luminance_symbols(self) -> None:
        content = ATLAS.read_bytes()
        header = HEADER.unpack_from(content)
        width, height, depth = header[8], header[9], header[10]
        self.assertEqual((width, height, depth), (256, 64, 32))
        pixels = content[HEADER.size :]

        for value in range(256):
            tile_left = (value % 16) * 16
            tile_top = (value // 16) * 4
            for symbol_index in range(4):
                shift = 2 * (3 - symbol_index)
                symbol = (value >> shift) & 0x03
                expected = 255 - symbol * 85
                for y in range(tile_top, tile_top + 4):
                    for x in range(
                        tile_left + symbol_index * 4,
                        tile_left + (symbol_index + 1) * 4,
                    ):
                        offset = (y * width + x) * 4
                        blue, green, red, alpha = pixels[offset : offset + 4]
                        self.assertEqual(
                            (blue, green, red, alpha),
                            (expected, expected, expected, 255),
                        )


if __name__ == "__main__":
    unittest.main()
