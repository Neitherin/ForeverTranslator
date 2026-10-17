from __future__ import annotations

import tkinter as tk
import tempfile
import threading
import queue
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from .diagnostics import ProbeDiagnostics
from .installation import install_addon
from .models import ChatMessage
from .optical import (
    CONTROL_EVENT,
    NoOpticalFrame,
    OpticalDecodeError,
    OpticalFrameDecoder,
    OpticalPacket,
    PacketReassembler,
    SequenceTracker,
)
from .parser import parse_chat_line
from .ocr import TesseractEngine, find_tesseract, has_ascii_path
from .screen_capture import ScreenRegion, capture_bgra, capture_bmp
from .tailer import FileFollower
from .settings import AppSettings
from .translation import (
    OfflineTranslator,
    OcrChatMessage,
    parse_ocr_messages,
    parse_wow_text,
)
from .resources import model_directory


CHANNEL_COLORS = {
    "SAY": "#FFFFFF",
    "YELL": "#FF3F40",
    "WHISPER": "#FF80FF",
    "WHISPER_INFORM": "#FF80FF",
    "PARTY": "#AAAFFF",
    "PARTY_LEADER": "#77A5FF",
    "RAID": "#FF7F00",
    "RAID_LEADER": "#FF7F00",
    "RAID_WARNING": "#FF4800",
    "GUILD": "#40FF40",
    "OFFICER": "#40C040",
    "INSTANCE_CHAT": "#FF7D01",
    "INSTANCE_CHAT_LEADER": "#FF7D01",
    "CHANNEL": "#F4B7A8",
    "EMOTE": "#FF7F3F",
    "SYSTEM": "#FFFF00",
}

CHANNEL_LABELS = {
    "SAY": "Say",
    "YELL": "Yell",
    "WHISPER": "/w",
    "WHISPER_INFORM": "To",
    "PARTY": "Party",
    "PARTY_LEADER": "Party",
    "RAID": "Raid",
    "RAID_LEADER": "Raid",
    "RAID_WARNING": "Raid warning",
    "GUILD": "Guild",
    "OFFICER": "Officer",
    "INSTANCE_CHAT": "Instance",
    "INSTANCE_CHAT_LEADER": "Instance",
    "CHANNEL": "World",
    "EMOTE": "Emote",
    "SYSTEM": "System",
}

CLASS_COLORS = {
    "WARRIOR": "#C69B6D",
    "PALADIN": "#F48CBA",
    "HUNTER": "#AAD372",
    "ROGUE": "#FFF468",
    "PRIEST": "#FFFFFF",
    "DEATHKNIGHT": "#C41E3A",
    "SHAMAN": "#0070DD",
    "MAGE": "#3FC7EB",
    "WARLOCK": "#8788EE",
    "MONK": "#00FF98",
    "DRUID": "#FF7C0A",
    "DEMONHUNTER": "#A330C9",
    "EVOKER": "#33937F",
}


def channel_color(channel: str) -> str:
    return CHANNEL_COLORS.get(channel.upper(), "#F0F0F0")


def channel_label(channel: str) -> str:
    normalized = channel.upper()
    return CHANNEL_LABELS.get(normalized, normalized.replace("_", " ").title())


def class_color(player_class: str | None) -> str | None:
    if not player_class:
        return None
    return CLASS_COLORS.get(player_class.upper())


