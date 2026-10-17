from __future__ import annotations

import unittest

from forever_probe.optical import (
    BITS_PER_CELL,
    CELLS_PER_BYTE,
    CONTROL_EVENT,
    GRID_SIZE,
    OpticalDecodeError,
    OpticalFrameDecoder,
    PacketReassembler,
    SequenceTracker,
    decode_packet,
    decode_message_payload,
    encode_packet,
    packetize_message,
    raster_bytes,
)


def synthetic_frame(packet, *, cell: int, offset: tuple[int, int]):
    raster = raster_bytes(packet)
    panel = (GRID_SIZE + 2) * cell
    width = offset[0] + panel + 11
    height = offset[1] + panel + 13
    pixels = bytearray((24, 31, 38, 255) * (width * height))

    def fill(left: int, top: int, right: int, bottom: int, bgra: tuple[int, ...]):
        for y in range(top, bottom):
            for x in range(left, right):
                position = (y * width + x) * 4
                pixels[position : position + 4] = bytes(bgra)

    left, top = offset
    fill(left, top, left + panel, top + panel, (255, 0, 255, 255))
    grid_left, grid_top = left + cell, top + cell
    fill(
        grid_left,
        grid_top,
        grid_left + GRID_SIZE * cell,
        grid_top + GRID_SIZE * cell,
        (255, 255, 255, 255),
    )
    for cell_index in range(GRID_SIZE * GRID_SIZE):
        byte = raster[cell_index // CELLS_PER_BYTE]
        shift = BITS_PER_CELL * (CELLS_PER_BYTE - 1 - cell_index % CELLS_PER_BYTE)
        symbol = (byte >> shift) & 0x03
        channel = 255 - symbol * 85
        row, column = divmod(cell_index, GRID_SIZE)
        fill(
            grid_left + column * cell,
            grid_top + row * cell,
            grid_left + (column + 1) * cell,
            grid_top + (row + 1) * cell,
            (channel, channel, channel, 255),
        )
    return width, height, bytes(pixels)


class OpticalProtocolTests(unittest.TestCase):
    def test_control_event_matches_addon_heartbeat(self) -> None:
        self.assertEqual(CONTROL_EVENT, "FT_HEARTBEAT")

    def test_quaternary_grid_is_compact_and_byte_aligned(self) -> None:
        self.assertEqual(BITS_PER_CELL, 2)
        self.assertEqual(CELLS_PER_BYTE, 4)
        self.assertEqual(GRID_SIZE, 48)
        self.assertEqual((GRID_SIZE + 2) * 2, 100)

    def test_packet_round_trip_and_checksum_rejection(self) -> None:
        packet = packetize_message(
            session=1234,
            sequence=55,
            event="CHAT_MSG_PARTY",
            author="Žluťoučký-Realm",
            text="Wait for mana, prosím.",
            player_class="MAGE",
        )[0]
        encoded = encode_packet(packet)
        self.assertEqual(decode_packet(encoded), packet)

        damaged = bytearray(encoded)
        damaged[20] ^= 0x01
        with self.assertRaisesRegex(OpticalDecodeError, "checksum"):
            decode_packet(bytes(damaged))

    def test_long_utf8_message_reassembles_out_of_order(self) -> None:
        packets = packetize_message(
            session=5,
            sequence=9,
            event="CHAT_MSG_GUILD",
            author="Tester",
            text="Příliš žluťoučký kůň. " * 80,
            player_class="DRUID",
        )
        self.assertGreater(len(packets), 1)
        reassembler = PacketReassembler()
        message = None
        for packet in reversed(packets):
            message = reassembler.accept(packet) or message
        assert message is not None
        self.assertEqual(message.event, "CHAT_MSG_GUILD")
        self.assertEqual(message.author, "Tester")
        self.assertEqual(message.text, "Příliš žluťoučký kůň. " * 80)
        self.assertEqual(message.player_class, "DRUID")
        self.assertIsNone(reassembler.accept(packets[0]))

    def test_decodes_legacy_message_without_player_class(self) -> None:
        event = b"CHAT_MSG_SAY"
        author = b"Old Client"
        text = b"hello"
        payload = bytes((len(event), len(author))) + len(text).to_bytes(2, "little")
        payload += event + author + text
        message = decode_message_payload(payload, session=1, sequence=2)
        self.assertEqual(message.author, "Old Client")
        self.assertEqual(message.text, "hello")
        self.assertIsNone(message.player_class)

    def test_sequence_tracker_recovers_late_gap(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(77, 10)
        tracker.observe(77, 13)
        self.assertEqual(tracker.lost, 2)
        tracker.observe(77, 11)
        self.assertEqual(tracker.lost, 1)
        tracker.observe(77, 12)
        self.assertEqual(tracker.lost, 0)

    def test_reassembler_bounds_incomplete_messages(self) -> None:
        reassembler = PacketReassembler(pending_capacity=3)
        for sequence in range(10):
            packets = packetize_message(
                session=1,
                sequence=sequence,
                event="CHAT_MSG_SYSTEM",
                author=None,
                text="x" * 700,
            )
            self.assertGreater(len(packets), 1)
            self.assertIsNone(reassembler.accept(packets[0]))
        self.assertEqual(reassembler.pending_count, 3)

    def test_sequence_tracker_bounds_unresolved_gaps(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(2, 0)
        for sequence in range(2, 10_000, 2):
            tracker.observe(2, sequence)
        self.assertLessEqual(tracker.lost, SequenceTracker.MAX_TRACKED_GAPS)

    def test_decodes_synthetic_screen_at_multiple_scales_and_offsets(self) -> None:
        packet = packetize_message(
            session=0xBEEF,
            sequence=12,
            event="CHAT_MSG_SAY",
            author="Main Tanki",
            text="{rt1} Questie: 5/5",
        )[0]
        for cell, offset in ((1, (2, 3)), (2, (3, 5)), (3, (7, 4)), (5, (11, 9))):
            with self.subTest(cell=cell, offset=offset):
                width, height, pixels = synthetic_frame(
                    packet, cell=cell, offset=offset
                )
                decoded = OpticalFrameDecoder().decode(width, height, pixels)
                self.assertEqual(decoded, packet)


if __name__ == "__main__":
    unittest.main()
