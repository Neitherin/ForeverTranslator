from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from forever_probe.optical import (  # noqa: E402
    BITS_PER_CELL,
    CELLS_PER_BYTE,
    GRID_SIZE,
    OpticalFrameDecoder,
    PacketReassembler,
    packetize_message,
    raster_bytes,
)
from forever_probe.screen_capture import (  # noqa: E402
    ScreenRegion,
    capture_bgra,
    enable_dpi_awareness,
)


CELL = 2
BORDER = CELL
PANEL = (GRID_SIZE + 2) * CELL


def main() -> int:
    enable_dpi_awareness()
    packet = packetize_message(
        session=0x1234,
        sequence=7,
        event="CHAT_MSG_PARTY",
        author="Loopback-Tank",
        text="Optical transport funguje — příliš žluťoučký kůň.",
    )[0]
    raster = raster_bytes(packet)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{PANEL}x{PANEL}+0+0")
    canvas = tk.Canvas(root, width=PANEL, height=PANEL, highlightthickness=0)
    canvas.pack()
    canvas.create_rectangle(0, 0, PANEL, PANEL, fill="#ff00ff", outline="")
    canvas.create_rectangle(
        BORDER,
        BORDER,
        BORDER + GRID_SIZE * CELL,
        BORDER + GRID_SIZE * CELL,
        fill="#ffffff",
        outline="",
    )
    palette = ("#ffffff", "#aaaaaa", "#555555", "#000000")
    for cell_index in range(GRID_SIZE * GRID_SIZE):
        value = raster[cell_index // CELLS_PER_BYTE]
        shift = BITS_PER_CELL * (CELLS_PER_BYTE - 1 - cell_index % CELLS_PER_BYTE)
        symbol = (value >> shift) & 0x03
        row, column = divmod(cell_index, GRID_SIZE)
        left = BORDER + column * CELL
        top = BORDER + row * CELL
        canvas.create_rectangle(
            left,
            top,
            left + CELL,
            top + CELL,
            fill=palette[symbol],
            outline="",
        )
    root.update_idletasks()
    root.update()

    frame = capture_bgra(ScreenRegion(0, 0, PANEL + 8, PANEL + 8))
    decoded = OpticalFrameDecoder().decode(frame.width, frame.height, frame.bgra)
    message = PacketReassembler().accept(decoded)
    root.destroy()
    if message is None or message.text != "Optical transport funguje — příliš žluťoučký kůň.":
        print("FAIL: loopback payload did not match")
        return 1
    print(
        f"PASS: session={message.session} seq={message.sequence} "
        f"event={message.event} author={message.author} text={message.text}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
