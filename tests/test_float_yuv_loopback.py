"""SDI loopback test for the float32 RGB → YUV encoder path.

Complements test_loopback.py, which exercises YUV10 with uint16 input and
YUV8 with uint8 input but never pushes float through the YUV converters.
Most real upstream processing (HDR transfer functions, gamut mapping,
OCIO graphs) lives in float, so this is the most common usage of the
library and warrants explicit loopback coverage on top of the offline
colour-science parity check in test_colour_science_parity.py.

The high-level display_static_frame routes float32 input through
rgb_float_to_yuv10 / rgb_float_to_yuv8 automatically, so simply passing
a float pattern in exercises the float YUV path end-to-end.

Requires a BNC cable connecting SDI OUT to SDI IN on the same device.
"""

import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import (
    BlackmagicInput, BlackmagicOutput,
    DisplayMode, Matrix, PixelFormat, create_test_pattern,
)


pytestmark = [pytest.mark.hardware, pytest.mark.sdi, pytest.mark.loopback]


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = DisplayMode.HD1080p25
CAPTURE_TIMEOUT_MS = 10000


# (label, pixel_format, mean_tolerance, max_tolerance)
# Tolerances mirror the YUV cases in test_loopback.py — chroma subsampling
# and matrix-rounding float error dominate; bar boundaries account for
# most of the max error.
CASES = [
    ("YUV8",  PixelFormat.YUV8,  0.03, 0.20),
    ("YUV10", PixelFormat.YUV10, 0.02, 0.15),
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
def test_float_rgb_to_yuv_loopback(output_device, label, pixel_format, mean_tol, max_tol):
    """Float RGB → Y'CbCr (encode) → SDI → Y'CbCr → float RGB (decode) round-trips."""
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

    time.sleep(0.5)  # SDI signal lock

    with BlackmagicInput() as input_device:
        assert input_device.initialize(
            INPUT_DEVICE_INDEX,
            input_connection=decklink_io.InputConnection.SDI,
        ), f"Failed to initialise SDI input for {label}"

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
