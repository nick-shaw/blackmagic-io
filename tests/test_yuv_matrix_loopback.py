"""SDI loopback tests for the Rec.601 and Rec.2020 Y'CbCr matrices.

test_loopback.py exercises Rec.709 only (HD1080p25 default). Rec.601 and
Rec.2020 matrix correctness is otherwise covered only by the offline
colour-science parity test, which can't catch hardware-level signalling
bugs (wrong VPID matrix, mis-tagged frames). These tests push float
RGB through the YUV converters at each matrix, capture over SDI, and
verify the round-trip via `capture_frame_as_rgb` — which decodes using
the captured frame's tagged matrix, so a wrong tag would either fail
the matrix decode or report the wrong Matrix enum.

- Rec.601: NTSC (720x486) + YUV8. The high-level API auto-selects Rec.601
  for SD modes, and the SDK signals Rec.601 in the VPID for SD content.
- Rec.2020: HD1080p25 + YUV10 with explicit Matrix.Rec2020. The high-level
  display_static_frame path signals Rec.2020 in the VPID via set_matrix()
  even without an HDR EOTF, so the capture decodes with the right matrix.

Requires an SDI loopback cable. Skips if the device cannot output the
requested combination.
"""

import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import (
    BlackmagicInput, BlackmagicOutput,
    DisplayMode, Matrix, PixelFormat, create_test_pattern,
)


pytestmark = pytest.mark.hardware


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
CAPTURE_TIMEOUT_MS = 10000

# (label, display_mode, pixel_format, matrix, expected_matrix_name,
#  mean_tol, max_tol)
CASES = [
    (
        "Rec601_NTSC_YUV8",
        DisplayMode.NTSC,
        PixelFormat.YUV8,
        Matrix.Rec601,
        "Rec601",
        0.04,   # SD chroma subsampling is coarser, allow a touch more
        0.25,
    ),
    (
        "Rec2020_1080p25_YUV10",
        DisplayMode.HD1080p25,
        PixelFormat.YUV10,
        Matrix.Rec2020,
        "Rec2020",
        0.02,
        0.15,
    ),
]


@pytest.fixture(scope="module")
def output_device():
    out = BlackmagicOutput()
    assert out.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"
    yield out
    out.cleanup()


@pytest.mark.parametrize(
    "label,display_mode,pixel_format,matrix,expected_matrix,mean_tol,max_tol",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_yuv_matrix_loopback(
    output_device, label, display_mode, pixel_format, matrix,
    expected_matrix, mean_tol, max_tol,
):
    """Float RGB → YUV (matrix) → SDI → YUV → float RGB round-trips, and the
    captured frame is tagged with the matching Matrix enum."""
    if not output_device.is_pixel_format_supported(display_mode, pixel_format):
        pytest.skip(f"{display_mode.name} + {pixel_format.name} not supported by this device")

    settings = output_device._device.get_video_settings(display_mode.value)
    width, height = settings.width, settings.height

    rgb_pattern = create_test_pattern(width, height, pattern="bars") * 0.75

    assert output_device.display_static_frame(
        rgb_pattern, display_mode,
        pixel_format=pixel_format,
        matrix=matrix,
        input_narrow_range=False,
        output_narrow_range=True,
    ), f"display_static_frame failed for {label}"

    time.sleep(0.5)  # SDI signal lock

    with BlackmagicInput() as input_device:
        assert input_device.initialize(
            INPUT_DEVICE_INDEX,
            input_connection=decklink_io.InputConnection.SDI,
        ), f"Failed to initialise SDI input for {label}"

        result = input_device.capture_frame_with_metadata(timeout_ms=CAPTURE_TIMEOUT_MS)
        assert result is not None, f"capture_frame_with_metadata returned None for {label}"

        assert result["matrix"] == expected_matrix, (
            f"{label}: expected matrix {expected_matrix}, "
            f"got {result['matrix']}"
        )

        captured = result["rgb"]
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
