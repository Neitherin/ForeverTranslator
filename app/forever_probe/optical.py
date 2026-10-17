from __future__ import annotations

import struct
from collections import deque
from dataclasses import dataclass


GRID_SIZE = 48
BITS_PER_CELL = 2
CELLS_PER_BYTE = 8 // BITS_PER_CELL
CONTROL_EVENT = "FT_HEARTBEAT"
BYTES_PER_ROW = GRID_SIZE // CELLS_PER_BYTE
SYNC_ROWS = 3
SYNC_BYTES = (
    bytes((0x1B,)) * BYTES_PER_ROW
    + bytes((0xE4,)) * BYTES_PER_ROW
    + bytes((0x55, 0xAA)) * (BYTES_PER_ROW // 2)
)
FRAME_BYTES = GRID_SIZE * GRID_SIZE // CELLS_PER_BYTE
PACKET_BYTES = FRAME_BYTES - len(SYNC_BYTES)
PACKET_MAGIC = b"FT"
PACKET_VERSION = 1
_HEADER = struct.Struct("<2sBHHBBH")
_CHECKSUM = struct.Struct("<H")
MAX_PACKET_PAYLOAD = PACKET_BYTES - _HEADER.size - _CHECKSUM.size


class OpticalDecodeError(ValueError):
    pass


class NoOpticalFrame(OpticalDecodeError):
    pass


@dataclass(frozen=True, slots=True)
class OpticalPacket:
    session: int
    sequence: int
    chunk_index: int
    chunk_count: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class OpticalMessage:
    session: int
    sequence: int
    event: str
    author: str | None
    text: str
    player_class: str | None = None


@dataclass(frozen=True, slots=True)
class GridGeometry:
    left: float
    top: float
    step_x: float
    step_y: float


def fletcher16(data: bytes) -> int:
    sum1 = 0
    sum2 = 0
    for value in data:
        sum1 = (sum1 + value) % 255
        sum2 = (sum2 + sum1) % 255
    return (sum2 << 8) | sum1


def encode_packet(packet: OpticalPacket) -> bytes:
    if not 0 <= packet.session <= 0xFFFF:
        raise ValueError("session must fit in uint16")
    if not 0 <= packet.sequence <= 0xFFFF:
        raise ValueError("sequence must fit in uint16")
    if not 0 <= packet.chunk_index < packet.chunk_count <= 0xFF:
        raise ValueError("invalid chunk index/count")
    if len(packet.payload) > MAX_PACKET_PAYLOAD:
        raise ValueError("packet payload is too large")
    body = _HEADER.pack(
        PACKET_MAGIC,
        PACKET_VERSION,
        packet.session,
        packet.sequence,
        packet.chunk_index,
        packet.chunk_count,
        len(packet.payload),
    ) + packet.payload
    encoded = body + _CHECKSUM.pack(fletcher16(body))
    return encoded.ljust(PACKET_BYTES, b"\0")


def decode_packet(data: bytes) -> OpticalPacket:
    if len(data) < _HEADER.size + _CHECKSUM.size:
        raise OpticalDecodeError("packet is truncated")
    magic, version, session, sequence, chunk_index, chunk_count, length = (
        _HEADER.unpack_from(data)
    )
    if magic != PACKET_MAGIC or version != PACKET_VERSION:
        raise NoOpticalFrame("packet magic/version not found")
    if chunk_count == 0 or chunk_index >= chunk_count:
        raise OpticalDecodeError("invalid packet chunk metadata")
    end = _HEADER.size + length
    checksum_end = end + _CHECKSUM.size
    if length > MAX_PACKET_PAYLOAD or checksum_end > len(data):
        raise OpticalDecodeError("invalid packet payload length")
    expected = _CHECKSUM.unpack_from(data, end)[0]
    actual = fletcher16(data[:end])
    if actual != expected:
        raise OpticalDecodeError("packet checksum mismatch")
    return OpticalPacket(session, sequence, chunk_index, chunk_count, data[_HEADER.size:end])


def encode_message_payload(
    event: str, author: str | None, text: str, player_class: str | None = None
) -> bytes:
    event_bytes = event.encode("utf-8")
    author_bytes = (author or "").encode("utf-8")
    text_bytes = text.encode("utf-8")
    class_bytes = (player_class or "").encode("utf-8")
    if any(len(value) > 0xFF for value in (event_bytes, author_bytes, class_bytes)):
        raise ValueError("event, author or player class is too long")
    if len(text_bytes) > 0xFFFF:
        raise ValueError("message text is too long")
    return (
        struct.pack("<BBH", len(event_bytes), len(author_bytes), len(text_bytes))
        + event_bytes
        + author_bytes
        + text_bytes
        + struct.pack("<B", len(class_bytes))
        + class_bytes
    )


def decode_message_payload(
    payload: bytes, *, session: int, sequence: int
) -> OpticalMessage:
    if len(payload) < 4:
        raise OpticalDecodeError("message payload is truncated")
    event_length, author_length, text_length = struct.unpack_from("<BBH", payload)
    message_end = 4 + event_length + author_length + text_length
    if message_end > len(payload):
        raise OpticalDecodeError("message payload lengths do not match")
    cursor = 4
    try:
        event = payload[cursor : cursor + event_length].decode("utf-8")
        cursor += event_length
        author_raw = payload[cursor : cursor + author_length].decode("utf-8")
        cursor += author_length
        text = payload[cursor:message_end].decode("utf-8")
        player_class = None
        if message_end < len(payload):
            class_length = payload[message_end]
            if message_end + 1 + class_length != len(payload):
                raise OpticalDecodeError("player class payload length does not match")
            class_raw = payload[message_end + 1 :].decode("utf-8")
            player_class = class_raw or None
    except UnicodeDecodeError as error:
        raise OpticalDecodeError("message payload is not valid UTF-8") from error
    return OpticalMessage(
        session, sequence, event, author_raw or None, text, player_class
    )


def packetize_message(
    *,
    session: int,
    sequence: int,
    event: str,
    author: str | None,
    text: str,
    player_class: str | None = None,
) -> list[OpticalPacket]:
    payload = encode_message_payload(event, author, text, player_class)
    chunks = [
        payload[offset : offset + MAX_PACKET_PAYLOAD]
        for offset in range(0, len(payload), MAX_PACKET_PAYLOAD)
    ] or [b""]
    if len(chunks) > 0xFF:
        raise ValueError("message needs too many chunks")
    return [
        OpticalPacket(session, sequence, index, len(chunks), chunk)
        for index, chunk in enumerate(chunks)
    ]


def raster_bytes(packet: OpticalPacket) -> bytes:
    return SYNC_BYTES + encode_packet(packet)


class PacketReassembler:
    def __init__(
        self, *, completed_capacity: int = 2048, pending_capacity: int = 256
    ) -> None:
        self._pending: dict[tuple[int, int], tuple[int, dict[int, bytes]]] = {}
        self._completed_order: deque[tuple[int, int]] = deque()
        self._completed: set[tuple[int, int]] = set()
        self._completed_capacity = completed_capacity
        self._pending_capacity = pending_capacity

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def accept(self, packet: OpticalPacket) -> OpticalMessage | None:
        key = packet.session, packet.sequence
        if key in self._completed:
            return None
        if key not in self._pending:
            self._pending[key] = packet.chunk_count, {}
            while len(self._pending) > self._pending_capacity:
                oldest = next(iter(self._pending))
                self._pending.pop(oldest, None)
        count, chunks = self._pending[key]
        if count != packet.chunk_count:
            self._pending.pop(key, None)
            raise OpticalDecodeError("chunk count changed within a message")
        chunks[packet.chunk_index] = packet.payload
        if len(chunks) != count:
            return None
        try:
            payload = b"".join(chunks[index] for index in range(count))
        except KeyError:
            return None
        self._pending.pop(key, None)
        message = decode_message_payload(
            payload, session=packet.session, sequence=packet.sequence
        )
        self._completed.add(key)
        self._completed_order.append(key)
        while len(self._completed_order) > self._completed_capacity:
            self._completed.discard(self._completed_order.popleft())
        return message


class SequenceTracker:
    MAX_TRACKED_GAPS = 4096

    def __init__(self) -> None:
        self.session: int | None = None
        self.latest: int | None = None
        self.missing: dict[int, None] = {}

    @property
    def lost(self) -> int:
        return len(self.missing)

    def observe(self, session: int, sequence: int) -> None:
        if session != self.session:
            self.session = session
            self.latest = sequence
            self.missing.clear()
            return
        assert self.latest is not None
        distance = (sequence - self.latest) & 0xFFFF
        if distance == 0:
            return
        if distance < 0x8000:
            if distance <= 4096:
                for step in range(1, distance):
                    missing = (self.latest + step) & 0xFFFF
                    if missing not in self.missing:
                        self.missing[missing] = None
                while len(self.missing) > self.MAX_TRACKED_GAPS:
                    self.missing.pop(next(iter(self.missing)))
            self.latest = sequence
            return
        self.missing.pop(sequence, None)


class OpticalFrameDecoder:
    def __init__(self) -> None:
        self._geometry: GridGeometry | None = None
        self._failed_with_geometry = 0

    @staticmethod
    def _pixel(bgra: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * width + x) * 4
        return bgra[offset], bgra[offset + 1], bgra[offset + 2]

    @staticmethod
    def _is_marker(pixel: tuple[int, int, int]) -> bool:
        blue, green, red = pixel
        return red >= 170 and blue >= 170 and green <= 120

    def _locate(self, width: int, height: int, bgra: bytes) -> GridGeometry:
        marker = bytearray(width * height)
        for y in range(height):
            row = y * width * 4
            for x in range(width):
                offset = row + x * 4
                blue, green, red = bgra[offset], bgra[offset + 1], bgra[offset + 2]
                if red >= 170 and blue >= 170 and green <= 120:
                    marker[y * width + x] = 1

        visited = bytearray(width * height)
        candidates: list[tuple[int, int, int, int, int]] = []
        for start, value in enumerate(marker):
            if not value or visited[start]:
                continue
            visited[start] = 1
            stack = [start]
            count = 0
            left = right = start % width
            top = bottom = start // width
            while stack:
                index = stack.pop()
                x, y = index % width, index // width
                count += 1
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
                for neighbor in (index - 1, index + 1, index - width, index + width):
                    if not 0 <= neighbor < len(marker):
                        continue
                    neighbor_x = neighbor % width
                    if abs(neighbor_x - x) > 1:
                        continue
                    if marker[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        stack.append(neighbor)
            component_width = right - left + 1
            component_height = bottom - top + 1
            if count >= 64 and component_width >= 45 and component_height >= 45:
                candidates.append((count, left, top, right, bottom))
        if not candidates:
            raise NoOpticalFrame("calibration border not found")
        _count, left, top, right, bottom = max(candidates)
        total_width = right - left + 1
        total_height = bottom - top + 1
        if abs(total_width - total_height) > max(3, int(max(total_width, total_height) * 0.04)):
            raise NoOpticalFrame("calibration border is not square")
        step_x = total_width / (GRID_SIZE + 2)
        step_y = total_height / (GRID_SIZE + 2)
        return GridGeometry(left + step_x, top + step_y, step_x, step_y)

    def _sample(self, width: int, height: int, bgra: bytes, geometry: GridGeometry) -> bytes:
        output = bytearray()
        current = 0
        cells = 0
        for row in range(GRID_SIZE):
            y = int(geometry.top + (row + 0.5) * geometry.step_y)
            if not 0 <= y < height:
                raise NoOpticalFrame("grid extends outside capture")
            for column in range(GRID_SIZE):
                x = int(geometry.left + (column + 0.5) * geometry.step_x)
                if not 0 <= x < width:
                    raise NoOpticalFrame("grid extends outside capture")
                blue, green, red = self._pixel(bgra, width, x, y)
                luminance = (red * 299 + green * 587 + blue * 114) // 1000
                if luminance >= 213:
                    symbol = 0
                elif luminance >= 128:
                    symbol = 1
                elif luminance >= 43:
                    symbol = 2
                else:
                    symbol = 3
                current = (current << BITS_PER_CELL) | symbol
                cells += 1
                if cells == CELLS_PER_BYTE:
                    output.append(current)
                    current = 0
                    cells = 0
        return bytes(output)

    def decode(self, width: int, height: int, bgra: bytes) -> OpticalPacket:
        if len(bgra) != width * height * 4:
            raise ValueError("BGRA buffer size does not match frame dimensions")
        if self._geometry is None:
            self._geometry = self._locate(width, height, bgra)
        try:
            frame = self._sample(width, height, bgra, self._geometry)
            if frame[: len(SYNC_BYTES)] != SYNC_BYTES:
                raise NoOpticalFrame("synchronization pattern does not match")
            packet = decode_packet(frame[len(SYNC_BYTES) :])
            self._failed_with_geometry = 0
            return packet
        except OpticalDecodeError:
            self._failed_with_geometry += 1
            if self._failed_with_geometry >= 3:
                self._geometry = None
                self._failed_with_geometry = 0
            raise
