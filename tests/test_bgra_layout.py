#!/usr/bin/env python3
"""Buffer-layout tests for BGRA conversion.

Verifies that rgb_to_bgra produces correctly-ordered bmdFormat8BitBGRA
buffers without requiring hardware. Catches byte-order, stride, and alpha
mistakes at the software boundary before frames hit the wire.
"""

import sys

import numpy as np
import pytest

import decklink_io


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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
