"""Cross-check our RGB <-> Y'CbCr math against the colour-science library.

colour-science is the authoritative reference for ITU-R BT.601/709/2020
conversions. This file asserts that our encoders produce the same integer
code values as colour-science, and our decoders produce the same float RGB
from the same integer code values.

Skipped automatically if colour-science is not installed:
    pip install colour-science

This catches the kind of factor-of-2 / wrong-normalisation drift that an
internal round-trip test misses (encoder and decoder can both be wrong in
compensating ways and round-trip cleanly).
"""

import numpy as np
import pytest

colour = pytest.importorskip("colour")

from blackmagic_io import (  # noqa: E402  (import after pytest.importorskip)
    rgb_float_to_yuv8,
    rgb_float_to_yuv10,
    yuv8_to_rgb_float,
    yuv10_to_rgb_float,
    unpack_2vuy,
    unpack_v210,
    Gamut,
)


# Map our Gamut enum to colour-science's WEIGHTS_YCBCR keys.
GAMUT_TO_WEIGHTS_KEY = {
    Gamut.Rec601:  "ITU-R BT.601",
    Gamut.Rec709:  "ITU-R BT.709",
    Gamut.Rec2020: "ITU-R BT.2020",
}

# Reference RGB triples covering every primary plus three grey points.
REFERENCE_RGB = [
    ("white",    [1.0, 1.0, 1.0]),
    ("black",    [0.0, 0.0, 0.0]),
    ("mid_gray", [0.5, 0.5, 0.5]),
    ("red",      [1.0, 0.0, 0.0]),
    ("green",    [0.0, 1.0, 0.0]),
    ("blue",     [0.0, 0.0, 1.0]),
]

MATRICES = [Gamut.Rec601, Gamut.Rec709, Gamut.Rec2020]
RANGES = [True, False]   # narrow, full


# --------------------------------------------------------------------------
# colour-science wrappers
# --------------------------------------------------------------------------

def _cs_encode(rgb_float, gamut, narrow, bits):
    """RGB -> integer (Y, Cb, Cr) code values via colour-science."""
    K = colour.WEIGHTS_YCBCR[GAMUT_TO_WEIGHTS_KEY[gamut]]
    rgb = np.asarray(rgb_float, dtype=np.float64)
    ycbcr = colour.RGB_to_YCbCr(
        rgb,
        K=K,
        in_bits=bits, in_legal=False, in_int=False,
        out_bits=bits, out_legal=narrow, out_int=True,
    )
    return tuple(int(round(float(v))) for v in ycbcr)


def _cs_decode(ycbcr_ints, gamut, narrow, bits):
    """Integer (Y, Cb, Cr) -> float RGB via colour-science."""
    K = colour.WEIGHTS_YCBCR[GAMUT_TO_WEIGHTS_KEY[gamut]]
    ycbcr = np.asarray(ycbcr_ints, dtype=np.float64)
    rgb = colour.YCbCr_to_RGB(
        ycbcr,
        K=K,
        in_bits=bits, in_legal=narrow, in_int=True,
        out_bits=bits, out_legal=False, out_int=False,
    )
    return tuple(float(v) for v in rgb)


# --------------------------------------------------------------------------
# YUV8 (2vuy) parity
# --------------------------------------------------------------------------

@pytest.mark.parametrize("narrow", RANGES, ids=lambda n: "narrow" if n else "full")
@pytest.mark.parametrize("gamut", MATRICES, ids=lambda g: g.name)
@pytest.mark.parametrize("name,rgb", REFERENCE_RGB)
def test_yuv8_encode_parity(name, rgb, gamut, narrow):
    """rgb_float_to_yuv8 must match colour.RGB_to_YCbCr at out_bits=8."""
    width, height = 16, 4
    rgb_frame = np.tile(np.asarray(rgb, dtype=np.float32), (height, width, 1))

    buf = rgb_float_to_yuv8(
        rgb_frame, width, height,
        matrix=gamut,
        output_narrow_range=narrow,
    )
    unpacked = unpack_2vuy(buf, width, height)
    cy, cx = height // 2, width // 2
    y_ours = int(unpacked["y"][cy, cx])
    cb_ours = int(unpacked["cb"][cy, cx])
    cr_ours = int(unpacked["cr"][cy, cx])

    y_ref, cb_ref, cr_ref = _cs_encode(rgb, gamut, narrow, bits=8)

    assert y_ours  == y_ref,  f"Y mismatch: ours={y_ours}, colour={y_ref}"
    assert cb_ours == cb_ref, f"Cb mismatch: ours={cb_ours}, colour={cb_ref}"
    assert cr_ours == cr_ref, f"Cr mismatch: ours={cr_ours}, colour={cr_ref}"


