"""SDI loopback test for capture_frame_as_uint16 wrapper methods.

Verifies the new high-level uint16 capture path end-to-end:

1. `test_capture_as_uint16_preserves_10bit_codes_narrow` — outputs a
   specific 10-bit R'G'B' value via `display_solid_color` with
   `pixel_format=RGB10` in narrow range, loops back through SDI, captures
   as uint16 with `input_narrow_range=True, output_narrow_range=True`, and
   asserts that the captured uint16 values are *exactly* the original
   10-bit codes LSB-padded (`N << 6`). Pure bit-shift, no rounding —
   bit-for-bit code preservation across the loopback.

2. `test_capture_as_uint16_preserves_10bit_codes_full` — counterpart that
   exercises the both-full branch. Outputs the same triplet as full-range
   10-bit codes and captures with both narrow flags False. Conversion here
   is arithmetic scaling (`N * 65535 / 1023`) rather than a bit shift; ±1
   code drift is accepted to absorb the C++ converter's rounding-mode choice.

3. `test_capture_as_uint16_with_metadata` — asserts the metadata-variant
   wrapper returns a well-formed dict with a uint16 `'rgb'` value and the
   same exact-match pixel values as the both-narrow test.

Requires a BNC cable connecting SDI OUT to SDI IN. The BGRA-source
promotion branch of `_convert_frame_to_int` (the new `<< 8` path) is
covered by `test_bgra_hdmi_loopback_uint16_via_wrapper` in
`test_hdmi_bgra_loopback.py`, since BGRA isn't a valid SDI format.
"""

import sys
import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import BlackmagicInput, BlackmagicOutput, DisplayMode, PixelFormat


pytestmark = pytest.mark.hardware


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = DisplayMode.HD1080p25

# A 10-bit R'G'B' triplet, distinct across channels so a channel-swap
# regression would be immediately visible in any pixel comparison.
# Valid as both a narrow-range code (well within 64-940) and a full-range
# code (within 0-1023).
TEST_COLOR_10BIT = (700, 400, 200)

# Expected uint16 values for the both-narrow path: 10-bit codes LSB-padded
# via `N << 6`. Exact, no rounding.
EXPECTED_UINT16_NARROW = tuple(c << 6 for c in TEST_COLOR_10BIT)  # (44800, 25600, 12800)

# Expected uint16 values for the both-full path: 10-bit codes scaled to
# 16-bit full range via `N * 65535 / 1023`. Computed with round-to-nearest;
# the test allows ±1 code drift to absorb internal rounding-mode choices.
EXPECTED_UINT16_FULL = tuple(round(c * 65535 / 1023) for c in TEST_COLOR_10BIT)
FULL_RANGE_TOLERANCE = 1


def test_capture_as_uint16_preserves_10bit_codes_narrow():
    """RGB10 narrow output → uint16 narrow capture is the 10-bit codes LSB-padded.

    Strongest possible round-trip test of the uint16 path's **both-narrow**
    branch: no subsampling, no matrix, and the conversion is a pure bit
    shift (`N << 6`) with no rounding. Any deviation here is a real
    regression.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            TEST_COLOR_10BIT,
            DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=True,
            output_narrow_range=True,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)  # SDI signal lock

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=True,
                output_narrow_range=True,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"
            assert captured.dtype == np.uint16, f"Expected uint16, got {captured.dtype}"
            assert captured.ndim == 3 and captured.shape[2] == 3, (
                f"Expected HxWx3, got {captured.shape}"
            )

            # Sample several pixels from a region away from the edges. With a
            # solid colour they should all be exactly EXPECTED_UINT16_NARROW.
            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                assert tuple(int(c) for c in pixel) == EXPECTED_UINT16_NARROW, (
                    f"Pixel sample {i}: expected {EXPECTED_UINT16_NARROW}, "
                    f"got {tuple(int(c) for c in pixel)}"
                )
    finally:
        output.cleanup()


def test_capture_as_uint16_preserves_10bit_codes_full():
    """RGB10 full-range output → uint16 full capture is the 10-bit codes scaled to 16-bit.

    Counterpart to the both-narrow test that covers the **both-full** branch
    of the uint16 path. The conversion here is arithmetic scaling
    (`N * 65535 / 1023`) rather than a bit shift, so ±1 code drift is
    accepted to absorb the C++ converter's internal rounding-mode choice.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            TEST_COLOR_10BIT,
            DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=False,
            output_narrow_range=False,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=False,
                output_narrow_range=False,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"
            assert captured.dtype == np.uint16, f"Expected uint16, got {captured.dtype}"

            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                for channel, (got, want) in enumerate(zip(pixel, EXPECTED_UINT16_FULL)):
                    drift = abs(int(got) - int(want))
                    assert drift <= FULL_RANGE_TOLERANCE, (
                        f"Pixel sample {i}, channel {channel}: expected {want} "
                        f"(within ±{FULL_RANGE_TOLERANCE}), got {int(got)} "
                        f"(drift {drift})"
                    )
    finally:
        output.cleanup()


def test_capture_as_uint16_with_metadata():
    """capture_frame_as_uint16_with_metadata returns the expected dict structure with uint16 'rgb'."""
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            TEST_COLOR_10BIT,
            DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=True,
            output_narrow_range=True,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            result = input_device.capture_frame_as_uint16_with_metadata(
                input_narrow_range=True,
                output_narrow_range=True,
            )
            assert result is not None, "capture_frame_as_uint16_with_metadata returned None"
            assert isinstance(result, dict)

            for key in ("rgb", "width", "height", "format", "mode", "colorspace",
                        "eotf", "input_narrow_range", "output_narrow_range"):
                assert key in result, f"Missing key {key!r}"

            rgb = result["rgb"]
            assert isinstance(rgb, np.ndarray)
            assert rgb.dtype == np.uint16
            assert rgb.shape == (result["height"], result["width"], 3)

            # Same exact-value check as the both-narrow non-metadata variant
            samples = rgb[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                assert tuple(int(c) for c in pixel) == EXPECTED_UINT16_NARROW, (
                    f"Pixel sample {i}: expected {EXPECTED_UINT16_NARROW}, "
                    f"got {tuple(int(c) for c in pixel)}"
                )

            assert result["input_narrow_range"] is True
            assert result["output_narrow_range"] is True
    finally:
        output.cleanup()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
