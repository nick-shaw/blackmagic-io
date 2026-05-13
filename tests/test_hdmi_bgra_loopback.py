#!/usr/bin/env python3
"""HDMI loopback test for 8-bit BGRA output.

Requires an HDMI cable from output to input on the same DeckLink device
(or two devices, with INPUT_DEVICE_INDEX overridden).

Outputs a 75% colour-bars pattern as bmdFormat8BitBGRA and captures it
back via HDMI. BGRA is not a valid SDI format, which is why this lives in
its own HDMI-only test rather than being mixed into the SDI suite in
test_loopback.py. The captured frame may come back as BGRA (byte-for-byte
preserved) or as 10-bit RGB with the original 8-bit values in the high 8
bits (LSBs zero-padded by the DeckLink) depending on HDMI EDID
negotiation. Both paths are accepted; the test verifies the 8-bit code
values round-trip within ±1.

Run in isolation or before any test that puts the SDK into YCbCr mode
within the same process — the DeckLink 4K Mini does not reliably switch
the input detector back to RGB once it has settled on YCbCr.
"""

import sys
import time

import decklink_io
import numpy as np
import pytest
from blackmagic_io import create_test_pattern

pytestmark = pytest.mark.hardware

OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = decklink_io.DisplayMode.HD1080p25
PIXEL_TOLERANCE = 1


def _build_bgra_frame(settings):
    rgb_pattern = create_test_pattern(
        settings.width, settings.height, pattern="bars"
    ) * 0.75
    rgb_uint8 = np.round(rgb_pattern * 255).astype(np.uint8)
    bgra = decklink_io.rgb_to_bgra(rgb_uint8, settings.width, settings.height)
    return rgb_uint8, bgra


