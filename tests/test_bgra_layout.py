#!/usr/bin/env python3
"""Buffer-layout and range-conversion tests for BGRA-related helpers.

Verifies that rgb_to_bgra produces correctly-ordered bmdFormat8BitBGRA
buffers without requiring hardware, and that _adjust_range_uint8 maps
between narrow (16-235) and full (0-255) range correctly.
"""

import sys

import numpy as np
import pytest

import decklink_io
from blackmagic_io import BlackmagicOutput, PixelFormat
from blackmagic_io.blackmagic_io import _adjust_range_uint8


def test_single_pixel_byte_order():
    rgb = np.array([[[10, 20, 30]]], dtype=np.uint8)
    bgra = decklink_io.rgb_to_bgra(rgb, width=1, height=1)
    assert bgra.shape == (1, 1, 4)
    assert bgra[0, 0, 0] == 30   # B
    assert bgra[0, 0, 1] == 20   # G
    assert bgra[0, 0, 2] == 10   # R
    assert bgra[0, 0, 3] == 255  # A


def test_pure_primaries():
    rgb = np.zeros((1, 4, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]
    rgb[0, 1] = [0, 255, 0]
    rgb[0, 2] = [0, 0, 255]
    rgb[0, 3] = [255, 255, 255]
    bgra = decklink_io.rgb_to_bgra(rgb, width=4, height=1)
    assert tuple(bgra[0, 0]) == (0, 0, 255, 255)
    assert tuple(bgra[0, 1]) == (0, 255, 0, 255)
    assert tuple(bgra[0, 2]) == (255, 0, 0, 255)
    assert tuple(bgra[0, 3]) == (255, 255, 255, 255)


def test_alpha_always_opaque():
    rgb = np.random.randint(0, 256, (8, 8, 3), dtype=np.uint8)
    bgra = decklink_io.rgb_to_bgra(rgb, width=8, height=8)
    assert np.all(bgra[:, :, 3] == 255)


def test_row_stride():
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[0, 0] = [1, 2, 3]
    rgb[0, 1] = [4, 5, 6]
    rgb[1, 0] = [7, 8, 9]
    rgb[1, 1] = [10, 11, 12]
    bgra = decklink_io.rgb_to_bgra(rgb, width=2, height=2)
    assert tuple(bgra[0, 0]) == (3, 2, 1, 255)
    assert tuple(bgra[0, 1]) == (6, 5, 4, 255)
    assert tuple(bgra[1, 0]) == (9, 8, 7, 255)
    assert tuple(bgra[1, 1]) == (12, 11, 10, 255)


def test_output_shape():
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    bgra = decklink_io.rgb_to_bgra(rgb, width=1280, height=720)
    assert bgra.shape == (720, 1280, 4)
    assert bgra.dtype == np.uint8


def test_round_trip_preserves_channels():
    rng = np.random.default_rng(42)
    rgb = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
    bgra = decklink_io.rgb_to_bgra(rgb, width=32, height=32)
    rgb_recovered = np.stack([bgra[:, :, 2], bgra[:, :, 1], bgra[:, :, 0]], axis=2)
    assert np.array_equal(rgb, rgb_recovered)


def test_dimension_mismatch_raises():
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError, match="dimensions"):
        decklink_io.rgb_to_bgra(rgb, width=8, height=8)


def test_wrong_channel_count_raises():
    rgba_in = np.zeros((4, 4, 4), dtype=np.uint8)
    with pytest.raises(RuntimeError, match="HxWx3"):
        decklink_io.rgb_to_bgra(rgba_in, width=4, height=4)


# --- _adjust_range_uint8 tests ---

