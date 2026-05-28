#!/usr/bin/env python3
"""HDMI loopback test for BGRA capture from a Y'CbCr source.

Requires an HDMI cable from output to input on the same DeckLink device
(or two devices, with INPUT_DEVICE_INDEX overridden).

Outputs a 75% colour-bars pattern as `YUV10` over HDMI with explicit matrix
metadata (Rec.709 and Rec.2020 cases) and captures it back as `BGRA` via
the high-level `BlackmagicInput` wrapper. The SDK's hardware Y'CbCr → RGB
conversion is expected to:

1. Honour the matrix metadata signalled in the output frame (verified
   visually earlier with `capture_preview` Rec.709 ↔ Rec.2020 toggle; this
   test makes that quantitative).
2. Expand the narrow Y'CbCr range to full 8-bit BGRA (the documented
   assumption the library now relies on).

If both hold, the captured BGRA should match the source RGB pattern scaled
to 8-bit full range, within a tolerance that accounts for chroma
subsampling, matrix-conversion rounding, and 8-bit quantisation.

Run in isolation or before any test that puts the SDK into Y'CbCr lock-in
mode (see README HDMI Input Notes about mid-stream protocol switches).
"""

import sys
import time

import decklink_io
import numpy as np
import pytest
from blackmagic_io import BlackmagicInput, PixelFormat, create_test_pattern

pytestmark = [pytest.mark.hardware, pytest.mark.hdmi, pytest.mark.loopback]

OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = decklink_io.DisplayMode.HD1080p25

# 4:2:2 chroma subsampling + matrix conversion + 8-bit quantisation. Bar
# boundaries account for most of the error; bar interiors are typically
# within ±1.
PIXEL_TOLERANCE = 3


def _build_yuv10_frame(settings, matrix):
    """Build a 75% colour-bars pattern as narrow-range YUV10 v210."""
    rgb_pattern = create_test_pattern(
        settings.width, settings.height, pattern="bars"
    ) * 0.75
    frame_data = decklink_io.rgb_float_to_yuv10(
        rgb_pattern, settings.width, settings.height,
        matrix=matrix,
        output_narrow_range=True,
    )
    # Expected BGRA: source RGB float scaled to 8-bit full range. The SDK's
    # narrow→full conversion is expected to recover this from the wire.
    expected_rgb_uint8 = np.round(rgb_pattern * 255).astype(np.uint8)
    return expected_rgb_uint8, frame_data


@pytest.mark.parametrize(
    "matrix, name",
    [
        (decklink_io.Matrix.Rec709, "Rec709"),
        (decklink_io.Matrix.Rec2020, "Rec2020"),
    ],
)
def test_bgra_from_ycbcr_source(matrix, name):
    """Output narrow-range YUV10 (Rec.709 / Rec.2020), capture as BGRA."""
    output_device = decklink_io.DeckLinkOutput()
    assert output_device.initialize(OUTPUT_DEVICE_INDEX), \
        "Failed to initialize output device"

    try:
        # Signal matrix metadata explicitly; SDR EOTF.
        output_device.set_matrix(matrix)
        output_device.set_eotf(decklink_io.Eotf.SDR)

        settings = output_device.get_video_settings(DISPLAY_MODE)
        settings.format = decklink_io.PixelFormat.YUV10
        assert output_device.setup_output(settings), \
            "Failed to setup YUV10 output"

        expected_rgb_uint8, frame_data = _build_yuv10_frame(settings, matrix)
        assert output_device.set_frame_data(frame_data), \
            "Failed to set YUV10 frame data"
        assert output_device.display_frame(), \
            "Failed to display YUV10 frame"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.HDMI,
                pixel_format=PixelFormat.BGRA,
            ), "Failed to initialise BlackmagicInput on HDMI with BGRA"

            captured = input_device.capture_frame_as_uint8()
            assert captured is not None, \
                "capture_frame_as_uint8 returned None"

            diff = np.abs(captured.astype(int) - expected_rgb_uint8.astype(int))
            max_diff = int(diff.max())
            mean_diff = float(diff.mean())

            print(f"\n{name}: max diff = {max_diff}, mean = {mean_diff:.3f}")
            assert max_diff <= PIXEL_TOLERANCE, (
                f"{name} loopback exceeded ±{PIXEL_TOLERANCE}: "
                f"max diff = {max_diff}, mean = {mean_diff:.3f}"
            )
    finally:
        output_device.stop_output()
        output_device.cleanup()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