class ProbeWindow:
    POLL_MS = 100
    OPTICAL_POLL_MS = 30
    OUTGOING_PLACEHOLDER = "Napiš česky a stiskni Enter…"

    def __init__(
        self,
        root: tk.Tk,
        *,
        log_path: Path | None,
        simulate: bool,
        start_at_end: bool,
        ocr_mode: bool = False,
        optical_mode: bool = False,
    ) -> None:
        if ocr_mode and optical_mode:
            raise ValueError("OCR and optical modes are mutually exclusive")
        self.root = root
        self.log_path = log_path
        self.simulate = simulate
        self.ocr_mode = ocr_mode
        self.optical_mode = optical_mode
        self.follower = (
            FileFollower(log_path, start_at_end=start_at_end)
            if log_path and not (ocr_mode or optical_mode)
            else None
        )
        source = (
            "optical screen transport"
            if optical_mode
            else (
                "ocr screen region"
                if ocr_mode
                else ("simulation" if simulate else str(log_path or "missing"))
            )
        )
        self.diagnostics = ProbeDiagnostics(source)
        self.messages: deque[ChatMessage] = deque(maxlen=10)
        self._simulation_index = 0
        self.ocr_region: ScreenRegion | None = (
            ScreenRegion(0, 0, 320, 320) if optical_mode else None
        )
        self.tesseract_path = find_tesseract() if ocr_mode else None
        self.ocr_engine = (
            TesseractEngine(self.tesseract_path) if self.tesseract_path else None
        )
        self._ocr_busy = False
        self._ocr_results: queue.Queue[tuple[str, str]] = queue.Queue()
        self.ocr_error: str | None = None
        self._last_capture_crc: int | None = None
        self._last_ocr_text = ""
        self._ocr_image = Path(tempfile.gettempdir()) / "forever-probe-ocr.bmp"
        self._ocr_messages: list[OcrChatMessage] = []
        self._optical_messages: deque[OcrChatMessage] = deque(maxlen=10)
        self._optical_decoder = OpticalFrameDecoder() if optical_mode else None
        self._optical_reassembler = PacketReassembler() if optical_mode else None
        self._optical_sequences = SequenceTracker() if optical_mode else None
        self._optical_busy = False
        self._optical_connected = False
        self._optical_results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._optical_corrupt = 0
        self._optical_decoded = 0
        self._translations: dict[tuple[str, str | None, str], str] = {}
        self._translation_pending: set[tuple[str, str | None, str]] = set()
        self._translation_jobs: queue.Queue[tuple[str, object] | None] = queue.Queue()
        self._translation_results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._translation_ready = False
        self._translation_error: str | None = None
        self._settings = AppSettings.load()
        self._geometry_save_after: str | None = None
        self._title_restore_after: str | None = None
        self._closing = False
        self._outgoing_busy = False
        self._placeholder_active = False
        self._drag_offset = (0, 0)
        self._resize_origin = (0, 0, 0, 0)

        root.title("Forever Translator")
        root.overrideredirect(True)
        root.geometry(self._settings.geometry)
        root.minsize(420, 300)
        root.resizable(True, True)
        root.configure(bg="#090b10")
        root.attributes("-topmost", self._settings.always_on_top)
        root.attributes("-alpha", 0.90)

        self.status_var = tk.StringVar()
        self.metrics_var = tk.StringVar()
        self.source_var = tk.StringVar(value=f"Zdroj: {source}")
        self._incoming_model_available = model_directory("en-cs").joinpath(
            "model.bin"
        ).is_file()
        self._outgoing_model_available = model_directory("cs-en").joinpath(
            "model.bin"
        ).is_file()
        self.title_var = tk.StringVar(
            value="Forever Translator — OFFLINE PŘEKLAD SE NAČÍTÁ"
            if self._incoming_model_available
            else "Forever Translator — CHYBÍ MODEL EN→CZ"
        )
        self.outgoing_status_var = tk.StringVar(
            value="Napiš česky. Překlad se zkopíruje do schránky."
        )
        self.always_on_top_var = tk.BooleanVar(value=self._settings.always_on_top)

        composer = tk.Frame(root, bg="#090b10", padx=12)
        composer.pack(fill="x", side="bottom", pady=(5, 10))
        self.outgoing_entry = tk.Entry(
            composer,
            bg="#15171b",
            fg="#737982",
            insertbackground="#f0f0f0",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self.outgoing_entry.pack(fill="x", ipady=6)
        self._show_outgoing_placeholder()
        self.outgoing_entry.bind("<FocusIn>", self._clear_outgoing_placeholder)
        self.outgoing_entry.bind("<FocusOut>", self._restore_outgoing_placeholder)
        self.outgoing_entry.bind("<Return>", self.translate_outgoing)

        self.chat_container = tk.Frame(root, bg="#090909")
        self.chat_container.pack(fill="both", expand=True)
        self.chat = tk.Text(
            self.chat_container,
            height=10,
            bg="#090909",
            fg="#f0f0f0",
            insertbackground="#f0f0f0",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=14,
            pady=12,
            spacing3=7,
            font=("Segoe UI", 10),
            state="disabled",
            wrap="word",
        )
        for channel, color in CHANNEL_COLORS.items():
            self.chat.tag_configure(
                f"channel_{channel}",
                foreground=color,
                font=("Segoe UI", 11, "bold"),
            )
        self.chat.tag_configure(
            "channel_UNKNOWN", foreground="#F0F0F0", font=("Segoe UI", 11, "bold")
        )
        for player_class, color in CLASS_COLORS.items():
            self.chat.tag_configure(
                f"class_{player_class}",
                foreground=color,
                font=("Segoe UI", 11, "bold"),
            )
        self.chat.tag_configure(
            "original", foreground="#858991", font=("Segoe UI", 9)
        )
        self._link_tags: set[str] = set()
        self.chat.pack(fill="both", expand=True)

        self.onboarding_status_var = tk.StringVar(
            value="Čekám, až aplikace uvidí datovou mřížku ve WoW…"
        )
        self.onboarding = tk.Frame(
            self.chat_container,
            bg="#090909",
            padx=20,
            pady=16,
        )
        onboarding_header = tk.Frame(self.onboarding, bg="#090909")
        onboarding_header.pack(fill="x", pady=(0, 7))
        onboarding_title = tk.Label(
            onboarding_header,
            text="První spuštění",
            bg="#090909",
            fg="#72D5E3",
            anchor="w",
            font=("Segoe UI", 17, "bold"),
        )
        onboarding_title.pack(side="left", fill="x", expand=True)
        onboarding_close = tk.Button(
            onboarding_header,
            text="×",
            command=self.close,
            bg="#090909",
            fg="#858991",
            activebackground="#171A1F",
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            padx=8,
            font=("Segoe UI", 13),
        )
        onboarding_close.pack(side="right")
        onboarding_steps = tk.Label(
            self.onboarding,
            text=(
                "1. Vyber složku WoW s Wow.exe nebo WowB.exe.\n"
                "2. Ve WoW zapni addon Forever Translator Probe.\n"
                "3. Pokud hra běží, napiš /reload."
            ),
            bg="#090909",
            fg="#E6E7E9",
            anchor="w",
            justify="left",
            wraplength=360,
            font=("Segoe UI", 10),
        )
        onboarding_steps.pack(fill="x")
        install_button = tk.Button(
            self.onboarding,
            text="Vybrat WoW a nainstalovat addon",
            command=self.install_addon,
            bg="#72D5E3",
            fg="#071013",
            activebackground="#93E6F0",
            activeforeground="#071013",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        install_button.pack(fill="x", pady=(12, 6))
        select_block_button = tk.Button(
            self.onboarding,
            text="Mřížka je jinde – vybrat datový blok ručně",
            command=self.select_ocr_region,
            bg="#171A1F",
            fg="#C8CCD2",
            activebackground="#22262D",
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=7,
            font=("Segoe UI", 9),
        )
        select_block_button.pack(fill="x")
        onboarding_status = tk.Label(
            self.onboarding,
            textvariable=self.onboarding_status_var,
            bg="#090909",
            fg="#858991",
            anchor="w",
            justify="left",
            wraplength=360,
            font=("Segoe UI", 9),
        )
        onboarding_status.pack(fill="x", pady=(10, 0))
        self._onboarding_drag_widgets = (
            self.onboarding,
            onboarding_header,
            onboarding_title,
            onboarding_steps,
            onboarding_status,
        )
        self.resize_handle = tk.Frame(
            root, width=14, height=14, bg="#090909", cursor="size_nw_se"
        )
        self.resize_handle.place(relx=1.0, rely=1.0, anchor="se")
        self.resize_handle.bind("<ButtonPress-1>", self._start_resize)
        self.resize_handle.bind("<B1-Motion>", self._resize_window)
        self.chat.bind("<ButtonPress-1>", self._start_drag)
        self.chat.bind("<B1-Motion>", self._drag_window)

        self.context_menu = tk.Menu(root, tearoff=False)
        self.context_menu.add_checkbutton(
            label="Vždy nahoře",
            variable=self.always_on_top_var,
            command=self._toggle_topmost,
        )
        if ocr_mode:
            self.context_menu.add_command(
                label="Vybrat tesseract.exe", command=self.select_tesseract
            )
            self.context_menu.add_command(
                label="Vybrat oblast OCR", command=self.select_ocr_region
            )
        elif optical_mode:
            self.context_menu.add_command(
                label="Vybrat datový blok", command=self.select_ocr_region
            )
        else:
            self.context_menu.add_command(
                label="Vybrat WoWChatLog.txt", command=self.select_log
            )
        self.context_menu.add_command(label="Instalovat addon", command=self.install_addon)
        self.context_menu.add_command(label="Diagnostika", command=self._show_diagnostics)
        self.context_menu.add_command(label="Uložit report", command=self.save_report)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Zavřít", command=self.close)
        for widget in (root, self.chat, self.outgoing_entry, *self._onboarding_drag_widgets):
            widget.bind("<Button-3>", self._show_context_menu)
        for widget in self._onboarding_drag_widgets:
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag_window)

        if optical_mode:
            self._show_onboarding()

        self._refresh_status()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Configure>", self._schedule_geometry_save)
        root.after(self.POLL_MS, self._poll)
        if simulate:
            root.after(250, self._emit_simulated)
        if ocr_mode:
            root.after(800, self._poll_ocr)
        elif optical_mode:
            root.after(self.OPTICAL_POLL_MS, self._poll_optical)
        if self._incoming_model_available:
            threading.Thread(target=self._translation_worker, daemon=True).start()

    def _emit_simulated(self) -> None:
        samples = (
            "[SAY] [Tester]: Ahoj, česká diakritika funguje.",
            "[PARTY] [Healer]: Wait for mana please.",
            "[1. General] [Tank-Realm]: Anyone for the dungeon?",
            "Unknown beta format is retained verbatim.",
        )
        text = samples[self._simulation_index % len(samples)]
        now = datetime.now().astimezone()
        stamp = now.strftime("%m/%d %H:%M:%S.%f")[:-3]
        message = parse_chat_line(f"{stamp}  {text}", received_at=now)
        message = ChatMessage(
            message.timestamp,
            message.channel,
            message.author,
            message.text,
            message.raw,
            message.received_at,
            source="simulation",
        )
        self._accept(message)
        self._simulation_index += 1
        self.root.after(1800, self._emit_simulated)

    def _poll(self) -> None:
        if self.follower:
            self.follower.poll(self._accept_line)
        self._drain_translation_results()
        self._refresh_status()
        self.root.after(self.POLL_MS, self._poll)

    def _accept_line(self, line: str) -> None:
        if line.strip():
            self._accept(parse_chat_line(line))

    def _accept(self, message: ChatMessage) -> None:
        self.diagnostics.observe(message)
        self.messages.append(message)
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        for item in self.messages:
            author = f"{item.author}: " if item.author else ""
            tag = self._channel_tag(item.channel)
            self.chat.insert("end", f"[{item.channel}] {author}{item.text}\n", tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")
        self._refresh_status()

    def _refresh_status(self) -> None:
        summary = self.diagnostics.summary()
        source_exists = self.log_path is not None and self.log_path.exists()
        if self.simulate:
            headline = "SIMULATION — živá integrace zůstává UNVERIFIED"
        elif self.ocr_mode and self.ocr_error:
            headline = f"OCR ERROR — {self.ocr_error.splitlines()[0]}"
        elif self.ocr_mode and self.tesseract_path is None:
            headline = "BLOCKED — Tesseract OCR nebyl nalezen"
        elif self.ocr_mode and self.ocr_region is None:
            headline = "UNVERIFIED — vyberte oblast OCR"
        elif self.ocr_mode:
            headline = f"{summary['status']} — OCR oblast je aktivní"
        elif self.optical_mode and self.ocr_region is None:
            headline = "UNVERIFIED — vyberte oblast datového bloku"
        elif self.optical_mode:
            latest = self._optical_sequences.latest if self._optical_sequences else None
            lost = self._optical_sequences.lost if self._optical_sequences else 0
            seq = "—" if latest is None else str(latest)
            headline = (
                f"{summary['status']} — optical seq {seq}, lost {lost}, "
                f"bad {self._optical_corrupt}"
            )
        elif not source_exists:
            headline = "UNVERIFIED — soubor logu nebyl nalezen"
        else:
            headline = f"{summary['status']} — soubor logu je dostupný"
        self.status_var.set(headline)
        latency = summary["latency_ms"]
        p50 = "—" if latency["p50"] is None else f"{latency['p50']:.0f} ms"
        p95 = "—" if latency["p95"] is None else f"{latency['p95']:.0f} ms"
        counts = ", ".join(
            f"{name}:{count}" for name, count in summary["channel_counts"].items()
        ) or "žádné zprávy"
        self.metrics_var.set(f"p50 {p50} | p95 {p95} | {counts}")

    def save_report(self) -> None:
        default = f"probe-report-{datetime.now():%Y%m%d-%H%M%S}.json"
        selected = filedialog.asksaveasfilename(
            title="Uložit anonymní diagnostický report",
            defaultextension=".json",
            initialfile=default,
            filetypes=(("JSON", "*.json"),),
        )
        if selected:
            self.diagnostics.save(Path(selected))

    def select_ocr_region(self) -> None:
        if self.ocr_mode and self.tesseract_path is None:
            self.status_var.set("BLOCKED — nejprve nainstalujte Tesseract OCR")
            return
        self.root.withdraw()
        selector = tk.Toplevel(self.root)
        selector.attributes("-fullscreen", True)
        selector.attributes("-topmost", True)
        selector.attributes("-alpha", 0.28)
        selector.configure(bg="black")
        canvas = tk.Canvas(selector, bg="black", cursor="crosshair", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        start: dict[str, int | None] = {"x": None, "y": None, "rect": None}

        def on_press(event: tk.Event) -> None:
            start["x"], start["y"] = event.x_root, event.y_root
            start["rect"] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline="#00ffff", width=3
            )

        def on_drag(event: tk.Event) -> None:
            if start["rect"] is not None and start["x"] is not None and start["y"] is not None:
                canvas.coords(
                    start["rect"],
                    start["x"],
                    start["y"],
                    event.x_root,
                    event.y_root,
                )

        def finish(event: tk.Event) -> None:
            selection_error = False
            if start["x"] is not None and start["y"] is not None:
                region = ScreenRegion.from_corners(
                    start["x"], start["y"], event.x_root, event.y_root
                )
                minimum = 48 if self.optical_mode else 40
                if region.width < minimum or region.height < minimum:
                    selection_error = True
                elif region.valid:
                    self.ocr_region = region
                    self.ocr_error = None
                    self._last_capture_crc = None
                    self.source_var.set(
                        f"Zdroj: {'OCR' if self.ocr_mode else 'OPTICAL'} "
                        f"{region.left},{region.top} {region.width}×{region.height}"
                    )
            selector.destroy()
            self.root.deiconify()
            self._refresh_status()
            if selection_error:
                messagebox.showwarning(
                    "Výběr datového bloku",
                    "Oblast je příliš malá. Označte celou mřížku i s fialovým rámečkem.",
                    parent=self.root,
                )

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", finish)
        selector.bind("<Escape>", lambda _event: (selector.destroy(), self.root.deiconify()))

    def select_tesseract(self) -> None:
        selected = filedialog.askopenfilename(
            title="Vyberte tesseract.exe",
            filetypes=(("Tesseract OCR", "tesseract.exe"), ("Programy", "*.exe")),
        )
        if not selected:
            return
        executable = Path(selected)
        if not has_ascii_path(executable):
            self.tesseract_path = executable
            self.ocr_engine = None
            self.ocr_error = (
                "Cesta k Tesseractu obsahuje diakritiku. Přesuňte celou instalaci "
                "například do D:\\Tesseract-OCR a vyberte nový tesseract.exe."
            )
            self._refresh_status()
            return
        self.tesseract_path = executable
        self.ocr_engine = TesseractEngine(executable)
        self.ocr_error = None
        self._last_capture_crc = None
        self._refresh_status()

    def _poll_ocr(self) -> None:
        try:
            while True:
                kind, value = self._ocr_results.get_nowait()
                if kind == "text":
                    self._accept_ocr(value)
                else:
                    self.ocr_error = value
                    self.chat.configure(state="normal")
                    self.chat.delete("1.0", "end")
                    self.chat.insert("end", f"OCR ERROR\n\n{value}")
                    self.chat.configure(state="disabled")
        except queue.Empty:
            pass
        self._drain_translation_results()
        if (
            self.ocr_engine
            and self.ocr_region
            and not self._ocr_busy
            and self.ocr_error is None
        ):
            self._ocr_busy = True
            threading.Thread(target=self._ocr_worker, daemon=True).start()
        self.root.after(800, self._poll_ocr)

    def _poll_optical(self) -> None:
        try:
            while True:
                kind, value = self._optical_results.get_nowait()
                if kind == "packet":
                    self._accept_optical_packet(value)
                elif kind == "corrupt":
                    self._optical_corrupt += 1
        except queue.Empty:
            pass
        self._drain_translation_results()
        if self.ocr_region and not self._optical_busy:
            self._optical_busy = True
            threading.Thread(target=self._optical_worker, daemon=True).start()
        self._refresh_status()
        self.root.after(self.OPTICAL_POLL_MS, self._poll_optical)

    def _optical_worker(self) -> None:
        try:
            assert self.ocr_region is not None
            assert self._optical_decoder is not None
            frame = capture_bgra(self.ocr_region)
            packet = self._optical_decoder.decode(
                frame.width, frame.height, frame.bgra
            )
            self._optical_results.put(("packet", packet))
        except NoOpticalFrame:
            pass
        except OpticalDecodeError as error:
            self._optical_results.put(("corrupt", str(error)))
        except Exception as error:
            self._optical_results.put(("corrupt", str(error)))
        finally:
            self._optical_busy = False

    def _accept_optical_packet(self, value: object) -> None:
        if not isinstance(value, OpticalPacket):
            return
        if not self._optical_connected:
            self._optical_connected = True
            self._hide_onboarding()
        assert self._optical_reassembler is not None
        try:
            message = self._optical_reassembler.accept(value)
        except OpticalDecodeError:
            self._optical_corrupt += 1
            return
        if message is None:
            return
        if message.event == CONTROL_EVENT:
            return
        assert self._optical_sequences is not None
        self._optical_sequences.observe(message.session, message.sequence)
        self._optical_decoded += 1
        now = datetime.now().astimezone()
        channel = message.event.removeprefix("CHAT_MSG_") or "UNKNOWN"
        chat_message = ChatMessage(
            None,
            channel,
            message.author,
            message.text,
            message.text,
            now,
            source="optical",
        )
        self.diagnostics.observe(chat_message)
        self.messages.appendleft(chat_message)
        item = OcrChatMessage(
            channel, message.author, message.text, message.player_class
        )
        self._optical_messages.append(item)
        self._set_translation_messages(list(self._optical_messages))

    def _ocr_worker(self) -> None:
        try:
            assert self.ocr_region is not None
            assert self.ocr_engine is not None
            checksum = capture_bmp(self.ocr_region, self._ocr_image)
            if checksum == self._last_capture_crc:
                return
            self._last_capture_crc = checksum
            text = self.ocr_engine.recognize(self._ocr_image)
            if text and text != self._last_ocr_text:
                self._last_ocr_text = text
                self._ocr_results.put(("text", text))
        except Exception as error:
            self._ocr_results.put(("error", str(error)))
        finally:
            self._ocr_busy = False

    def _accept_ocr(self, text: str) -> None:
        now = datetime.now().astimezone()
        message = ChatMessage(None, "OCR", None, text, text, now, source="ocr")
        self.diagnostics.observe(message)
        self.messages.clear()
        self.messages.append(message)
        self._set_translation_messages(parse_ocr_messages(text), fallback_text=text)

    def _set_translation_messages(
        self, messages: list[OcrChatMessage], *, fallback_text: str = ""
    ) -> None:
        self._ocr_messages = messages
        new_jobs: list[tuple[tuple[str, str | None, str], str]] = []
        for item in self._ocr_messages:
            key = item.cache_key
            if (
                item.text
                and key not in self._translations
                and key not in self._translation_pending
            ):
                self._translation_pending.add(key)
                new_jobs.append((key, item.text))
        if new_jobs and self._translation_ready:
            self._translation_jobs.put(("incoming", new_jobs))
        self._render_ocr(fallback_text)
        self._refresh_status()

    def _render_ocr(self, fallback_text: str = "") -> None:
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        if not self._ocr_messages:
            if fallback_text:
                self.chat.insert("end", fallback_text, "original")
        else:
            for item in self._ocr_messages:
                tag = self._channel_tag(item.channel)
                translated = self._translations.get(item.cache_key)
                if translated:
                    label = channel_label(item.channel)
                    self.chat.insert("end", f"[{label}] ", tag)
                    if item.author:
                        author_tag = self._class_tag(item.player_class) or tag
                        self.chat.insert("end", f"{item.author}: ", author_tag)
                    self._insert_wow_text(translated, tag, "translated")
                    self.chat.insert("end", "\n", tag)
                original_prefix = "EN: " if translated else ""
                self.chat.insert("end", original_prefix, "original")
                self._insert_wow_text(item.text, "original", "original")
                self.chat.insert("end", "\n", "original")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _insert_wow_text(self, text: str, base_tag: str, style: str) -> None:
        for segment in parse_wow_text(text):
            if not segment.is_link:
                self.chat.insert("end", segment.text, base_tag)
                continue
            color = segment.color or "#FFD100"
            tag = f"wow_link_{style}_{color[1:].lower()}"
            if tag not in self._link_tags:
                self.chat.tag_configure(tag, foreground=color, underline=True)
                self._link_tags.add(tag)
            self.chat.insert("end", segment.text, (base_tag, tag))

    def _channel_tag(self, channel: str) -> str:
        normalized = channel.upper()
        return (
            f"channel_{normalized}"
            if normalized in CHANNEL_COLORS
            else "channel_UNKNOWN"
        )

    def _class_tag(self, player_class: str | None) -> str | None:
        if not player_class:
            return None
        normalized = player_class.upper()
        return f"class_{normalized}" if normalized in CLASS_COLORS else None

    def _translation_worker(self) -> None:
        try:
            translators = {"en-cs": OfflineTranslator("en-cs")}
            self._translation_results.put(("ready", None))
            while True:
                job = self._translation_jobs.get()
                if job is None:
                    return
                kind, payload = job
                try:
                    if kind == "incoming":
                        jobs = payload
                        translated = translators["en-cs"].translate_batch(
                            text for _key, text in jobs
                        )
                        self._translation_results.put(
                            (
                                "translations",
                                list(zip((key for key, _text in jobs), translated)),
                            )
                        )
                    elif kind == "outgoing":
                        if "cs-en" not in translators:
                            translators["cs-en"] = OfflineTranslator("cs-en")
                        translated = translators["cs-en"].translate_batch([str(payload)])[0]
                        self._translation_results.put(("outgoing", translated))
                except Exception as error:
                    if kind == "incoming":
                        keys = [key for key, _text in payload]
                        self._translation_results.put(
                            ("incoming_error", (keys, str(error)))
                        )
                    else:
                        self._translation_results.put((f"{kind}_error", str(error)))
        except Exception as error:
            self._translation_results.put(("error", str(error)))

    def _drain_translation_results(self) -> None:
        try:
            while True:
                kind, value = self._translation_results.get_nowait()
                if kind == "ready":
                    self._translation_ready = True
                    self.title_var.set(
                        "Forever Translator — EN↔CZ OFFLINE"
                        if self._outgoing_model_available
                        else "Forever Translator — EN→CZ OFFLINE | CHYBÍ CZ→EN"
                    )
                    jobs = [
                        (item.cache_key, item.text)
                        for item in self._ocr_messages
                        if item.text and item.cache_key not in self._translations
                    ]
                    if jobs:
                        self._translation_jobs.put(("incoming", jobs))
                elif kind == "translations":
                    for key, translated in value:
                        self._translations[key] = translated
                        self._translation_pending.discard(key)
                    self._render_ocr()
                elif kind == "outgoing":
                    translated = str(value)
                    self.root.clipboard_clear()
                    self.root.clipboard_append(translated)
                    self.root.update_idletasks()
                    self.outgoing_status_var.set(
                        f"Zkopírováno do schránky: {translated}"
                    )
                    self._outgoing_busy = False
                    self.outgoing_entry.delete(0, "end")
                    self._show_transient_title("Zkopírováno do schránky")
                    self.outgoing_entry.focus_set()
                elif kind == "outgoing_error":
                    self.outgoing_status_var.set(f"Překlad se nezdařil: {value}")
                    self._outgoing_busy = False
                    self._show_transient_title("Překlad se nezdařil")
                elif kind == "incoming_error":
                    keys, error = value
                    for key in keys:
                        self._translation_pending.discard(key)
                    self._translation_error = str(error)
                    self._show_transient_title("Některé zprávy se nepodařilo přeložit")
                else:
                    self._translation_error = str(value)
                    self.title_var.set("Forever Translator — CHYBA PŘEKLADU")
        except queue.Empty:
            pass

    def translate_outgoing(self, _event: tk.Event | None = None) -> str:
        if self._placeholder_active or self._outgoing_busy:
            return "break"
        text = self.outgoing_entry.get().strip()
        if not text:
            self.outgoing_status_var.set("Nejdřív napiš českou zprávu.")
            self._show_transient_title("Nejdřív napiš českou zprávu")
            return "break"
        if not self._translation_ready:
            self.outgoing_status_var.set("Překladač se ještě načítá.")
            self._show_transient_title("Překladač se ještě načítá")
            return "break"
        if not self._outgoing_model_available:
            self.outgoing_status_var.set("V balíčku chybí offline model CZ→EN.")
            self._show_transient_title("Chybí offline model CZ→EN")
            return "break"
        self._outgoing_busy = True
        self.outgoing_status_var.set("Překládám do angličtiny…")
        self._show_transient_title("Překládám do angličtiny…")
        self._translation_jobs.put(("outgoing", text))
        return "break"

    def _show_transient_title(self, text: str) -> None:
        if self._title_restore_after is not None:
            self.root.after_cancel(self._title_restore_after)
        self.root.title(f"Forever Translator — {text}")
        self._title_restore_after = self.root.after(2400, self._restore_window_title)

    def _restore_window_title(self) -> None:
        self._title_restore_after = None
        self.root.title("Forever Translator")

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_offset = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )

    def _drag_window(self, event: tk.Event) -> None:
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.root.geometry(f"+{x}+{y}")

    def _start_resize(self, event: tk.Event) -> None:
        self._resize_origin = (
            event.x_root,
            event.y_root,
            self.root.winfo_width(),
            self.root.winfo_height(),
        )

    def _resize_window(self, event: tk.Event) -> None:
        start_x, start_y, width, height = self._resize_origin
        new_width = max(420, width + event.x_root - start_x)
        new_height = max(300, height + event.y_root - start_y)
        self.root.geometry(f"{new_width}x{new_height}")

    def _show_outgoing_placeholder(self) -> None:
        if self.outgoing_entry.get():
            return
        self._placeholder_active = True
        self.outgoing_entry.configure(fg="#737982")
        self.outgoing_entry.insert(0, self.OUTGOING_PLACEHOLDER)

    def _clear_outgoing_placeholder(self, _event: tk.Event | None = None) -> None:
        if self._placeholder_active:
            self.outgoing_entry.delete(0, "end")
            self._placeholder_active = False
        self.outgoing_entry.configure(fg="#f0f0f0")

    def _restore_outgoing_placeholder(self, _event: tk.Event | None = None) -> None:
        if not self.outgoing_entry.get():
            self._show_outgoing_placeholder()

    def _show_context_menu(self, event: tk.Event) -> None:
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _show_onboarding(self) -> None:
        if not self.optical_mode or self._optical_connected:
            return
        self.onboarding.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.onboarding.lift()
        self.resize_handle.lift()

    def _hide_onboarding(self) -> None:
        self.onboarding.place_forget()

    def _show_diagnostics(self) -> None:
        messagebox.showinfo(
            "Forever Translator — diagnostika",
            f"{self.status_var.get()}\n\n{self.source_var.get()}\n{self.metrics_var.get()}",
            parent=self.root,
        )

    def install_addon(self) -> None:
        selected = filedialog.askdirectory(
            title="Vyberte složku WoW verze (_retail_, _classic_ nebo _classic_beta_)"
        )
        if not selected:
            return
        try:
            target = install_addon(Path(selected))
        except (OSError, ValueError) as error:
            messagebox.showerror("Instalace addonu", str(error), parent=self.root)
            return
        self.onboarding_status_var.set(
            "Nainstalováno. Ve WoW addon zapni a napiš /reload. "
            "Čekám na mřížku…"
        )
        messagebox.showinfo(
            "Instalace addonu",
            f"Addon byl nainstalován do:\n{target}\n\nPokud WoW běží, proveďte /reload.",
            parent=self.root,
        )

    def _toggle_topmost(self) -> None:
        enabled = self.always_on_top_var.get()
        self.root.attributes("-topmost", enabled)
        self._settings.always_on_top = enabled
        self._settings.save()

    def _schedule_geometry_save(self, event: tk.Event) -> None:
        if event.widget is not self.root or self._closing:
            return
        if self._geometry_save_after is not None:
            self.root.after_cancel(self._geometry_save_after)
        self._geometry_save_after = self.root.after(400, self._save_geometry)

    def _save_geometry(self) -> None:
        self._geometry_save_after = None
        if self.root.state() == "normal":
            self._settings.geometry = self.root.geometry()
            self._settings.save()

    def select_log(self) -> None:
        selected = filedialog.askopenfilename(
            title="Vyberte WoWChatLog.txt",
            filetypes=(("WoW chat log", "WoWChatLog.txt"), ("Textové soubory", "*.txt")),
        )
        if not selected:
            return
        self.log_path = Path(selected)
        self.follower = FileFollower(self.log_path, start_at_end=True)
        self.diagnostics.source_label = str(self.log_path)
        self.source_var.set(f"Zdroj: {self.log_path}")
        self._refresh_status()

    def close(self) -> None:
        self._closing = True
        if self._title_restore_after is not None:
            self.root.after_cancel(self._title_restore_after)
            self._title_restore_after = None
        if self._geometry_save_after is not None:
            self.root.after_cancel(self._geometry_save_after)
            self._geometry_save_after = None
        if self.root.state() == "normal":
            self._settings.geometry = self.root.geometry()
        self._settings.always_on_top = self.always_on_top_var.get()
        self._settings.save()
        if self.follower:
            self.follower.flush_pending(self._accept_line)
        self._translation_jobs.put(None)
        self.root.destroy()

