"""SDI loopback test for all pixel formats.

Requires a BNC cable connecting SDI OUT to SDI IN on the same device.
Verifies that each pixel format round-trips through the loopback within
acceptable error tolerances. HDR static metadata round-tripping is covered
separately by ``test_hdr_metadata_loopback.py``.
"""

import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import create_test_pattern


pytestmark = [pytest.mark.hardware, pytest.mark.sdi]


DISPLAY_MODE = decklink_io.DisplayMode.HD1080p25
CAPTURE_TIMEOUT_MS = 10000

# (pixel_format, format_name)
PIXEL_FORMATS = [
    (decklink_io.PixelFormat.YUV8,  "8-bit Y'CbCr (2vuy)"),
    (decklink_io.PixelFormat.YUV10, "10-bit Y'CbCr (v210)"),
    (decklink_io.PixelFormat.RGB10, "10-bit R'G'B' (R10l)"),
    (decklink_io.PixelFormat.RGB12, "12-bit R'G'B' (R12L)"),
]


@pytest.fixture(scope="module")
def decklink_devices():
    output_device = decklink_io.DeckLinkOutput()
    input_device = decklink_io.DeckLinkInput()
    assert output_device.initialize(0), "Failed to initialise output device"
    assert input_device.initialize(0), "Failed to initialise input device"
    yield output_device, input_device
    input_device.cleanup()
    output_device.cleanup()


def _build_frame_data(pixel_format, rgb_pattern, width, height):
    """Convert the float-RGB test pattern into the target wire format."""
    if pixel_format == decklink_io.PixelFormat.BGRA:
        rgb_uint8 = np.round(rgb_pattern * 255).astype(np.uint8)
        return decklink_io.rgb_to_bgra(rgb_uint8, width, height)
    if pixel_format == decklink_io.PixelFormat.YUV8:
        rgb_uint8 = np.round(rgb_pattern * 255).astype(np.uint8)
        return decklink_io.rgb_uint8_to_yuv8(
            rgb_uint8, width, height, matrix=decklink_io.Matrix.Rec709,
        )
    if pixel_format == decklink_io.PixelFormat.YUV10:
        rgb_uint16 = np.round(rgb_pattern * 65535).astype(np.uint16)
        return decklink_io.rgb_uint16_to_yuv10(
            rgb_uint16, width, height,
            matrix=decklink_io.Matrix.Rec709,
            input_narrow_range=False,
            output_narrow_range=True,
        )
    if pixel_format == decklink_io.PixelFormat.RGB10:
        return decklink_io.rgb_float_to_rgb10(
            rgb_pattern, width, height, output_narrow_range=True,
        )
    if pixel_format == decklink_io.PixelFormat.RGB12:
        return decklink_io.rgb_float_to_rgb12(
            rgb_pattern, width, height, output_narrow_range=True,
        )
    raise ValueError(f"Unsupported pixel format: {pixel_format}")


def _captured_to_rgb_float(captured_frame):
    """Convert a captured frame into float RGB for comparison against the source."""
    fmt = captured_frame.format
    if fmt == decklink_io.PixelFormat.YUV8:
        return decklink_io.yuv8_to_rgb_float(
            np.array(captured_frame.data, dtype=np.uint8),
            captured_frame.width, captured_frame.height,
            matrix=captured_frame.matrix,
            input_narrow_range=True,
            row_bytes=captured_frame.row_bytes,
        )
    if fmt == decklink_io.PixelFormat.YUV10:
        return decklink_io.yuv10_to_rgb_float(
            np.array(captured_frame.data, dtype=np.uint8),
            captured_frame.width, captured_frame.height,
            matrix=captured_frame.matrix,
            input_narrow_range=True,
            row_bytes=captured_frame.row_bytes,
        )
    if fmt == decklink_io.PixelFormat.RGB10:
        return decklink_io.rgb10_to_float(
            np.array(captured_frame.data, dtype=np.uint8),
            captured_frame.width, captured_frame.height,
            input_narrow_range=True,
            row_bytes=captured_frame.row_bytes,
        )
    if fmt == decklink_io.PixelFormat.RGB12:
        return decklink_io.rgb12_to_float(
            np.array(captured_frame.data, dtype=np.uint8),
            captured_frame.width, captured_frame.height,
            input_narrow_range=True,
            row_bytes=captured_frame.row_bytes,
        )
    if fmt == decklink_io.PixelFormat.BGRA:
        bgra = np.frombuffer(captured_frame.data, dtype=np.uint8).reshape(
            (captured_frame.height, captured_frame.width, 4),
        )
        rgb = np.zeros((captured_frame.height, captured_frame.width, 3), dtype=np.float32)
        rgb[:, :, 0] = bgra[:, :, 2] / 255.0
        rgb[:, :, 1] = bgra[:, :, 1] / 255.0
        rgb[:, :, 2] = bgra[:, :, 0] / 255.0
        return rgb
    raise ValueError(f"Unsupported pixel format for capture conversion: {fmt}")


@pytest.mark.parametrize(
    "pixel_format, format_name",
    PIXEL_FORMATS,
    ids=[p[1] for p in PIXEL_FORMATS],
)
def test_pixel_format_loopback(decklink_devices, pixel_format, format_name):
    """Round-trip a 75% colour-bars pattern through SDI loopback and verify."""
    output_device, input_device = decklink_devices

    settings = output_device.get_video_settings(DISPLAY_MODE)
    settings.format = pixel_format
    width, height = settings.width, settings.height

    assert output_device.setup_output(settings), f"Failed to set up output for {format_name}"

    rgb_pattern = create_test_pattern(width, height, pattern="bars") * 0.75
    frame_data = _build_frame_data(pixel_format, rgb_pattern, width, height)

    try:
        assert output_device.set_frame_data(frame_data), f"Failed to set frame data for {format_name}"
        assert output_device.display_frame(), f"Failed to display frame for {format_name}"

        time.sleep(0.5)  # SDI signal lock

        assert input_device.start_capture(), f"Failed to start capture for {format_name}"
        try:
            captured = decklink_io.CapturedFrame()
            assert input_device.capture_frame(captured, CAPTURE_TIMEOUT_MS), (
                f"Failed to capture frame for {format_name}"
            )

            rgb_captured = _captured_to_rgb_float(captured)
            diff = np.abs(rgb_pattern - rgb_captured)
            mean_error = float(np.mean(diff))
            max_error = float(np.max(diff))

            # Tolerances vary by chroma-subsampling / bit depth. 4:2:2 formats
            # have small unavoidable errors from chroma subsampling; RGB formats
            # round-trip with near-zero error given proper rounding.
            if captured.format == decklink_io.PixelFormat.YUV8:
                accept_mean, accept_max = 0.03, 0.20
            elif captured.format == decklink_io.PixelFormat.YUV10:
                accept_mean, accept_max = 0.02, 0.15
            else:
                accept_mean, accept_max = 0.01, 0.05

            assert mean_error < accept_mean, (
                f"{format_name}: mean error {mean_error:.4f} exceeds {accept_mean}"
            )
            assert max_error < accept_max, (
                f"{format_name}: max error {max_error:.4f} exceeds {accept_max}"
            )
        finally:
            input_device.stop_capture()
    finally:
        output_device.stop_output()
