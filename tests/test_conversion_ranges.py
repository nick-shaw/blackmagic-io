"""
Test R'G'B' to Y'CbCr conversion with different range parameters.

These tests verify colour conversion accuracy for known reference values
and serve as regression tests during refactoring.
"""

import numpy as np
import pytest

try:
    from blackmagic_io import rgb_uint16_to_yuv10, rgb_float_to_yuv10, Matrix
    CONVERSIONS_AVAILABLE = True
except ImportError:
    CONVERSIONS_AVAILABLE = False


def unpack_v210_pixel(v210_buffer, pixel_index, width):
    """
    Unpack a single pixel's Y, Cb, Cr values from v210 format.

    This unpacking logic matches pixel_reader.cpp exactly.

    v210 packs 6 pixels into 4 DWORDs (16 bytes):
    - DWORD 0: U0[9:0] Y0[9:0] V0[9:0] (bits [9:0] U0, [19:10] Y0, [29:20] V0)
    - DWORD 1: Y1[9:0] U1[9:0] Y2[9:0] (bits [9:0] Y1, [19:10] U1, [29:20] Y2)
    - DWORD 2: V1[9:0] Y3[9:0] U2[9:0] (bits [9:0] V1, [19:10] Y3, [29:20] U2)
    - DWORD 3: Y4[9:0] V2[9:0] Y5[9:0] (bits [9:0] Y4, [19:10] V2, [29:20] Y5)

    Returns: (Y, Cb, Cr) as 10-bit values (0-1023)
    """
    dwords = np.frombuffer(v210_buffer, dtype=np.uint32)

    group_index = (pixel_index // 6) * 4
    pixel_in_group = pixel_index % 6

    d0 = dwords[group_index]
    d1 = dwords[group_index + 1]
    d2 = dwords[group_index + 2]
    d3 = dwords[group_index + 3]

    if pixel_in_group == 0:
        y = (d0 >> 10) & 0x3FF
        cb = d0 & 0x3FF
        cr = (d0 >> 20) & 0x3FF
    elif pixel_in_group == 1:
        y = d1 & 0x3FF
        cb = d0 & 0x3FF
        cr = (d0 >> 20) & 0x3FF
    elif pixel_in_group == 2:
        y = (d1 >> 20) & 0x3FF
        cb = (d1 >> 10) & 0x3FF
        cr = d2 & 0x3FF
    elif pixel_in_group == 3:
        y = (d2 >> 10) & 0x3FF
        cb = (d1 >> 10) & 0x3FF
        cr = d2 & 0x3FF
    elif pixel_in_group == 4:
        y = d3 & 0x3FF
        cb = (d2 >> 20) & 0x3FF
        cr = (d3 >> 10) & 0x3FF
    else:  # pixel_in_group == 5
        y = (d3 >> 20) & 0x3FF
        cb = (d2 >> 20) & 0x3FF
        cr = (d3 >> 10) & 0x3FF

    return (y, cb, cr)


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGBtoYUVConversions:
    """Test R'G'B' to Y'CbCr conversions with known reference values."""

    def test_uint16_black_narrow_range_rec709(self):
        """Test black (0,0,0) converts to Y=64, Cb=512, Cr=512 in narrow range."""
        width, height = 12, 2
        rgb = np.zeros((height, width, 3), dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 64, f"Expected Y=64 for black, got {y}"
        assert cb == 512, f"Expected Cb=512 for black, got {cb}"
        assert cr == 512, f"Expected Cr=512 for black, got {cr}"

    def test_uint16_white_narrow_range_rec709(self):
        """Test white (65535,65535,65535) converts to Y=940, Cb=512, Cr=512 in narrow range."""
        width, height = 12, 2
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 940, f"Expected Y=940 for white, got {y}"
        assert cb == 512, f"Expected Cb=512 for white, got {cb}"
        assert cr == 512, f"Expected Cr=512 for white, got {cr}"

    def test_uint16_mid_gray_narrow_range_rec709(self):
        """Test mid-gray (32768,32768,32768) converts to approximately Y=502, Cb=512, Cr=512."""
        width, height = 12, 2
        rgb = np.full((height, width, 3), 32768, dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert 500 <= y <= 504, f"Expected Y≈502 for mid-gray, got {y}"
        assert 510 <= cb <= 514, f"Expected Cb≈512 for mid-gray, got {cb}"
        assert 510 <= cr <= 514, f"Expected Cr≈512 for mid-gray, got {cr}"

    def test_float_black_narrow_range_rec709(self):
        """Test black (0.0,0.0,0.0) converts to Y=64, Cb=512, Cr=512 in narrow range."""
        width, height = 12, 2
        rgb = np.zeros((height, width, 3), dtype=np.float32)

        yuv_buffer = rgb_float_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 64, f"Expected Y=64 for black, got {y}"
        assert cb == 512, f"Expected Cb=512 for black, got {cb}"
        assert cr == 512, f"Expected Cr=512 for black, got {cr}"

    def test_float_white_narrow_range_rec709(self):
        """Test white (1.0,1.0,1.0) converts to Y=940, Cb=512, Cr=512 in narrow range."""
        width, height = 12, 2
        rgb = np.ones((height, width, 3), dtype=np.float32)

        yuv_buffer = rgb_float_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 940, f"Expected Y=940 for white, got {y}"
        assert cb == 512, f"Expected Cb=512 for white, got {cb}"
        assert cr == 512, f"Expected Cr=512 for white, got {cr}"

    def test_float_mid_gray_narrow_range_rec709(self):
        """Test mid-gray (0.5,0.5,0.5) converts to approximately Y=502, Cb=512, Cr=512."""
        width, height = 12, 2
        rgb = np.full((height, width, 3), 0.5, dtype=np.float32)

        yuv_buffer = rgb_float_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert 500 <= y <= 504, f"Expected Y≈502 for mid-gray, got {y}"
        assert 510 <= cb <= 514, f"Expected Cb≈512 for mid-gray, got {cb}"
        assert 510 <= cr <= 514, f"Expected Cr≈512 for mid-gray, got {cr}"

    def test_uint16_red_narrow_range_rec709(self):
        """Test pure red converts correctly with Rec.709 matrix."""
        width, height = 12, 2
        rgb = np.zeros((height, width, 3), dtype=np.uint16)
        rgb[:, :, 0] = 65535

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        # For pure red (R=1, G=0, B=0) with Rec.709:
        # Y = 0.2126, Cb = -0.1146, Cr = 0.5000
        expected_y = int(0.2126 * 876 + 64)
        expected_cb = int((-0.1146 + 0.5) * 896 + 64)
        expected_cr = int((0.5 + 0.5) * 896 + 64)

        assert abs(y - expected_y) <= 2, f"Expected Y≈{expected_y} for red, got {y}"
        assert abs(cb - expected_cb) <= 2, f"Expected Cb≈{expected_cb} for red, got {cb}"
        assert abs(cr - expected_cr) <= 2, f"Expected Cr≈{expected_cr} for red, got {cr}"


    def test_uint16_white_full_range_yuv_rec709(self):
        """Test white converts to Y=1023, Cb=512, Cr=512 in full range Y'CbCr."""
        width, height = 12, 2
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709,
                                         input_narrow_range=False, output_narrow_range=False)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 1023, f"Expected Y=1023 for white full range, got {y}"
        assert cb == 512, f"Expected Cb=512 for white, got {cb}"
        assert cr == 512, f"Expected Cr=512 for white, got {cr}"

    def test_uint16_black_full_range_yuv_rec709(self):
        """Test black converts to Y=0, Cb=512, Cr=512 in full range Y'CbCr."""
        width, height = 12, 2
        rgb = np.zeros((height, width, 3), dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709,
                                         input_narrow_range=False, output_narrow_range=False)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 0, f"Expected Y=0 for black full range, got {y}"
        assert cb == 512, f"Expected Cb=512 for black, got {cb}"
        assert cr == 512, f"Expected Cr=512 for black, got {cr}"

    def test_uint16_narrow_input_to_narrow_output(self):
        """Test narrow range RGB input (64-940 @10-bit) to narrow range Y'CbCr."""
        width, height = 12, 2
        # White in narrow range: 940 @ 10-bit = 60160 @ 16-bit
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709,
                                         input_narrow_range=True, output_narrow_range=True)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 940, f"Expected Y=940 for narrow white, got {y}"
        assert cb == 512, f"Expected Cb=512 for narrow white, got {cb}"
        assert cr == 512, f"Expected Cr=512 for narrow white, got {cr}"

    def test_uint16_narrow_input_to_full_output(self):
        """Test narrow range RGB input to full range Y'CbCr output."""
        width, height = 12, 2
        # White in narrow range: 940 @ 10-bit = 60160 @ 16-bit
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)

        yuv_buffer = rgb_uint16_to_yuv10(rgb, width, height, Matrix.Rec709,
                                         input_narrow_range=True, output_narrow_range=False)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 1023, f"Expected Y=1023 for narrow input to full output, got {y}"
        assert cb == 512, f"Expected Cb=512, got {cb}"
        assert cr == 512, f"Expected Cr=512, got {cr}"

    def test_float_white_full_range_yuv_rec709(self):
        """Test float white converts to full range Y'CbCr (Y=1023, Cb=512, Cr=512)."""
        width, height = 12, 2
        rgb = np.ones((height, width, 3), dtype=np.float32)

        yuv_buffer = rgb_float_to_yuv10(rgb, width, height, Matrix.Rec709, output_narrow_range=False)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 1023, f"Expected Y=1023 for white full range, got {y}"
        assert cb == 512, f"Expected Cb=512 for white, got {cb}"
        assert cr == 512, f"Expected Cr=512 for white, got {cr}"

    def test_float_black_full_range_yuv_rec709(self):
        """Test float black converts to full range Y'CbCr (Y=0, Cb=512, Cr=512)."""
        width, height = 12, 2
        rgb = np.zeros((height, width, 3), dtype=np.float32)

        yuv_buffer = rgb_float_to_yuv10(rgb, width, height, Matrix.Rec709, output_narrow_range=False)

        y, cb, cr = unpack_v210_pixel(yuv_buffer, 0, width)

        assert y == 0, f"Expected Y=0 for black full range, got {y}"
        assert cb == 512, f"Expected Cb=512 for black, got {cb}"
        assert cr == 512, f"Expected Cr=512 for black, got {cr}"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGBtoRGB10Conversions:
    """Test RGB to RGB10 conversions with different range parameters."""

    def test_uint16_to_rgb10_narrow_to_narrow(self):
        """Test narrow range uint16 to narrow range RGB10 (default behaviour - bit shift)."""
        width, height = 12, 2
        # Narrow range white: 940 @ 10-bit = 60160 @ 16-bit
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb10

        rgb10_buffer = rgb_uint16_to_rgb10(rgb, width, height)

        # Unpack first pixel from r210 format (little-endian RGBX 10-bit)
        dwords = np.frombuffer(rgb10_buffer, dtype=np.uint32)
        r = (dwords[0] >> 22) & 0x3FF
        g = (dwords[0] >> 12) & 0x3FF
        b = (dwords[0] >> 2) & 0x3FF

        assert r == 940, f"Expected R=940 for narrow white, got {r}"
        assert g == 940, f"Expected G=940 for narrow white, got {g}"
        assert b == 940, f"Expected B=940 for narrow white, got {b}"

    def test_uint16_to_rgb10_full_to_full(self):
        """Test full range uint16 to full range RGB10."""
        width, height = 12, 2
        # Full range white: 65535 @ 16-bit
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb10

        rgb10_buffer = rgb_uint16_to_rgb10(rgb, width, height,
                                          input_narrow_range=False, output_narrow_range=False)

        dwords = np.frombuffer(rgb10_buffer, dtype=np.uint32)
        r = (dwords[0] >> 22) & 0x3FF
        g = (dwords[0] >> 12) & 0x3FF
        b = (dwords[0] >> 2) & 0x3FF

        assert r == 1023, f"Expected R=1023 for full white, got {r}"
        assert g == 1023, f"Expected G=1023 for full white, got {g}"
        assert b == 1023, f"Expected B=1023 for full white, got {b}"

    def test_uint16_to_rgb10_full_to_narrow(self):
        """Test full range uint16 to narrow range RGB10."""
        width, height = 12, 2
        # Full range white: 65535 @ 16-bit
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb10

        rgb10_buffer = rgb_uint16_to_rgb10(rgb, width, height,
                                          input_narrow_range=False, output_narrow_range=True)

        dwords = np.frombuffer(rgb10_buffer, dtype=np.uint32)
        r = (dwords[0] >> 22) & 0x3FF
        g = (dwords[0] >> 12) & 0x3FF
        b = (dwords[0] >> 2) & 0x3FF

        assert r == 940, f"Expected R=940 for full→narrow white, got {r}"
        assert g == 940, f"Expected G=940 for full→narrow white, got {g}"
        assert b == 940, f"Expected B=940 for full→narrow white, got {b}"

    def test_uint16_to_rgb10_narrow_to_full(self):
        """Test narrow range uint16 to full range RGB10."""
        width, height = 12, 2
        # Narrow range white: 940 @ 10-bit = 60160 @ 16-bit
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb10

        rgb10_buffer = rgb_uint16_to_rgb10(rgb, width, height,
                                          input_narrow_range=True, output_narrow_range=False)

        dwords = np.frombuffer(rgb10_buffer, dtype=np.uint32)
        r = (dwords[0] >> 22) & 0x3FF
        g = (dwords[0] >> 12) & 0x3FF
        b = (dwords[0] >> 2) & 0x3FF

        assert r == 1023, f"Expected R=1023 for narrow→full white, got {r}"
        assert g == 1023, f"Expected G=1023 for narrow→full white, got {g}"
        assert b == 1023, f"Expected B=1023 for narrow→full white, got {b}"


