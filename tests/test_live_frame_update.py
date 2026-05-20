"""SDI loopback test for live frame updates.

Verifies that `BlackmagicOutput.update_frame()` actually swaps the displayed
content after `display_static_frame()` has started the output. Without
this test, the in-place update path is unexercised; only the start-once
display path is covered by test_loopback.py and test_capture_as_uint16.py.

The test displays one solid colour, captures a frame to confirm what's
on the wire, calls update_frame with a different colour, captures again
and asserts the captured colour now matches the updated one (and not the
original). Uses RGB10 narrow-range output and uint16 capture so the
comparison is bit-exact via canonical narrow 16-bit codes (N << 6),
avoiding chroma-subsampling / matrix tolerance noise.

Requires a BNC cable connecting SDI OUT to SDI IN on the same device.
"""

import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import BlackmagicInput, BlackmagicOutput, DisplayMode, PixelFormat


pytestmark = pytest.mark.hardware


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = DisplayMode.HD1080p25


# Two distinct 10-bit triplets, well within narrow range and with different
# values per channel so a channel swap would be visible.
COLOR_A_10BIT = (700, 400, 200)
COLOR_B_10BIT = (200, 800, 500)

EXPECTED_A_UINT16 = tuple(c << 6 for c in COLOR_A_10BIT)
EXPECTED_B_UINT16 = tuple(c << 6 for c in COLOR_B_10BIT)


def _solid_uint16_frame(width, height, color_10bit):
    """Build a solid-colour RGB10 uint16 frame in canonical narrow 16-bit (N << 6)."""
    color_uint16 = tuple(c << 6 for c in color_10bit)
    return np.full((height, width, 3), color_uint16, dtype=np.uint16)


def _sample_center(rgb_uint16):
    """Sample a 5×5 block away from any edges; return the centre pixel as a tuple."""
    samples = rgb_uint16[100:105, 100:105, :].reshape(-1, 3)
    return tuple(int(c) for c in samples[len(samples) // 2])


def test_update_frame_swaps_displayed_content():
    """display_static_frame(A) → capture A → update_frame(B) → capture B."""
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        settings = output._device.get_video_settings(DISPLAY_MODE.value)
        width, height = settings.width, settings.height

        frame_a = _solid_uint16_frame(width, height, COLOR_A_10BIT)
        frame_b = _solid_uint16_frame(width, height, COLOR_B_10BIT)

        assert output.display_static_frame(
            frame_a, DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=True,
            output_narrow_range=True,
        ), "display_static_frame(frame_a) returned False"

        time.sleep(0.5)  # SDI signal lock

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise SDI input"

            captured_a = input_device.capture_frame_as_uint16(
                input_narrow_range=True, output_narrow_range=True,
            )
            assert captured_a is not None, "capture A returned None"
            assert _sample_center(captured_a) == EXPECTED_A_UINT16, (
                f"Before update: expected {EXPECTED_A_UINT16}, "
                f"got {_sample_center(captured_a)}"
            )

            assert output.update_frame(frame_b), "update_frame(frame_b) returned False"

            time.sleep(0.5)  # let the new frame settle on the wire

            captured_b = input_device.capture_frame_as_uint16(
                input_narrow_range=True, output_narrow_range=True,
            )
            assert captured_b is not None, "capture B returned None"

            sampled_b = _sample_center(captured_b)
            assert sampled_b == EXPECTED_B_UINT16, (
                f"After update: expected {EXPECTED_B_UINT16}, got {sampled_b}"
            )
            assert sampled_b != EXPECTED_A_UINT16, (
                "After update_frame the wire still shows the original colour — "
                "the update did not take effect"
            )
    finally:
        output.cleanup()
