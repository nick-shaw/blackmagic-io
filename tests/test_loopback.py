"""SDI loopback test for all pixel formats.

Requires a BNC cable connecting SDI OUT to SDI IN on the same device.
Verifies that each pixel format round-trips through the loopback within
acceptable error tolerances. The RGB10 case also asserts that HDR static
metadata fields are signalled correctly per frame.
"""

import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import create_test_pattern


pytestmark = pytest.mark.hardware


DISPLAY_MODE = decklink_io.DisplayMode.HD1080p25
CAPTURE_TIMEOUT_MS = 10000

# (pixel_format, format_name, verify_hdr_metadata)
PIXEL_FORMATS = [
    (decklink_io.PixelFormat.YUV8,  "8-bit YUV (2vuy)",                False),
    (decklink_io.PixelFormat.YUV10, "10-bit YUV (v210)",               False),
    (decklink_io.PixelFormat.RGB10, "10-bit RGB (R10l) + HDR metadata", True),
    (decklink_io.PixelFormat.RGB12, "12-bit RGB (R12L)",               False),
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


def _make_hdr_metadata():
    """Build the canonical PQ + Rec.2020 HDR static metadata used for RGB10 verification."""
    md = decklink_io.HdrStaticMetadata()
    md.display_primaries_red_x   = 0.708
    md.display_primaries_red_y   = 0.292
    md.display_primaries_green_x = 0.170
    md.display_primaries_green_y = 0.797
    md.display_primaries_blue_x  = 0.131
    md.display_primaries_blue_y  = 0.046
    md.white_point_x = 0.3127
    md.white_point_y = 0.3290
    md.max_display_mastering_luminance = 1000.0
    md.min_display_mastering_luminance = 0.005
    md.max_content_light_level         = 800.0
    md.max_frame_average_light_level   = 400.0
    return md


def _assert_hdr_metadata(captured_frame):
    """Assert captured HDR static metadata matches what _make_hdr_metadata() set."""
    tol = 0.0001

    assert captured_frame.eotf == decklink_io.Eotf.PQ, (
        f"EOTF mismatch: expected PQ, got {captured_frame.eotf}"
    )
    assert captured_frame.matrix == decklink_io.Matrix.Rec2020, (
        f"Matrix mismatch: expected Rec2020, got {captured_frame.matrix}"
    )

    assert captured_frame.has_display_primaries, "Display primaries missing from captured signal"
    assert abs(captured_frame.display_primaries_red_x - 0.708) <= tol
    assert abs(captured_frame.display_primaries_red_y - 0.292) <= tol

    assert captured_frame.has_white_point, "White point missing from captured signal"
    assert abs(captured_frame.white_point_x - 0.3127) <= tol
    assert abs(captured_frame.white_point_y - 0.3290) <= tol

    assert captured_frame.has_mastering_luminance, "Mastering luminance missing from captured signal"
    assert abs(captured_frame.max_display_mastering_luminance - 1000.0) <= 1.0
    assert abs(captured_frame.min_display_mastering_luminance - 0.005) <= 0.001

    assert captured_frame.has_max_cll, "MaxCLL missing from captured signal"
    assert abs(captured_frame.max_content_light_level - 800.0) <= 1.0

    assert captured_frame.has_max_fall, "MaxFALL missing from captured signal"
    assert abs(captured_frame.max_frame_average_light_level - 400.0) <= 1.0


@pytest.mark.parametrize(
    "pixel_format, format_name, verify_hdr",
    PIXEL_FORMATS,
    ids=[p[1] for p in PIXEL_FORMATS],
)
def test_pixel_format_loopback(decklink_devices, pixel_format, format_name, verify_hdr):
    """Round-trip a 75% colour-bars pattern through SDI loopback and verify."""
    output_device, input_device = decklink_devices

    settings = output_device.get_video_settings(DISPLAY_MODE)
    settings.format = pixel_format
    width, height = settings.width, settings.height

    if verify_hdr:
        output_device.set_matrix(decklink_io.Matrix.Rec2020)
        output_device.set_eotf(decklink_io.Eotf.PQ)
        output_device.set_static_metadata(_make_hdr_metadata())

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

            if verify_hdr:
                _assert_hdr_metadata(captured)

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