class TestRGBtoRGB12Conversions:
    """Test RGB to 12-bit RGB conversions with range parameters."""

    @staticmethod
    def unpack_r12l_pixel(buffer, pixel_index):
        """Unpack a single pixel from R12L (12-bit RGB LE) format.

        R12L format: 8 pixels in 36 bytes (9 DWORDs).
        This matches the unpacking code in pixel_reader.cpp.
        """
        # Each group of 8 pixels is packed in 9 DWORDs (36 bytes)
        group = pixel_index // 8
        pixel_in_group = pixel_index % 8

        # Start of this group's data
        dwords = np.frombuffer(buffer[group * 36:(group + 1) * 36], dtype=np.uint32)

        # Unpack based on position in group (matching pixel_reader.cpp)
        if pixel_in_group == 0:
            r = dwords[0] & 0xFFF
            g = (dwords[0] >> 12) & 0xFFF
            b = ((dwords[0] >> 24) & 0xFF) | ((dwords[1] & 0xF) << 8)
        elif pixel_in_group == 1:
            r = (dwords[1] >> 4) & 0xFFF
            g = (dwords[1] >> 16) & 0xFFF
            b = ((dwords[1] >> 28) & 0xF) | ((dwords[2] & 0xFF) << 4)
        elif pixel_in_group == 2:
            r = (dwords[2] >> 8) & 0xFFF
            g = (dwords[2] >> 20) & 0xFFF
            b = dwords[3] & 0xFFF
        elif pixel_in_group == 3:
            r = (dwords[3] >> 12) & 0xFFF
            g = ((dwords[3] >> 24) & 0xFF) | ((dwords[4] & 0xF) << 8)
            b = (dwords[4] >> 4) & 0xFFF
        elif pixel_in_group == 4:
            r = (dwords[4] >> 16) & 0xFFF
            g = ((dwords[4] >> 28) & 0xF) | ((dwords[5] & 0xFF) << 4)
            b = (dwords[5] >> 8) & 0xFFF
        elif pixel_in_group == 5:
            r = (dwords[5] >> 20) & 0xFFF
            g = dwords[6] & 0xFFF
            b = (dwords[6] >> 12) & 0xFFF
        elif pixel_in_group == 6:
            r = ((dwords[6] >> 24) & 0xFF) | ((dwords[7] & 0xF) << 8)
            g = (dwords[7] >> 4) & 0xFFF
            b = (dwords[7] >> 16) & 0xFFF
        else:  # pixel_in_group == 7
            r = ((dwords[7] >> 28) & 0xF) | ((dwords[8] & 0xFF) << 4)
            g = (dwords[8] >> 8) & 0xFFF
            b = (dwords[8] >> 20) & 0xFFF

        return r, g, b

    def test_uint16_to_rgb12_default(self):
        """Test default behaviour: full to full."""
        width, height = 16, 2
        # Full range white: 65535 @ 16-bit
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb12

        rgb12_buffer = rgb_uint16_to_rgb12(rgb, width, height)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 4095, f"Expected R=4095 for full white, got {r}"
        assert g == 4095, f"Expected G=4095 for full white, got {g}"
        assert b == 4095, f"Expected B=4095 for full white, got {b}"

    def test_uint16_to_rgb12_full_to_full(self):
        """Test full range uint16 to full range RGB12."""
        width, height = 16, 2
        # Full range white: 65535 @ 16-bit
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb12

        rgb12_buffer = rgb_uint16_to_rgb12(rgb, width, height,
                                          input_narrow_range=False, output_narrow_range=False)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 4095, f"Expected R=4095 for full white, got {r}"
        assert g == 4095, f"Expected G=4095 for full white, got {g}"
        assert b == 4095, f"Expected B=4095 for full white, got {b}"

    def test_uint16_to_rgb12_full_to_narrow(self):
        """Test full range uint16 to narrow range RGB12."""
        width, height = 16, 2
        # Full range white: 65535 @ 16-bit
        rgb = np.full((height, width, 3), 65535, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb12

        rgb12_buffer = rgb_uint16_to_rgb12(rgb, width, height,
                                          input_narrow_range=False, output_narrow_range=True)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 3760, f"Expected R=3760 for full→narrow white, got {r}"
        assert g == 3760, f"Expected G=3760 for full→narrow white, got {g}"
        assert b == 3760, f"Expected B=3760 for full→narrow white, got {b}"

    def test_uint16_to_rgb12_narrow_to_full(self):
        """Test narrow range uint16 to full range RGB12."""
        width, height = 16, 2
        # Narrow range white: 940 @ 10-bit = 60160 @ 16-bit
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb12

        rgb12_buffer = rgb_uint16_to_rgb12(rgb, width, height,
                                          input_narrow_range=True, output_narrow_range=False)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 4095, f"Expected R=4095 for narrow→full white, got {r}"
        assert g == 4095, f"Expected G=4095 for narrow→full white, got {g}"
        assert b == 4095, f"Expected B=4095 for narrow→full white, got {b}"

    def test_uint16_to_rgb12_narrow_to_narrow(self):
        """Test narrow range uint16 to narrow range RGB12 (bitshift path)."""
        width, height = 16, 2
        # Narrow range white: 940 @ 10-bit = 60160 @ 16-bit = 3760 @ 12-bit
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)

        from blackmagic_io import rgb_uint16_to_rgb12

        rgb12_buffer = rgb_uint16_to_rgb12(rgb, width, height,
                                          input_narrow_range=True, output_narrow_range=True)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 3760, f"Expected R=3760 for narrow white, got {r}"
        assert g == 3760, f"Expected G=3760 for narrow white, got {g}"
        assert b == 3760, f"Expected B=3760 for narrow white, got {b}"

    def test_float_to_rgb12_default(self):
        """Test float to RGB12 default (full range output)."""
        width, height = 16, 2
        rgb = np.full((height, width, 3), 1.0, dtype=np.float32)

        from blackmagic_io import rgb_float_to_rgb12

        rgb12_buffer = rgb_float_to_rgb12(rgb, width, height)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 4095, f"Expected R=4095 for float full white, got {r}"
        assert g == 4095, f"Expected G=4095 for float full white, got {g}"
        assert b == 4095, f"Expected B=4095 for float full white, got {b}"

    def test_float_to_rgb12_narrow(self):
        """Test float to RGB12 narrow range output."""
        width, height = 16, 2
        rgb = np.full((height, width, 3), 1.0, dtype=np.float32)

        from blackmagic_io import rgb_float_to_rgb12

        rgb12_buffer = rgb_float_to_rgb12(rgb, width, height, output_narrow_range=True)

        r, g, b = self.unpack_r12l_pixel(rgb12_buffer, 0)

        assert r == 3760, f"Expected R=3760 for float narrow white, got {r}"
        assert g == 3760, f"Expected G=3760 for float narrow white, got {g}"
        assert b == 3760, f"Expected B=3760 for float narrow white, got {b}"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestYUV8RoundTrip:
    """Round-trip RGB through 8-bit Y'CbCr (2vuy) encode + decode.

    Regression test for a chroma-scaling bug in the YUV8 decoder where
    Cb/Cr were normalised to [-1, 1] while the matrix coefficients
    expected [-0.5, 0.5], doubling all chroma in the recovered RGB.

    Uses constant-colour frames so 4:2:2 chroma subsampling is lossless;
    the only round-trip error is 8-bit quantisation.
    """

    # 8-bit narrow-range Y has 219 codes, so a 1-step quantisation error
    # is 1/219 ~= 0.00457 in normalised RGB. Allow 1.5 codes of slack.
    TOL = 1.5 / 219.0

    @staticmethod
    def _const_rgb_uint8(width, height, rgb_triplet):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = rgb_triplet[0]
        frame[:, :, 1] = rgb_triplet[1]
        frame[:, :, 2] = rgb_triplet[2]
        return frame

    def _round_trip(self, rgb_uint8, width, height, matrix=None,
                    output_narrow_range=True):
        from blackmagic_io import (rgb_uint8_to_yuv8, yuv8_to_rgb_float, Matrix)
        if matrix is None:
            matrix = Matrix.Rec709
        yuv = rgb_uint8_to_yuv8(rgb_uint8, width, height, matrix=matrix,
                                input_narrow_range=False,
                                output_narrow_range=output_narrow_range)
        return yuv8_to_rgb_float(yuv, width, height, matrix=matrix,
                                 input_narrow_range=output_narrow_range)

    def test_mid_gray_narrow_rec709(self):
        """Mid-gray round-trips with chroma at midpoint and Y in band."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (128, 128, 128))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        expected = 128 / 255.0
        assert np.allclose(recovered, expected, atol=self.TOL), \
            f"Mid-gray round-trip drift exceeds tolerance: {np.max(np.abs(recovered - expected))}"

    def test_pure_red_narrow_rec709(self):
        """Pure red round-trips to ~ (1, 0, 0). Bug produced ~ (1.79, -0.07, -0.20)."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        # Sample the centre pixel (avoids any potential edge effects).
        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Red R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Red G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Red B={b} (expected 0.0)"

    def test_pure_blue_narrow_rec709(self):
        """Pure blue round-trips to ~ (0, 0, 1)."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (0, 0, 255))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 0.0) < self.TOL, f"Blue R={r} (expected 0.0)"
        assert abs(g - 0.0) < self.TOL, f"Blue G={g} (expected 0.0)"
        assert abs(b - 1.0) < self.TOL, f"Blue B={b} (expected 1.0)"

    def test_pure_green_narrow_rec709(self):
        """Pure green round-trips to ~ (0, 1, 0)."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (0, 255, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 0.0) < self.TOL, f"Green R={r} (expected 0.0)"
        assert abs(g - 1.0) < self.TOL, f"Green G={g} (expected 1.0)"
        assert abs(b - 0.0) < self.TOL, f"Green B={b} (expected 0.0)"

    def test_pure_red_full_range_rec709(self):
        """Pure red round-trips correctly with full-range Y'CbCr too."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709,
                                     output_narrow_range=False)

        # Full range has 255 Y codes (vs 219), so tighter tolerance is fine,
        # but reuse the narrow tolerance to keep this readable.
        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Red (full) R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Red (full) G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Red (full) B={b} (expected 0.0)"

    def test_pure_red_narrow_rec601(self):
        """Bug applied to all matrices — verify Rec.601 round-trips too."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec601)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Rec.601 red R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Rec.601 red G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Rec.601 red B={b} (expected 0.0)"

    def test_pure_red_narrow_rec2020(self):
        """Rec.2020 has different Kr/Kb but same encode/decode structure."""
        from blackmagic_io import Matrix
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec2020)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Rec.2020 red R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Rec.2020 red G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Rec.2020 red B={b} (expected 0.0)"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestYUV10RoundTrip:
    """Round-trip RGB through 10-bit Y'CbCr (v210) encode + decode.

    Mirrors TestYUV8RoundTrip at 10-bit precision. Provides direct
    non-hardware coverage of the YUV10 decoder, which previously was
    only exercised by the hardware loopback test.

    Uses constant-colour frames so 4:2:2 chroma subsampling is lossless;
    the only round-trip error is 10-bit quantisation.
    """

    # 10-bit narrow-range Y has 876 codes; a 1-step quantisation error
    # is 1/876 ~= 0.00114 in normalised RGB. Allow 1.5 codes of slack.
    TOL = 1.5 / 876.0

    # v210 packs 6 pixels per 16 bytes. The encoder writes the minimum
    # ((width+5)/6)*16 bytes/row, but the decoder defaults to BMD's hardware
    # stride ((width+47)/48)*128. These agree only when width is a multiple
    # of 48. Real BMD captures (1280, 1920, ...) all satisfy that; pick 48
    # here so the round-trip works without an explicit row_bytes= argument.

    @staticmethod
    def _const_rgb_uint16(width, height, rgb_triplet_u16):
        frame = np.zeros((height, width, 3), dtype=np.uint16)
        frame[:, :, 0] = rgb_triplet_u16[0]
        frame[:, :, 1] = rgb_triplet_u16[1]
        frame[:, :, 2] = rgb_triplet_u16[2]
        return frame

    def _round_trip(self, rgb_uint16, width, height, matrix=None,
                    output_narrow_range=True):
        from blackmagic_io import (rgb_uint16_to_yuv10, yuv10_to_rgb_float, Matrix)
        if matrix is None:
            matrix = Matrix.Rec709
        yuv = rgb_uint16_to_yuv10(rgb_uint16, width, height, matrix=matrix,
                                  input_narrow_range=False,
                                  output_narrow_range=output_narrow_range)
        return yuv10_to_rgb_float(yuv, width, height, matrix=matrix,
                                  input_narrow_range=output_narrow_range)

    def test_mid_gray_narrow_rec709(self):
        """Mid-gray round-trips with chroma at midpoint and Y in band."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (32768, 32768, 32768))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        expected = 32768 / 65535.0
        assert np.allclose(recovered, expected, atol=self.TOL), \
            f"Mid-gray round-trip drift exceeds tolerance: {np.max(np.abs(recovered - expected))}"

    def test_pure_red_narrow_rec709(self):
        """Pure red round-trips to ~ (1, 0, 0)."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Red R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Red G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Red B={b} (expected 0.0)"

    def test_pure_blue_narrow_rec709(self):
        """Pure blue round-trips to ~ (0, 0, 1)."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (0, 0, 65535))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 0.0) < self.TOL, f"Blue R={r} (expected 0.0)"
        assert abs(g - 0.0) < self.TOL, f"Blue G={g} (expected 0.0)"
        assert abs(b - 1.0) < self.TOL, f"Blue B={b} (expected 1.0)"

    def test_pure_green_narrow_rec709(self):
        """Pure green round-trips to ~ (0, 1, 0)."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (0, 65535, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 0.0) < self.TOL, f"Green R={r} (expected 0.0)"
        assert abs(g - 1.0) < self.TOL, f"Green G={g} (expected 1.0)"
        assert abs(b - 0.0) < self.TOL, f"Green B={b} (expected 0.0)"

    def test_pure_red_full_range_rec709(self):
        """Pure red round-trips correctly with full-range Y'CbCr too."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec709,
                                     output_narrow_range=False)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Red (full) R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Red (full) G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Red (full) B={b} (expected 0.0)"

    def test_pure_red_narrow_rec601(self):
        """Rec.601 (different Kr/Kb) round-trips too."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec601)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Rec.601 red R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Rec.601 red G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Rec.601 red B={b} (expected 0.0)"

    def test_pure_red_narrow_rec2020(self):
        """Rec.2020 has different Kr/Kb but same encode/decode structure."""
        from blackmagic_io import Matrix
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 0, 0))
        recovered = self._round_trip(rgb, width, height, matrix=Matrix.Rec2020)

        r = recovered[height // 2, width // 2, 0]
        g = recovered[height // 2, width // 2, 1]
        b = recovered[height // 2, width // 2, 2]
        assert abs(r - 1.0) < self.TOL, f"Rec.2020 red R={r} (expected 1.0)"
        assert abs(g - 0.0) < self.TOL, f"Rec.2020 red G={g} (expected 0.0)"
        assert abs(b - 0.0) < self.TOL, f"Rec.2020 red B={b} (expected 0.0)"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGB10RoundTrip:
    """Round-trip RGB uint16 through 10-bit RGB (R10l) encode + decode.

    RGB10 has no chroma subsampling and no matrix. Narrow→narrow uses
    bit-shift on both sides and is bit-exact. Full→full encodes by bit-shift
    (`>>6`) and decodes by arithmetic scaling (`N * 65535 / 1023`); the
    round-trip is bit-exact at the range extremes (0, 65535). Cross-range
    conversions go through float math.
    """

    @staticmethod
    def _const_rgb_uint16(width, height, rgb_triplet_u16):
        frame = np.zeros((height, width, 3), dtype=np.uint16)
        frame[:, :, 0] = rgb_triplet_u16[0]
        frame[:, :, 1] = rgb_triplet_u16[1]
        frame[:, :, 2] = rgb_triplet_u16[2]
        return frame

    def _round_trip_same_range(self, rgb_uint16, width, height, narrow):
        """Encode and decode in matching ranges."""
        from blackmagic_io import rgb_uint16_to_rgb10, rgb10_to_uint16
        packed = rgb_uint16_to_rgb10(rgb_uint16, width, height,
                                     input_narrow_range=narrow,
                                     output_narrow_range=narrow)
        return rgb10_to_uint16(packed, width, height,
                               input_narrow_range=narrow,
                               output_narrow_range=narrow)

    def _round_trip_cross_range(self, rgb_uint16, width, height):
        """Encode narrow→full, decode full→narrow (exercises float fallback)."""
        from blackmagic_io import rgb_uint16_to_rgb10, rgb10_to_uint16
        packed = rgb_uint16_to_rgb10(rgb_uint16, width, height,
                                     input_narrow_range=True,
                                     output_narrow_range=False)
        return rgb10_to_uint16(packed, width, height,
                               input_narrow_range=False,
                               output_narrow_range=True)

    def test_white_narrow_round_trip(self):
        """Narrow white (60160 = 940<<6) round-trips bit-exact."""
        width, height = 12, 2
        rgb = self._const_rgb_uint16(width, height, (60160, 60160, 60160))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow white must round-trip exactly via bit-shift path"

    def test_black_narrow_round_trip(self):
        """Narrow black (4096 = 64<<6) round-trips bit-exact."""
        width, height = 12, 2
        rgb = self._const_rgb_uint16(width, height, (4096, 4096, 4096))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow black must round-trip exactly via bit-shift path"

    def test_mid_gray_narrow_round_trip(self):
        """Narrow mid-gray (32128 = 502<<6) round-trips bit-exact."""
        width, height = 12, 2
        rgb = self._const_rgb_uint16(width, height, (32128, 32128, 32128))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow mid-gray must round-trip exactly via bit-shift path"

    def test_pure_red_narrow_round_trip(self):
        """Per-channel: pure red round-trips bit-exact (rules out channel swap)."""
        width, height = 12, 2
        rgb = self._const_rgb_uint16(width, height, (60160, 4096, 4096))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow pure red must round-trip exactly via bit-shift path"

    def test_white_full_round_trip(self):
        """Full-range white (65535) round-trips bit-exact."""
        width, height = 12, 2
        rgb = self._const_rgb_uint16(width, height, (65535, 65535, 65535))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=False)
        # Encode: 65535 >> 6 = 1023. Decode: 1023 * 65535 / 1023 = 65535.
        # Range extremes round-trip exactly under bit-shift encode + scale decode.
        assert np.array_equal(rgb, recovered), \
            "Full white must round-trip exactly"

    def test_cross_range_narrow_white(self):
        """Narrow→full→narrow round-trip stays within 1 code (10-bit ≈ 64 in 16-bit)."""
        width, height = 12, 2
        rgb = self._const_rgb_uint16(width, height, (60160, 60160, 60160))
        recovered = self._round_trip_cross_range(rgb, width, height)
        # One 10-bit narrow code is 1<<6 = 64 in 16-bit representation.
        max_diff = int(np.max(np.abs(rgb.astype(int) - recovered.astype(int))))
        assert max_diff <= 64, \
            f"Cross-range round-trip drift exceeds 1 narrow 10-bit code: {max_diff}"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGB12RoundTrip:
    """Round-trip RGB uint16 through 12-bit RGB (R12L) encode + decode.

    Same structure as TestRGB10RoundTrip but at 12-bit precision. Width must
    be a multiple of 8 because R12L packs 8 pixels per 36-byte group.
    """

    @staticmethod
    def _const_rgb_uint16(width, height, rgb_triplet_u16):
        frame = np.zeros((height, width, 3), dtype=np.uint16)
        frame[:, :, 0] = rgb_triplet_u16[0]
        frame[:, :, 1] = rgb_triplet_u16[1]
        frame[:, :, 2] = rgb_triplet_u16[2]
        return frame

    def _round_trip_same_range(self, rgb_uint16, width, height, narrow):
        from blackmagic_io import rgb_uint16_to_rgb12, rgb12_to_uint16
        packed = rgb_uint16_to_rgb12(rgb_uint16, width, height,
                                     input_narrow_range=narrow,
                                     output_narrow_range=narrow)
        return rgb12_to_uint16(packed, width, height,
                               input_narrow_range=narrow,
                               output_narrow_range=narrow)

    def _round_trip_cross_range(self, rgb_uint16, width, height):
        from blackmagic_io import rgb_uint16_to_rgb12, rgb12_to_uint16
        packed = rgb_uint16_to_rgb12(rgb_uint16, width, height,
                                     input_narrow_range=True,
                                     output_narrow_range=False)
        return rgb12_to_uint16(packed, width, height,
                               input_narrow_range=False,
                               output_narrow_range=True)

    def test_white_narrow_round_trip(self):
        """Narrow white (60160 = 3760<<4) round-trips bit-exact."""
        width, height = 16, 2
        rgb = self._const_rgb_uint16(width, height, (60160, 60160, 60160))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow white must round-trip exactly via bit-shift path"

    def test_black_narrow_round_trip(self):
        """Narrow black (4096 = 256<<4) round-trips bit-exact."""
        width, height = 16, 2
        rgb = self._const_rgb_uint16(width, height, (4096, 4096, 4096))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow black must round-trip exactly via bit-shift path"

    def test_mid_gray_narrow_round_trip(self):
        """Narrow mid-gray (32128 = 2008<<4) round-trips bit-exact."""
        width, height = 16, 2
        rgb = self._const_rgb_uint16(width, height, (32128, 32128, 32128))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow mid-gray must round-trip exactly via bit-shift path"

    def test_pure_red_narrow_round_trip(self):
        """Per-channel: pure red round-trips bit-exact (rules out channel swap)."""
        width, height = 16, 2
        rgb = self._const_rgb_uint16(width, height, (60160, 4096, 4096))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=True)
        assert np.array_equal(rgb, recovered), \
            "Narrow pure red must round-trip exactly via bit-shift path"

    def test_white_full_round_trip(self):
        """Full-range white (65535) round-trips bit-exact."""
        width, height = 16, 2
        rgb = self._const_rgb_uint16(width, height, (65535, 65535, 65535))
        recovered = self._round_trip_same_range(rgb, width, height, narrow=False)
        # Encode: 65535 >> 4 = 4095. Decode: 4095 * 65535 / 4095 = 65535.
        # Range extremes round-trip exactly under bit-shift encode + scale decode.
        assert np.array_equal(rgb, recovered), \
            "Full white must round-trip exactly"

    def test_cross_range_narrow_white(self):
        """Narrow→full→narrow round-trip stays within 1 code (12-bit ≈ 16 in 16-bit)."""
        width, height = 16, 2
        rgb = self._const_rgb_uint16(width, height, (60160, 60160, 60160))
        recovered = self._round_trip_cross_range(rgb, width, height)
        # One 12-bit narrow code is 1<<4 = 16 in 16-bit representation.
        max_diff = int(np.max(np.abs(rgb.astype(int) - recovered.astype(int))))
        assert max_diff <= 16, \
            f"Cross-range round-trip drift exceeds 1 narrow 12-bit code: {max_diff}"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGB10FloatRoundTrip:
    """Round-trip float RGB through `rgb_float_to_rgb10` + `rgb10_to_float`.

    Float input is always [0, 1] full range. The encoder maps it to either
    narrow or full 10-bit codes; the decoder reverses. At the test inputs
    (0.0, 0.5, 1.0 per channel) the round-trip is exact through narrow
    because 0.5 maps to 502 = (64+940)/2 and decodes back to 0.5 exactly.
    Allow 1.5 codes of tolerance as a safety margin.
    """

    TOL_NARROW = 1.5 / 876.0
    TOL_FULL   = 1.5 / 1023.0

    @staticmethod
    def _const_rgb_float(width, height, rgb_triplet):
        frame = np.zeros((height, width, 3), dtype=np.float32)
        frame[:, :, 0] = rgb_triplet[0]
        frame[:, :, 1] = rgb_triplet[1]
        frame[:, :, 2] = rgb_triplet[2]
        return frame

    def _round_trip(self, rgb_float, width, height, narrow):
        from blackmagic_io import rgb_float_to_rgb10, rgb10_to_float
        packed = rgb_float_to_rgb10(rgb_float, width, height,
                                    output_narrow_range=narrow)
        return rgb10_to_float(packed, width, height, input_narrow_range=narrow)

    def test_white_narrow(self):
        width, height = 12, 2
        rgb = self._const_rgb_float(width, height, (1.0, 1.0, 1.0))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        assert np.allclose(recovered, 1.0, atol=self.TOL_NARROW), \
            f"White narrow drift: {np.max(np.abs(recovered - 1.0))}"

    def test_black_narrow(self):
        width, height = 12, 2
        rgb = self._const_rgb_float(width, height, (0.0, 0.0, 0.0))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        assert np.allclose(recovered, 0.0, atol=self.TOL_NARROW), \
            f"Black narrow drift: {np.max(np.abs(recovered))}"

    def test_mid_gray_narrow(self):
        width, height = 12, 2
        rgb = self._const_rgb_float(width, height, (0.5, 0.5, 0.5))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        assert np.allclose(recovered, 0.5, atol=self.TOL_NARROW), \
            f"Mid-gray narrow drift: {np.max(np.abs(recovered - 0.5))}"

    def test_pure_red_narrow(self):
        """Per-channel: pure red round-trips to (1, 0, 0). Rules out channel swap."""
        width, height = 12, 2
        rgb = self._const_rgb_float(width, height, (1.0, 0.0, 0.0))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        cy, cx = height // 2, width // 2
        assert abs(recovered[cy, cx, 0] - 1.0) < self.TOL_NARROW
        assert abs(recovered[cy, cx, 1] - 0.0) < self.TOL_NARROW
        assert abs(recovered[cy, cx, 2] - 0.0) < self.TOL_NARROW

    def test_white_full(self):
        width, height = 12, 2
        rgb = self._const_rgb_float(width, height, (1.0, 1.0, 1.0))
        recovered = self._round_trip(rgb, width, height, narrow=False)
        assert np.allclose(recovered, 1.0, atol=self.TOL_FULL)


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGB12FloatRoundTrip:
    """Round-trip float RGB through `rgb_float_to_rgb12` + `rgb12_to_float`.

    Same structure as TestRGB10FloatRoundTrip at 12-bit precision. Width
    must be a multiple of 8 because R12L packs 8 pixels per 36-byte group.
    """

    TOL_NARROW = 1.5 / 3504.0
    TOL_FULL   = 1.5 / 4095.0

    @staticmethod
    def _const_rgb_float(width, height, rgb_triplet):
        frame = np.zeros((height, width, 3), dtype=np.float32)
        frame[:, :, 0] = rgb_triplet[0]
        frame[:, :, 1] = rgb_triplet[1]
        frame[:, :, 2] = rgb_triplet[2]
        return frame

    def _round_trip(self, rgb_float, width, height, narrow):
        from blackmagic_io import rgb_float_to_rgb12, rgb12_to_float
        packed = rgb_float_to_rgb12(rgb_float, width, height,
                                    output_narrow_range=narrow)
        return rgb12_to_float(packed, width, height, input_narrow_range=narrow)

    def test_white_narrow(self):
        width, height = 16, 2
        rgb = self._const_rgb_float(width, height, (1.0, 1.0, 1.0))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        assert np.allclose(recovered, 1.0, atol=self.TOL_NARROW), \
            f"White narrow drift: {np.max(np.abs(recovered - 1.0))}"

    def test_black_narrow(self):
        width, height = 16, 2
        rgb = self._const_rgb_float(width, height, (0.0, 0.0, 0.0))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        assert np.allclose(recovered, 0.0, atol=self.TOL_NARROW), \
            f"Black narrow drift: {np.max(np.abs(recovered))}"

    def test_mid_gray_narrow(self):
        width, height = 16, 2
        rgb = self._const_rgb_float(width, height, (0.5, 0.5, 0.5))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        assert np.allclose(recovered, 0.5, atol=self.TOL_NARROW), \
            f"Mid-gray narrow drift: {np.max(np.abs(recovered - 0.5))}"

    def test_pure_red_narrow(self):
        """Per-channel: pure red round-trips to (1, 0, 0). Rules out channel swap."""
        width, height = 16, 2
        rgb = self._const_rgb_float(width, height, (1.0, 0.0, 0.0))
        recovered = self._round_trip(rgb, width, height, narrow=True)
        cy, cx = height // 2, width // 2
        assert abs(recovered[cy, cx, 0] - 1.0) < self.TOL_NARROW
        assert abs(recovered[cy, cx, 1] - 0.0) < self.TOL_NARROW
        assert abs(recovered[cy, cx, 2] - 0.0) < self.TOL_NARROW

    def test_white_full(self):
        width, height = 16, 2
        rgb = self._const_rgb_float(width, height, (1.0, 1.0, 1.0))
        recovered = self._round_trip(rgb, width, height, narrow=False)
        assert np.allclose(recovered, 1.0, atol=self.TOL_FULL)


# --------------------------------------------------------------------------
# Gap-closing tests for paths previously only covered by hardware loopback.
# (Closes items from issue #2 plus the YUV uint16 decoder gap.)
# --------------------------------------------------------------------------

@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestYUV8Uint16RoundTrip:
    """Exercises `yuv8_to_rgb_uint16` (the uint16-output decoder branch).

    The float decoder `yuv8_to_rgb_float` is covered by `TestYUV8RoundTrip`
    and the colour-science parity tests, but the uint16 decoder has a
    separate output-packing branch (`rf * 56064 + 4096` for narrow 16-bit,
    `rf * 65535` for full) that wasn't exercised in CI.
    """

    # 8-bit Y has 219 narrow codes; one code in narrow 16-bit output is
    # ~256 uint16 units. Allow 2 codes of slack.
    TOL = 512

    @staticmethod
    def _const_rgb_uint8(width, height, rgb_triplet):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = rgb_triplet[0]
        frame[:, :, 1] = rgb_triplet[1]
        frame[:, :, 2] = rgb_triplet[2]
        return frame

    def _round_trip(self, rgb_uint8, width, height, output_narrow_range):
        from blackmagic_io import rgb_uint8_to_yuv8, yuv8_to_rgb_uint16, Matrix
        yuv = rgb_uint8_to_yuv8(rgb_uint8, width, height,
                                matrix=Matrix.Rec709,
                                input_narrow_range=False,
                                output_narrow_range=True)
        return yuv8_to_rgb_uint16(yuv, width, height,
                                  matrix=Matrix.Rec709,
                                  input_narrow_range=True,
                                  output_narrow_range=output_narrow_range)

    def test_white_to_full_uint16(self):
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 255, 255))
        recovered = self._round_trip(rgb, width, height, output_narrow_range=False)
        cy, cx = height // 2, width // 2
        for ch in range(3):
            assert abs(int(recovered[cy, cx, ch]) - 65535) <= self.TOL, \
                f"channel {ch}: {recovered[cy, cx, ch]} (expected ~65535)"

    def test_white_to_narrow_uint16(self):
        """Exercises the `rf * 56064 + 4096` narrow output branch."""
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 255, 255))
        recovered = self._round_trip(rgb, width, height, output_narrow_range=True)
        cy, cx = height // 2, width // 2
        # Narrow 16-bit white = 60160 (= 940 << 6)
        for ch in range(3):
            assert abs(int(recovered[cy, cx, ch]) - 60160) <= self.TOL, \
                f"channel {ch}: {recovered[cy, cx, ch]} (expected ~60160)"

    def test_pure_red_to_full_uint16(self):
        """Per-channel: pure red round-trips to (~65535, ~0, ~0)."""
        width, height = 16, 4
        rgb = self._const_rgb_uint8(width, height, (255, 0, 0))
        recovered = self._round_trip(rgb, width, height, output_narrow_range=False)
        cy, cx = height // 2, width // 2
        assert abs(int(recovered[cy, cx, 0]) - 65535) <= self.TOL
        assert int(recovered[cy, cx, 1]) <= self.TOL
        assert int(recovered[cy, cx, 2]) <= self.TOL


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestYUV10Uint16RoundTrip:
    """Exercises `yuv10_to_rgb_uint16` (the uint16-output decoder branch)."""

    # 10-bit Y has 876 narrow codes; one code in narrow 16-bit output is 64.
    # Allow 2 codes slack.
    TOL = 128

    @staticmethod
    def _const_rgb_uint16(width, height, rgb_triplet_u16):
        frame = np.zeros((height, width, 3), dtype=np.uint16)
        frame[:, :, 0] = rgb_triplet_u16[0]
        frame[:, :, 1] = rgb_triplet_u16[1]
        frame[:, :, 2] = rgb_triplet_u16[2]
        return frame

    def _round_trip(self, rgb_uint16, width, height, output_narrow_range):
        from blackmagic_io import rgb_uint16_to_yuv10, yuv10_to_rgb_uint16, Matrix
        yuv = rgb_uint16_to_yuv10(rgb_uint16, width, height,
                                  matrix=Matrix.Rec709,
                                  input_narrow_range=False,
                                  output_narrow_range=True)
        return yuv10_to_rgb_uint16(yuv, width, height,
                                   matrix=Matrix.Rec709,
                                   input_narrow_range=True,
                                   output_narrow_range=output_narrow_range)

    def test_white_to_full_uint16(self):
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 65535, 65535))
        recovered = self._round_trip(rgb, width, height, output_narrow_range=False)
        cy, cx = height // 2, width // 2
        for ch in range(3):
            assert abs(int(recovered[cy, cx, ch]) - 65535) <= self.TOL

    def test_white_to_narrow_uint16(self):
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 65535, 65535))
        recovered = self._round_trip(rgb, width, height, output_narrow_range=True)
        cy, cx = height // 2, width // 2
        for ch in range(3):
            assert abs(int(recovered[cy, cx, ch]) - 60160) <= self.TOL

    def test_pure_red_to_full_uint16(self):
        width, height = 48, 4
        rgb = self._const_rgb_uint16(width, height, (65535, 0, 0))
        recovered = self._round_trip(rgb, width, height, output_narrow_range=False)
        cy, cx = height // 2, width // 2
        assert abs(int(recovered[cy, cx, 0]) - 65535) <= self.TOL
        assert int(recovered[cy, cx, 1]) <= self.TOL
        assert int(recovered[cy, cx, 2]) <= self.TOL


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGBUnpack:
    """Exercises `unpack_rgb10` and `unpack_rgb12`.

    These extract bit fields from packed RGB buffers but were not directly
    tested in CI (no parity-test analog because colour-science doesn't have
    an RGB10/RGB12 reference).
    """

    def test_unpack_rgb10_narrow_white(self):
        """Encode narrow white, unpack, assert R=G=B=940."""
        from blackmagic_io import rgb_uint16_to_rgb10, unpack_rgb10
        width, height = 12, 2
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)  # narrow 16-bit white
        packed = rgb_uint16_to_rgb10(rgb, width, height,
                                     input_narrow_range=True, output_narrow_range=True)
        unpacked = unpack_rgb10(packed, width, height)
        assert (unpacked['r'] == 940).all()
        assert (unpacked['g'] == 940).all()
        assert (unpacked['b'] == 940).all()

    def test_unpack_rgb10_pure_red(self):
        """Per-channel: pure narrow red unpacks to (940, 64, 64)."""
        from blackmagic_io import rgb_uint16_to_rgb10, unpack_rgb10
        width, height = 12, 2
        rgb = np.zeros((height, width, 3), dtype=np.uint16)
        rgb[..., 0] = 60160  # narrow white in R
        rgb[..., 1] = 4096   # narrow black in G
        rgb[..., 2] = 4096   # narrow black in B
        packed = rgb_uint16_to_rgb10(rgb, width, height,
                                     input_narrow_range=True, output_narrow_range=True)
        unpacked = unpack_rgb10(packed, width, height)
        assert (unpacked['r'] == 940).all()
        assert (unpacked['g'] == 64).all()
        assert (unpacked['b'] == 64).all()

    def test_unpack_rgb12_narrow_white(self):
        """Encode narrow white, unpack, assert R=G=B=3760."""
        from blackmagic_io import rgb_uint16_to_rgb12, unpack_rgb12
        width, height = 16, 2
        rgb = np.full((height, width, 3), 60160, dtype=np.uint16)
        packed = rgb_uint16_to_rgb12(rgb, width, height,
                                     input_narrow_range=True, output_narrow_range=True)
        unpacked = unpack_rgb12(packed, width, height)
        assert (unpacked['r'] == 3760).all()
        assert (unpacked['g'] == 3760).all()
        assert (unpacked['b'] == 3760).all()

    def test_unpack_rgb12_pure_red(self):
        """Per-channel: pure narrow red unpacks to (3760, 256, 256)."""
        from blackmagic_io import rgb_uint16_to_rgb12, unpack_rgb12
        width, height = 16, 2
        rgb = np.zeros((height, width, 3), dtype=np.uint16)
        rgb[..., 0] = 60160
        rgb[..., 1] = 4096
        rgb[..., 2] = 4096
        packed = rgb_uint16_to_rgb12(rgb, width, height,
                                     input_narrow_range=True, output_narrow_range=True)
        unpacked = unpack_rgb12(packed, width, height)
        assert (unpacked['r'] == 3760).all()
        assert (unpacked['g'] == 256).all()
        assert (unpacked['b'] == 256).all()


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRowBytesForwarding:
    """Verifies the wrapper-level `row_bytes=` argument is forwarded to C++.

    The risk being guarded against is silent drop: a wrapper that accepts
    `row_bytes=N` but doesn't pass it through. The check here uses v210
    because it has the most impactful stride mismatch (the encoder writes
    minimum-pack rows and the decoder default expects BMD's hardware
    alignment).
    """

    def test_yuv10_explicit_row_bytes_matches_default(self):
        """At width=48 (v210-aligned) explicit and default row_bytes agree."""
        from blackmagic_io import rgb_float_to_yuv10, yuv10_to_rgb_float
        width, height = 48, 2
        rgb = np.full((height, width, 3), 0.5, dtype=np.float32)
        packed = rgb_float_to_yuv10(rgb, width, height, output_narrow_range=True)
        # Default row_bytes (((48+47)/48)*128 = 128) and explicit 128 must match.
        from_default  = yuv10_to_rgb_float(packed, width, height, input_narrow_range=True)
        from_explicit = yuv10_to_rgb_float(packed, width, height, input_narrow_range=True,
                                           row_bytes=128)
        assert np.array_equal(from_default, from_explicit)

    def test_yuv10_non_aligned_width_requires_row_bytes(self):
        """At width=12 (not v210-aligned) the encoder writes 32 bytes/row.

        The decoder default ((12+47)/48)*128 = 128 mismatches; passing the
        encoder's actual stride must succeed.
        """
        from blackmagic_io import rgb_float_to_yuv10, yuv10_to_rgb_float
        width, height = 12, 2
        rgb = np.full((height, width, 3), 0.5, dtype=np.float32)
        packed = rgb_float_to_yuv10(rgb, width, height, output_narrow_range=True)
        # Without explicit row_bytes, decoder rejects the buffer (too small).
        with pytest.raises(RuntimeError, match="size too small"):
            yuv10_to_rgb_float(packed, width, height, input_narrow_range=True)
        # With the right row_bytes (32 bytes/row for width=12), decode succeeds.
        recovered = yuv10_to_rgb_float(packed, width, height, input_narrow_range=True,
                                       row_bytes=32)
        # Sanity: mid-gray (0.5) round-trips to ~0.5
        assert np.allclose(recovered, 0.5, atol=1.5 / 876.0)


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestRGBtoBGRA:
    """Exercises `rgb_to_bgra` channel-swap helper."""

    def test_channel_swap(self):
        from blackmagic_io import rgb_to_bgra
        width, height = 4, 2
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        rgb[:, :, 0] = 10   # R
        rgb[:, :, 1] = 20   # G
        rgb[:, :, 2] = 30   # B
        bgra = rgb_to_bgra(rgb, width, height)
        assert bgra.shape == (height, width, 4)
        assert (bgra[..., 0] == 30).all(),  "B channel"
        assert (bgra[..., 1] == 20).all(),  "G channel"
        assert (bgra[..., 2] == 10).all(),  "R channel"
        assert (bgra[..., 3] == 255).all(), "A channel"