def test_adjust_range_identity_narrow():
    rgb = np.array([[[64, 128, 192]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=True)
    np.testing.assert_array_equal(result, rgb)


def test_adjust_range_identity_full():
    rgb = np.array([[[64, 128, 192]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=False, output_narrow_range=False)
    np.testing.assert_array_equal(result, rgb)


def test_adjust_range_narrow_to_full_endpoints():
    # 16 (nominal black) → 0, 235 (nominal white) → 255
    rgb = np.array([[[16, 235, 16]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=False)
    assert tuple(result[0, 0]) == (0, 255, 0)


def test_adjust_range_full_to_narrow_endpoints():
    # 0 → 16, 255 → 235
    rgb = np.array([[[0, 255, 0]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=False, output_narrow_range=True)
    assert tuple(result[0, 0]) == (16, 235, 16)


def test_adjust_range_narrow_to_full_midrange():
    # 125 ≈ midpoint of [16, 235]; (125 - 16) * 255 / 219 = 126.92 → 127
    rgb = np.array([[[125]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=False)
    assert result[0, 0, 0] == 127


def test_adjust_range_full_to_narrow_midrange():
    # 128 ≈ midpoint of [0, 255]; 128 * 219 / 255 + 16 = 125.94 → 126
    rgb = np.array([[[128]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=False, output_narrow_range=True)
    assert result[0, 0, 0] == 126


def test_adjust_range_narrow_to_full_clips_sub_blacks():
    # Sub-black inputs (< 16) should clip to 0 after the stretch
    rgb = np.array([[[0, 8, 15]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=False)
    assert tuple(result[0, 0]) == (0, 0, 0)


def test_adjust_range_narrow_to_full_clips_super_whites():
    # Super-white inputs (> 235) should clip to 255
    rgb = np.array([[[236, 245, 255]]], dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=False)
    assert tuple(result[0, 0]) == (255, 255, 255)


def test_adjust_range_round_trip_narrow_full_narrow():
    # Narrow values in nominal range round-trip within ±1
    rng = np.random.default_rng(42)
    rgb = rng.integers(16, 236, (16, 16, 3), dtype=np.uint8)
    full = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=False)
    back = _adjust_range_uint8(full, input_narrow_range=False, output_narrow_range=True)
    diff = np.abs(back.astype(int) - rgb.astype(int))
    assert diff.max() <= 1


def test_adjust_range_output_shape_and_dtype():
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    result = _adjust_range_uint8(rgb, input_narrow_range=True, output_narrow_range=False)
    assert result.shape == rgb.shape
    assert result.dtype == np.uint8


# BGRA dtype-rejection tests. BGRA is intentionally uint8-only — passing
# float / uint16 to the BGRA path used to silently truncate (`.astype(np.uint8)`),
# producing near-black or low-byte-only output. The library now rejects with a
# clear ValueError pointing users at YUV10 / RGB10 / RGB12 for higher-precision
# data.

def test_bgra_rejects_float32_dtype():
    output = BlackmagicOutput()
    float_rgb = np.zeros((2, 4, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="BGRA format.*uint8"):
        output._prepare_frame_data(
            float_rgb, PixelFormat.BGRA, matrix=None,
            input_narrow_range=False, output_narrow_range=False,
        )


def test_bgra_rejects_float64_dtype():
    output = BlackmagicOutput()
    float_rgb = np.zeros((2, 4, 3), dtype=np.float64)
    with pytest.raises(ValueError, match="BGRA format.*uint8"):
        output._prepare_frame_data(
            float_rgb, PixelFormat.BGRA, matrix=None,
            input_narrow_range=False, output_narrow_range=False,
        )


def test_bgra_rejects_uint16_dtype():
    output = BlackmagicOutput()
    uint16_rgb = np.zeros((2, 4, 3), dtype=np.uint16)
    with pytest.raises(ValueError, match="BGRA format.*uint8"):
        output._prepare_frame_data(
            uint16_rgb, PixelFormat.BGRA, matrix=None,
            input_narrow_range=False, output_narrow_range=False,
        )


def test_bgra_rejects_bad_shape():
    output = BlackmagicOutput()
    rgb_2d = np.zeros((4, 3), dtype=np.uint8)  # missing channel axis
    with pytest.raises(ValueError, match="HxWx3 .* HxWx4"):
        output._prepare_frame_data(
            rgb_2d, PixelFormat.BGRA, matrix=None,
            input_narrow_range=False, output_narrow_range=False,
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
