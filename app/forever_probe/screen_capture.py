from __future__ import annotations

import ctypes
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from ctypes import wintypes


SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0


@dataclass(frozen=True, slots=True)
class ScreenRegion:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_corners(cls, x1: int, y1: int, x2: int, y2: int) -> "ScreenRegion":
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return cls(left, top, right - left, bottom - top)

    @property
    def valid(self) -> bool:
        return self.width >= 40 and self.height >= 20


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    width: int
    height: int
    bgra: bytes


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def enable_dpi_awareness() -> None:
    """Use physical screen coordinates when Windows display scaling is enabled."""
    try:
        per_monitor_v2 = ctypes.c_void_p(-4)
        if not ctypes.windll.user32.SetProcessDpiAwarenessContext(per_monitor_v2):
            ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def capture_bgra(region: ScreenRegion) -> CapturedFrame:
    """Capture a screen region into a top-down 32-bit BGRA buffer."""
    if not region.valid:
        raise ValueError("Selected screen region is too small")
    if not hasattr(ctypes, "windll"):
        raise OSError("Screen capture is supported only on Windows")

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    screen_dc = user32.GetDC(None)
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, region.width, region.height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    bitmap_selected = True
    try:
        copied = gdi32.BitBlt(
            memory_dc,
            0,
            0,
            region.width,
            region.height,
            screen_dc,
            region.left,
            region.top,
            SRCCOPY,
        )
        if not copied:
            raise OSError("Windows BitBlt screen capture failed")

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = region.width
        header.biHeight = -region.height
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = BI_RGB
        header.biSizeImage = region.width * region.height * 4
        info = BITMAPINFO()
        info.bmiHeader = header
        pixels = ctypes.create_string_buffer(header.biSizeImage)
        gdi32.SelectObject(memory_dc, previous)
        bitmap_selected = False
        rows = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            region.height,
            pixels,
            ctypes.byref(info),
            DIB_RGB_COLORS,
        )
        if rows != region.height:
            raise OSError("Windows GetDIBits screen capture failed")

        return CapturedFrame(region.width, region.height, pixels.raw)
    finally:
        if bitmap_selected:
            gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


def capture_bmp(region: ScreenRegion, destination: Path) -> int:
    """Capture a screen region into a 32-bit BMP and return its CRC32."""
    frame = capture_bgra(region)
    file_header = struct.pack(
        "<2sIHHI", b"BM", 14 + 40 + len(frame.bgra), 0, 0, 14 + 40
    )
    dib_header = struct.pack(
        "<IiiHHIIiiII",
        40,
        frame.width,
        -frame.height,
        1,
        32,
        BI_RGB,
        len(frame.bgra),
        0,
        0,
        0,
        0,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(file_header + dib_header + frame.bgra)
    return zlib.crc32(frame.bgra)