@pytest.mark.parametrize("narrow", RANGES, ids=lambda n: "narrow" if n else "full")
@pytest.mark.parametrize("gamut", MATRICES, ids=lambda g: g.name)
@pytest.mark.parametrize("name,rgb", REFERENCE_RGB)
def test_yuv8_decode_parity(name, rgb, gamut, narrow):
    """yuv8_to_rgb_float must match colour.YCbCr_to_RGB on the same codes."""
    y, cb, cr = _cs_encode(rgb, gamut, narrow, bits=8)
    y  = max(0, min(255, y))
    cb = max(0, min(255, cb))
    cr = max(0, min(255, cr))

    width, height = 4, 2
    pair = bytes([cb, y, cr, y])
    row = pair * (width // 2)
    buf = np.frombuffer(row * height, dtype=np.uint8)

    rgb_ours_arr = yuv8_to_rgb_float(
        buf, width, height,
        matrix=gamut,
        input_narrow_range=narrow,
    )
    cy, cx = height // 2, width // 2
    r_ours, g_ours, b_ours = (float(x) for x in rgb_ours_arr[cy, cx])

    r_ref, g_ref, b_ref = _cs_decode((y, cb, cr), gamut, narrow, bits=8)

    tol = 1e-4
    assert abs(r_ours - r_ref) < tol, f"R mismatch: ours={r_ours}, colour={r_ref}"
    assert abs(g_ours - g_ref) < tol, f"G mismatch: ours={g_ours}, colour={g_ref}"
    assert abs(b_ours - b_ref) < tol, f"B mismatch: ours={b_ours}, colour={b_ref}"


# --------------------------------------------------------------------------
# YUV10 (v210) parity
# --------------------------------------------------------------------------

@pytest.mark.parametrize("narrow", RANGES, ids=lambda n: "narrow" if n else "full")
@pytest.mark.parametrize("gamut", MATRICES, ids=lambda g: g.name)
@pytest.mark.parametrize("name,rgb", REFERENCE_RGB)
def test_yuv10_encode_parity(name, rgb, gamut, narrow):
    """rgb_float_to_yuv10 must match colour.RGB_to_YCbCr at out_bits=10."""
    # Width 48 = v210 alignment boundary so encoder and unpack defaults agree.
    width, height = 48, 4
    rgb_frame = np.tile(np.asarray(rgb, dtype=np.float32), (height, width, 1))

    buf = rgb_float_to_yuv10(
        rgb_frame, width, height,
        matrix=gamut,
        output_narrow_range=narrow,
    )
    unpacked = unpack_v210(buf, width, height)
    cy, cx = height // 2, width // 2
    y_ours = int(unpacked["y"][cy, cx])
    cb_ours = int(unpacked["cb"][cy, cx])
    cr_ours = int(unpacked["cr"][cy, cx])

    y_ref, cb_ref, cr_ref = _cs_encode(rgb, gamut, narrow, bits=10)

    assert y_ours  == y_ref,  f"Y mismatch: ours={y_ours}, colour={y_ref}"
    assert cb_ours == cb_ref, f"Cb mismatch: ours={cb_ours}, colour={cb_ref}"
    assert cr_ours == cr_ref, f"Cr mismatch: ours={cr_ours}, colour={cr_ref}"


@pytest.mark.parametrize("narrow", RANGES, ids=lambda n: "narrow" if n else "full")
@pytest.mark.parametrize("gamut", MATRICES, ids=lambda g: g.name)
@pytest.mark.parametrize("name,rgb", REFERENCE_RGB)
def test_yuv10_decode_parity(name, rgb, gamut, narrow):
    """yuv10_to_rgb_float must match colour.YCbCr_to_RGB on the same codes."""
    y, cb, cr = _cs_encode(rgb, gamut, narrow, bits=10)
    y  = max(0, min(1023, y))
    cb = max(0, min(1023, cb))
    cr = max(0, min(1023, cr))

    # Build a v210 buffer with 6 pixels of constant (Y, Cb, Cr), then tile
    # it across width=48 so the decoder's default row_bytes formula matches.
    # v210 packs 6 pixels into 4 DWORDs as:
    #   DWORD 0:  U0 (b0..9)  | Y0 (b10..19) | V0 (b20..29)
    #   DWORD 1:  Y1 (b0..9)  | U1 (b10..19) | Y2 (b20..29)
    #   DWORD 2:  V1 (b0..9)  | Y3 (b10..19) | U2 (b20..29)
    #   DWORD 3:  Y4 (b0..9)  | V2 (b10..19) | Y5 (b20..29)
    d0 = cb | (y  << 10) | (cr << 20)
    d1 = y  | (cb << 10) | (y  << 20)
    d2 = cr | (y  << 10) | (cb << 20)
    d3 = y  | (cr << 10) | (y  << 20)
    group = np.array([d0, d1, d2, d3], dtype=np.uint32).tobytes()

    width, height = 48, 2
    row = group * (width // 6)        # 8 groups per row = 48 pixels
    buf = np.frombuffer(row * height, dtype=np.uint8)

    rgb_ours_arr = yuv10_to_rgb_float(
        buf, width, height,
        matrix=gamut,
        input_narrow_range=narrow,
    )
    cy, cx = height // 2, width // 2
    r_ours, g_ours, b_ours = (float(x) for x in rgb_ours_arr[cy, cx])

    r_ref, g_ref, b_ref = _cs_decode((y, cb, cr), gamut, narrow, bits=10)

    tol = 1e-4
    assert abs(r_ours - r_ref) < tol, f"R mismatch: ours={r_ours}, colour={r_ref}"
    assert abs(g_ours - g_ref) < tol, f"G mismatch: ours={g_ours}, colour={g_ref}"
    assert abs(b_ours - b_ref) < tol, f"B mismatch: ours={b_ours}, colour={b_ref}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
