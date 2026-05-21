"""HDMI loopback tests for YUV10 and RGB12.

Existing HDMI coverage is limited to BGRA (test_hdmi_bgra_loopback.py),
RGB10 (test_hdr_metadata_loopback.py, test_hdmi_full_range_round_trip.py)
and the YCbCr-source BGRA capture path (test_hdmi_bgra_ycbcr_source.py).
The YUV10 and RGB12 output paths over HDMI are not independently
verified; this file closes that gap.

Requires an HDMI cable from output to input on the same DeckLink device.
Skips a case if the device does not support that pixel format for HDMI
output. Format negotiation may deliver the signal in a different
pixel format on the capture side (e.g. RGB12 may come back as RGB10);
`capture_frame_as_rgb` normalises any of these to float RGB.
"""

import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import (
    BlackmagicInput, BlackmagicOutput,
    DisplayMode, Matrix, PixelFormat, create_test_pattern,
)


pytestmark = [pytest.mark.hardware, pytest.mark.hdmi]


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = DisplayMode.HD1080p25
CAPTURE_TIMEOUT_MS = 10000


# (label, pixel_format, mean_tolerance, max_tolerance)
CASES = [
    ("YUV10", PixelFormat.YUV10, 0.02, 0.15),
    ("RGB12", PixelFormat.RGB12, 0.01, 0.05),
]


@pytest.fixture(scope="module")
def output_device():
    out = BlackmagicOutput()
    assert out.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"
    yield out
    out.cleanup()


@pytest.mark.parametrize(
    "label,pixel_format,mean_tol,max_tol",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_hdmi_loopback(output_device, label, pixel_format, mean_tol, max_tol):
    """Float RGB → pixel_format → HDMI → captured → float RGB round-trips."""
    if not output_device.is_pixel_format_supported(DISPLAY_MODE, pixel_format):
        pytest.skip(f"{DISPLAY_MODE.name} + {pixel_format.name} not supported by this device")

    settings = output_device._device.get_video_settings(DISPLAY_MODE.value)
    width, height = settings.width, settings.height

    rgb_pattern = create_test_pattern(width, height, pattern="bars") * 0.75

    assert output_device.display_static_frame(
        rgb_pattern, DISPLAY_MODE,
        pixel_format=pixel_format,
        matrix=Matrix.Rec709,
        input_narrow_range=False,
        output_narrow_range=True,
    ), f"display_static_frame failed for {label}"

    time.sleep(0.5)  # HDMI signal lock

    with BlackmagicInput() as input_device:
        assert input_device.initialize(
            INPUT_DEVICE_INDEX,
            input_connection=decklink_io.InputConnection.HDMI,
        ), f"Failed to initialise HDMI input for {label}"

        captured = input_device.capture_frame_as_rgb(timeout_ms=CAPTURE_TIMEOUT_MS)
        assert captured is not None, f"capture_frame_as_rgb returned None for {label}"
        assert captured.shape == rgb_pattern.shape, (
            f"{label}: captured shape {captured.shape} != source {rgb_pattern.shape}"
        )

        diff = np.abs(rgb_pattern - captured)
        mean_err = float(np.mean(diff))
        max_err = float(np.max(diff))

        assert mean_err < mean_tol, (
            f"{label}: mean error {mean_err:.4f} exceeds {mean_tol}"
        )
        assert max_err < max_tol, (
            f"{label}: max error {max_err:.4f} exceeds {max_tol}"
        )
