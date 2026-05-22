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
from blackmagic_io import BlackmagicInput, PixelFormat, create_test_pattern

pytestmark = [pytest.mark.hardware, pytest.mark.hdmi]

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
    """Build a horizontal greyscale ramp covering all 256 8-bit values.

    Column x maps to value floor(x * 256 / width), so each value 0-255 occupies
    a known contiguous block of columns. R, G and B all carry the same value at
    each column (greyscale). Repeated unchanged across every row.

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


def test_bgra_hdmi_loopback_via_wrapper():
    """End-to-end via the BlackmagicInput wrapper rather than the raw API.

    Exercises the BGRA-requested + RGB10-delivered branch of
    `_convert_frame_to_uint8`. The wrapper sees that the user initialised
    with `pixel_format=BGRA` but the SDK delivers `RGB10` (typical for 8-bit
    RGB HDMI sources on tested hardware), and is expected to right-shift
    each channel by 2 to recover the original 8-bit values before applying
    any requested range conversion. Two cases:

    1. `output_narrow_range=False` (default) — uint8 output should match the
       source 75% bars byte-for-byte within ±1.
    2. `output_narrow_range=True` — uint8 output should be the source values
       compressed to narrow range at 8-bit precision (`value * 219/255 + 16`),
       again within ±1.

    Both cases pass `input_narrow_range=False` because the test pattern is
    full-range 8-bit RGB (values 0-191 for 75% bars at full-range encoding).
    The library's default of `input_narrow_range=True` would interpret the
    bytes as narrow-range codes and apply an erroneous narrow→full stretch.
    """
    output_device = decklink_io.DeckLinkOutput()
    assert output_device.initialize(OUTPUT_DEVICE_INDEX), \
        "Failed to initialize output device"

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

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.HDMI,
                pixel_format=PixelFormat.BGRA,
            ), "Failed to initialise BlackmagicInput on HDMI with BGRA"

            # --- Case 1: default full-range uint8 output ---
            captured_full = input_device.capture_frame_as_uint8(
                input_narrow_range=False
            )
            assert captured_full is not None, \
                "capture_frame_as_uint8 (default) returned None"

            diff_full = np.abs(captured_full.astype(int) - expected_rgb.astype(int))
            max_diff_full = int(diff_full.max())
            mean_diff_full = float(diff_full.mean())
            print(f"\nFull-range output: max diff = {max_diff_full}, "
                  f"mean = {mean_diff_full:.3f}")
            assert max_diff_full <= PIXEL_TOLERANCE, (
                f"Full-range capture exceeded ±{PIXEL_TOLERANCE}: "
                f"max diff = {max_diff_full}"
            )

            # --- Case 2: narrow-range output ---
            captured_narrow = input_device.capture_frame_as_uint8(
                input_narrow_range=False,
                output_narrow_range=True,
            )
            assert captured_narrow is not None, \
                "capture_frame_as_uint8 (narrow) returned None"

            # Source is full-range 8-bit; expected output is the same values
            # compressed to narrow range at 8-bit precision.
            expected_narrow = np.clip(
                np.round(expected_rgb.astype(np.float32) * 219.0 / 255.0 + 16.0),
                0, 255,
            ).astype(np.uint8)

            diff_narrow = np.abs(
                captured_narrow.astype(int) - expected_narrow.astype(int)
            )
            max_diff_narrow = int(diff_narrow.max())
            mean_diff_narrow = float(diff_narrow.mean())
            print(f"Narrow-range output: max diff = {max_diff_narrow}, "
                  f"mean = {mean_diff_narrow:.3f}")
            assert max_diff_narrow <= PIXEL_TOLERANCE, (
                f"Narrow-range capture exceeded ±{PIXEL_TOLERANCE}: "
                f"max diff = {max_diff_narrow}"
            )
    finally:
        output_device.stop_output()
        output_device.cleanup()


def test_bgra_hdmi_loopback_uint16_via_wrapper():
    """End-to-end via `capture_frame_as_uint16` from a BGRA-requested input.

    Exercises the new BGRA-source promotion branch of `_convert_frame_to_int`.
    The wrapper sees an 8-bit-precision source and is expected to LSB-pad
    the result via `<< 8` (so 0xff -> 0xff00). Compared against the source
    uint8 array promoted the same way; tolerance is the ±1 uint8-code
    tolerance from the uint8 variant, shifted into uint16 space.
    """
    output_device = decklink_io.DeckLinkOutput()
    assert output_device.initialize(OUTPUT_DEVICE_INDEX), \
        "Failed to initialize output device"

    try:
        settings = output_device.get_video_settings(DISPLAY_MODE)
        settings.format = decklink_io.PixelFormat.BGRA
        assert output_device.setup_output(settings), \
            "Failed to setup BGRA output"

        expected_rgb_uint8, bgra = _build_bgra_frame(settings)
        assert output_device.set_frame_data(bgra), \
            "Failed to set BGRA frame data"
        assert output_device.display_frame(), \
            "Failed to display BGRA frame"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.HDMI,
                pixel_format=PixelFormat.BGRA,
            ), "Failed to initialise BlackmagicInput on HDMI with BGRA"

            captured_uint16 = input_device.capture_frame_as_uint16(
                input_narrow_range=False,
            )
            assert captured_uint16 is not None, \
                "capture_frame_as_uint16 returned None"
            assert captured_uint16.dtype == np.uint16, \
                f"Expected uint16, got {captured_uint16.dtype}"

            expected_uint16 = expected_rgb_uint8.astype(np.uint16) << 8
            diff = np.abs(captured_uint16.astype(int) - expected_uint16.astype(int))
            max_diff = int(diff.max())
            mean_diff = float(diff.mean())
            tolerance_uint16 = PIXEL_TOLERANCE << 8
            print(f"\nuint16 BGRA capture: max diff = {max_diff}, "
                  f"mean = {mean_diff:.3f}, tolerance = {tolerance_uint16}")
            assert max_diff <= tolerance_uint16, (
                f"uint16 BGRA capture exceeded ±{tolerance_uint16} "
                f"({PIXEL_TOLERANCE} 8-bit codes): max diff = {max_diff}"
            )
    finally:
        output_device.stop_output()
        output_device.cleanup()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