@pytest.mark.skipif(not CONVERSIONS_AVAILABLE, reason="Conversion functions not available")
class TestPrepareFrameDataRangeDefaults:
    """Per-format `output_narrow_range` defaults when the caller omits the arg.

    From 0.18.0b1 the high-level `display_static_frame` /
    `display_solid_color` signature changed from
    `output_narrow_range: bool = True` to
    `output_narrow_range: Optional[bool] = None`, so each pixel format
    can resolve "unspecified" to its own canonical default. These tests
    pin both layers of that contract:

    1. The signature default itself stays as the "unspecified" sentinel
       — exercised by calling `_prepare_frame_data` without the
       `output_narrow_range` keyword, the way a real caller would.
    2. The per-format resolution: True for YUV8 / YUV10 / RGB10, False
       for RGB12 — matching the low-level wrappers in
       `blackmagic_io/__init__.py` and the per-format defaults listed
       in the README's PixelFormat section.

    Pre-0.18.0b1 callers who omitted `output_narrow_range` got True for
    every format because `bool = True` was the only single-value default
    the signature could express. The RGB12 test below is the regression
    guard against that constraint reappearing — it would catch any
    signature default that resolves to narrow on the RGB12 path,
    including an accidental revert to `bool = True`.
    """

    @staticmethod
    def _make_stubbed_output(width, height):
        from types import SimpleNamespace
        from blackmagic_io import BlackmagicOutput
        output = BlackmagicOutput()
        output._current_settings = SimpleNamespace(width=width, height=height)
        return output

    def test_yuv8_default_matches_explicit_narrow(self):
        from blackmagic_io import PixelFormat
        rgb = np.full((1, 8, 3), 128, dtype=np.uint8)
        output = self._make_stubbed_output(width=8, height=1)
        via_default = output._prepare_frame_data(
            rgb, PixelFormat.YUV8, matrix=Matrix.Rec709,
            input_narrow_range=False,
        )
        via_explicit = output._prepare_frame_data(
            rgb, PixelFormat.YUV8, matrix=Matrix.Rec709,
            input_narrow_range=False, output_narrow_range=True,
        )
        np.testing.assert_array_equal(via_default, via_explicit)

    def test_yuv10_default_matches_explicit_narrow(self):
        from blackmagic_io import PixelFormat
        # 24 = LCM(6 for v210 alignment, 8 for general alignment); a safe width.
        rgb = np.full((1, 24, 3), 32768, dtype=np.uint16)
        output = self._make_stubbed_output(width=24, height=1)
        via_default = output._prepare_frame_data(
            rgb, PixelFormat.YUV10, matrix=Matrix.Rec709,
            input_narrow_range=False,
        )
        via_explicit = output._prepare_frame_data(
            rgb, PixelFormat.YUV10, matrix=Matrix.Rec709,
            input_narrow_range=False, output_narrow_range=True,
        )
        np.testing.assert_array_equal(via_default, via_explicit)

    def test_rgb10_default_matches_explicit_narrow(self):
        from blackmagic_io import PixelFormat
        rgb = np.full((1, 8, 3), 32768, dtype=np.uint16)
        output = self._make_stubbed_output(width=8, height=1)
        via_default = output._prepare_frame_data(
            rgb, PixelFormat.RGB10, matrix=None,
            input_narrow_range=False,
        )
        via_explicit = output._prepare_frame_data(
            rgb, PixelFormat.RGB10, matrix=None,
            input_narrow_range=False, output_narrow_range=True,
        )
        np.testing.assert_array_equal(via_default, via_explicit)

    def test_rgb12_default_matches_explicit_full_not_narrow(self):
        from blackmagic_io import PixelFormat
        rgb = np.full((1, 8, 3), 32768, dtype=np.uint16)
        output = self._make_stubbed_output(width=8, height=1)
        via_default = output._prepare_frame_data(
            rgb, PixelFormat.RGB12, matrix=None,
            input_narrow_range=False,
        )
        via_full = output._prepare_frame_data(
            rgb, PixelFormat.RGB12, matrix=None,
            input_narrow_range=False, output_narrow_range=False,
        )
        np.testing.assert_array_equal(via_default, via_full)

        via_narrow = output._prepare_frame_data(
            rgb, PixelFormat.RGB12, matrix=None,
            input_narrow_range=False, output_narrow_range=True,
        )
        assert not np.array_equal(via_default, via_narrow), (
            "RGB12 with no explicit output_narrow_range must default to "
            "full-range encoding; got a buffer matching the narrow-range "
            "encoding"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