def _build_bgra_ramp_frame(settings):
    """Build a horizontal grayscale ramp covering all 256 8-bit values.

    Column x maps to value floor(x * 256 / width), so each value 0-255 occupies
    a known contiguous block of columns. R, G and B all carry the same value at
    each column (grayscale). Repeated unchanged across every row.

    The ramp exposes any wire-level full→narrow→full scaling: a hidden
    256→220→256 round-trip at 8-bit collapses ~36 source values into pairs
    that share a narrow code, then come back as the lower of each pair,
    producing ~14% off-by-one pixels and only ~220 distinct captured values.
    A 75% colour-bars pattern can miss this because its codes happen to land
    on stable points of the conversion.
    """
    width, height = settings.width, settings.height
    ramp = ((np.arange(width, dtype=np.uint32) * 256) // width).astype(np.uint8)
    rgb_uint8 = np.broadcast_to(
        ramp[None, :, None], (height, width, 3)
    ).astype(np.uint8).copy()
    bgra = decklink_io.rgb_to_bgra(rgb_uint8, width, height)
    return rgb_uint8, bgra


def _decode_captured(frame):
    width = frame.width
    height = frame.height
    fmt = frame.format

    if fmt == decklink_io.PixelFormat.BGRA:
        bgra = np.frombuffer(frame.data, dtype=np.uint8).reshape(
            (height, frame.row_bytes // 4, 4)
        )
        bgra = bgra[:, :width, :]
        rgb = np.stack([bgra[:, :, 2], bgra[:, :, 1], bgra[:, :, 0]], axis=2)
        return rgb, "BGRA (byte-for-byte)"

    if fmt == decklink_io.PixelFormat.RGB10:
        raw = np.frombuffer(frame.data, dtype=np.uint32).reshape(
            (height, frame.row_bytes // 4)
        )
        raw = raw[:, :width]
        r10 = (raw >> 22) & 0x3FF
        g10 = (raw >> 12) & 0x3FF
        b10 = (raw >> 2) & 0x3FF
        rgb = np.stack(
            [
                (r10 >> 2).astype(np.uint8),
                (g10 >> 2).astype(np.uint8),
                (b10 >> 2).astype(np.uint8),
            ],
            axis=2,
        )
        return rgb, "RGB10 (top 8 bits, LSBs zero-padded)"

    return None, f"unsupported captured format: {fmt}"


def test_bgra_hdmi_loopback():
    output_device = decklink_io.DeckLinkOutput()
    input_device = decklink_io.DeckLinkInput()

    assert output_device.initialize(OUTPUT_DEVICE_INDEX), \
        "Failed to initialize output device"
    assert input_device.initialize(
        INPUT_DEVICE_INDEX, decklink_io.InputConnection.HDMI
    ), "Failed to initialize input device on HDMI"

    try:
        settings = output_device.get_video_settings(DISPLAY_MODE)
        settings.format = decklink_io.PixelFormat.BGRA
        assert output_device.setup_output(settings), \
            "Failed to setup BGRA output"

        expected_rgb, bgra = _build_bgra_frame(settings)
        assert output_device.set_frame_data(bgra), \
            "Failed to set BGRA frame data"
        assert output_device.display_frame(), \
            "Failed to display BGRA frame"

        time.sleep(0.5)

        assert input_device.start_capture(), "Failed to start capture"

        frame = decklink_io.CapturedFrame()
        assert input_device.capture_frame(frame, 10000), \
            "Failed to capture frame"
        assert frame.valid, "Captured frame is invalid"

        captured_rgb, label = _decode_captured(frame)
        assert captured_rgb is not None, \
            f"Cannot interpret captured frame: {label}"

        print(f"\nCaptured as: {label}")
        print(f"Captured shape: {captured_rgb.shape}")

        diff = np.abs(captured_rgb.astype(int) - expected_rgb.astype(int))
        max_diff = int(diff.max())
        mean_diff = float(diff.mean())

        print(f"Max per-channel difference: {max_diff} (8-bit code)")
        print(f"Mean per-channel difference: {mean_diff:.3f} (8-bit code)")

        assert max_diff <= PIXEL_TOLERANCE, (
            f"BGRA loopback exceeded ±{PIXEL_TOLERANCE} tolerance: "
            f"max diff = {max_diff}, mean = {mean_diff:.3f}, "
            f"format = {label}"
        )
    finally:
        input_device.stop_capture()
        output_device.stop_output()
        input_device.cleanup()
        output_device.cleanup()


def test_bgra_hdmi_loopback_ramp():
    """Full 0-255 ramp round-trip, catching any wire-level full→narrow→full scaling.

    The 75% colour-bars test only samples a handful of code values and may
    happen to land on values that survive a hidden full→narrow→full scaling
    intact. A monotonic ramp covers every 8-bit value 0-255 and exposes the
    systematic quantisation that scaling would introduce. If the wire really
    does carry full range end-to-end, every value round-trips exactly.
    """
    output_device = decklink_io.DeckLinkOutput()
    input_device = decklink_io.DeckLinkInput()

    assert output_device.initialize(OUTPUT_DEVICE_INDEX), \
        "Failed to initialize output device"
    assert input_device.initialize(
        INPUT_DEVICE_INDEX, decklink_io.InputConnection.HDMI
    ), "Failed to initialize input device on HDMI"

    try:
        settings = output_device.get_video_settings(DISPLAY_MODE)
        settings.format = decklink_io.PixelFormat.BGRA
        assert output_device.setup_output(settings), \
            "Failed to setup BGRA output"

        expected_rgb, bgra = _build_bgra_ramp_frame(settings)
        assert output_device.set_frame_data(bgra), \
            "Failed to set BGRA ramp frame data"
        assert output_device.display_frame(), \
            "Failed to display BGRA ramp frame"

        time.sleep(0.5)

        assert input_device.start_capture(), "Failed to start capture"

        frame = decklink_io.CapturedFrame()
        assert input_device.capture_frame(frame, 10000), \
            "Failed to capture frame"
        assert frame.valid, "Captured frame is invalid"

        captured_rgb, label = _decode_captured(frame)
        assert captured_rgb is not None, \
            f"Cannot interpret captured frame: {label}"

        diff = np.abs(captured_rgb.astype(int) - expected_rgb.astype(int))
        max_diff = int(diff.max())
        mean_diff = float(diff.mean())
        mismatched_pixels = int((diff > 0).any(axis=-1).sum())
        total_pixels = expected_rgb.shape[0] * expected_rgb.shape[1]
        mismatch_pct = 100.0 * mismatched_pixels / total_pixels

        unique_in = int(len(np.unique(expected_rgb[:, :, 0])))
        unique_out = int(len(np.unique(captured_rgb[:, :, 0])))

        print(f"\nCaptured as: {label}")
        print(f"Captured shape: {captured_rgb.shape}")
        print(f"Max per-channel difference: {max_diff} (8-bit code)")
        print(f"Mean per-channel difference: {mean_diff:.4f} (8-bit code)")
        print(f"Mismatched pixels: {mismatched_pixels}/{total_pixels} "
              f"({mismatch_pct:.2f}%)")
        print(f"Distinct R values: input={unique_in}, captured={unique_out}")

        assert max_diff <= PIXEL_TOLERANCE, (
            f"Ramp exceeded ±{PIXEL_TOLERANCE}: max diff = {max_diff}, "
            f"format = {label}"
        )
        # Wire-level full→narrow→full at 8-bit produces ~14% mismatched pixels;
        # preserving full range gives 0%. Threshold well below 14%, well above noise.
        assert mismatch_pct < 1.0, (
            f"{mismatch_pct:.2f}% of pixels off by 1 — suggests wire-level "
            f"full→narrow→full scaling (format={label})"
        )
        # 256 → 220 distinct values would be visible here. Threshold catches
        # any non-trivial collapse while allowing for occasional HDMI noise.
        assert unique_out >= 250, (
            f"Only {unique_out}/256 distinct values preserved — suggests "
            f"wire-level full→narrow→full scaling (format={label})"
        )
    finally:
        input_device.stop_capture()
        output_device.stop_output()
        input_device.cleanup()
        output_device.cleanup()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
