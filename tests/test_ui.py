from __future__ import annotations

import unittest

from forever_probe.optical import OpticalPacket
from forever_probe.ui import ProbeWindow


class _FrameStub:
    def __init__(self) -> None:
        self.placed = False
        self.forgotten = False

    def place(self, **_kwargs: object) -> None:
        self.placed = True

    def place_forget(self) -> None:
        self.forgotten = True

    def lift(self) -> None:
        pass


class _ReassemblerStub:
    def accept(self, _packet: OpticalPacket) -> None:
        return None


class OnboardingTests(unittest.TestCase):
    def test_first_valid_optical_packet_hides_onboarding(self) -> None:
        window = object.__new__(ProbeWindow)
        window._optical_connected = False
        window.onboarding = _FrameStub()
        window._optical_reassembler = _ReassemblerStub()

        window._accept_optical_packet(OpticalPacket(1, 1, 0, 1, b"payload"))

        self.assertTrue(window._optical_connected)
        self.assertTrue(window.onboarding.forgotten)

    def test_onboarding_is_shown_only_while_optical_input_is_missing(self) -> None:
        window = object.__new__(ProbeWindow)
        window.optical_mode = True
        window._optical_connected = False
        window.onboarding = _FrameStub()
        window.resize_handle = _FrameStub()

        window._show_onboarding()

        self.assertTrue(window.onboarding.placed)

        window.onboarding.placed = False
        window._optical_connected = True
        window._show_onboarding()

        self.assertFalse(window.onboarding.placed)


if __name__ == "__main__":
    unittest.main()
