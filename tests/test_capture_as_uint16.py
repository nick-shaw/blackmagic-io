"""SDI loopback test for capture_frame_as_uint16 wrapper methods.

Verifies the high-level uint16 capture path end-to-end across both
specific value-preservation cases and a parametrised matrix of all
(pixel_format, input_narrow, output_narrow) combinations:

1. `test_capture_as_uint16_preserves_10bit_codes_narrow` — outputs a
   specific 10-bit R'G'B' value via `display_solid_color` with
   `pixel_format=RGB10` in narrow range, loops back through SDI, captures
   as uint16 with `input_narrow_range=True, output_narrow_range=True`, and
   asserts that the captured uint16 values are *exactly* the original
   10-bit codes LSB-padded (`N << 6`). Pure bit-shift, no rounding —
   bit-for-bit code preservation across the loopback.

2. `test_capture_as_uint16_preserves_10bit_codes_full` — counterpart that
   exercises the both-full branch. Outputs the same triplet as full-range
   10-bit codes and captures with both narrow flags False. Conversion here
   is arithmetic scaling (`N * 65535 / 1023`) rather than a bit shift; ±1
   code drift is accepted to absorb the C++ converter's rounding-mode choice.

3. `test_capture_as_uint16_with_metadata` — asserts the metadata-variant
   wrapper returns a well-formed dict with a uint16 `'rgb'` value and the
   same exact-match pixel values as the both-narrow test.

4. `test_display_solid_color_greyscale_bit_exact` — parametrised matrix
   (pixel_format ∈ {YUV8, YUV10, RGB10, RGB12} × input_narrow ∈ {True,
   False} × output_narrow ∈ {True, False} × colour ∈ {high, low} =
   32 cases). For every combination, displays a solid greyscale via
   `display_solid_color`, captures as uint16 with the matching output
   range, and asserts the captured uint16 equals the canonical 16-bit
   code for the output range. Input values are chosen per range
   combination so the encoder always writes wire codes within the SDI
   permitted range (4-1019), making the SDI wire a clean passthrough — the
   test isolates the library's encode/decode pipeline from SDI clamping
   behaviour. RGB10/RGB12 paths are bit-exact (zero tolerance); YUV8/
   YUV10 paths in full output allow ±1 to absorb matrix-rounding float
   error; narrow output is always bit-exact even for YUV. This battery
   is what catches the class of bug where `display_solid_color`'s
   integer-code packing fails to match the declared range (the bug
   fixed shortly after 0.17.0b5).

Requires a BNC cable connecting SDI OUT to SDI IN. The BGRA-source
promotion branch of `_convert_frame_to_int` (the new `<< 8` path) is
covered by `test_bgra_hdmi_loopback_uint16_via_wrapper` in
`test_hdmi_bgra_loopback.py`, since BGRA isn't a valid SDI format.
"""

import sys
import time

import decklink_io
import numpy as np
import pytest

from blackmagic_io import BlackmagicInput, BlackmagicOutput, DisplayMode, PixelFormat


pytestmark = [pytest.mark.hardware, pytest.mark.sdi]


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = DisplayMode.HD1080p25

# A 10-bit R'G'B' triplet, distinct across channels so a channel-swap
# regression would be immediately visible in any pixel comparison.
# Valid as both a narrow-range code (well within 64-940) and a full-range
# code (within 0-1023).
TEST_COLOR_10BIT = (700, 400, 200)

# Expected uint16 values for the both-narrow path: 10-bit codes LSB-padded
# via `N << 6`. Exact, no rounding.
EXPECTED_UINT16_NARROW = tuple(c << 6 for c in TEST_COLOR_10BIT)  # (44800, 25600, 12800)

# Expected uint16 values for the both-full path: 10-bit codes scaled to
# 16-bit full range via `N * 65535 / 1023`. Computed with round-to-nearest;
# the test allows ±1 code drift to absorb internal rounding-mode choices.
EXPECTED_UINT16_FULL = tuple(round(c * 65535 / 1023) for c in TEST_COLOR_10BIT)
FULL_RANGE_TOLERANCE = 1


def test_capture_as_uint16_preserves_10bit_codes_narrow():
    """RGB10 narrow output → uint16 narrow capture is the 10-bit codes LSB-padded.

    Strongest possible round-trip test of the uint16 path's **both-narrow**
    branch: no subsampling, no matrix, and the conversion is a pure bit
    shift (`N << 6`) with no rounding. Any deviation here is a real
    regression.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            TEST_COLOR_10BIT,
            DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=True,
            output_narrow_range=True,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)  # SDI signal lock

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=True,
                output_narrow_range=True,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"
            assert captured.dtype == np.uint16, f"Expected uint16, got {captured.dtype}"
            assert captured.ndim == 3 and captured.shape[2] == 3, (
                f"Expected HxWx3, got {captured.shape}"
            )

            # Sample several pixels from a region away from the edges. With a
            # solid colour they should all be exactly EXPECTED_UINT16_NARROW.
            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                assert tuple(int(c) for c in pixel) == EXPECTED_UINT16_NARROW, (
                    f"Pixel sample {i}: expected {EXPECTED_UINT16_NARROW}, "
                    f"got {tuple(int(c) for c in pixel)}"
                )
    finally:
        output.cleanup()


def test_capture_as_uint16_preserves_10bit_codes_full():
    """RGB10 full-range output → uint16 full capture is the 10-bit codes scaled to 16-bit.

    Counterpart to the both-narrow test that covers the **both-full** branch
    of the uint16 path. The conversion here is arithmetic scaling
    (`N * 65535 / 1023`) rather than a bit shift, so ±1 code drift is
    accepted to absorb the C++ converter's internal rounding-mode choice.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            TEST_COLOR_10BIT,
            DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=False,
            output_narrow_range=False,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=False,
                output_narrow_range=False,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"
            assert captured.dtype == np.uint16, f"Expected uint16, got {captured.dtype}"

            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                for channel, (got, want) in enumerate(zip(pixel, EXPECTED_UINT16_FULL)):
                    drift = abs(int(got) - int(want))
                    assert drift <= FULL_RANGE_TOLERANCE, (
                        f"Pixel sample {i}, channel {channel}: expected {want} "
                        f"(within ±{FULL_RANGE_TOLERANCE}), got {int(got)} "
                        f"(drift {drift})"
                    )
    finally:
        output.cleanup()


def test_capture_as_uint16_with_metadata():
    """capture_frame_as_uint16_with_metadata returns the expected dict structure with uint16 'rgb'."""
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            TEST_COLOR_10BIT,
            DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            input_narrow_range=True,
            output_narrow_range=True,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            result = input_device.capture_frame_as_uint16_with_metadata(
                input_narrow_range=True,
                output_narrow_range=True,
            )
            assert result is not None, "capture_frame_as_uint16_with_metadata returned None"
            assert isinstance(result, dict)

            for key in ("rgb", "width", "height", "format", "mode", "matrix",
                        "eotf", "input_narrow_range", "output_narrow_range"):
                assert key in result, f"Missing key {key!r}"

            rgb = result["rgb"]
            assert isinstance(rgb, np.ndarray)
            assert rgb.dtype == np.uint16
            assert rgb.shape == (result["height"], result["width"], 3)

            # Same exact-value check as the both-narrow non-metadata variant
            samples = rgb[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                assert tuple(int(c) for c in pixel) == EXPECTED_UINT16_NARROW, (
                    f"Pixel sample {i}: expected {EXPECTED_UINT16_NARROW}, "
                    f"got {tuple(int(c) for c in pixel)}"
                )

            assert result["input_narrow_range"] is True
            assert result["output_narrow_range"] is True
    finally:
        output.cleanup()


# --- Parametrised greyscale bit-exact matrix -------------------------------

# Every pixel format that supports SDI loopback. BGRA is excluded because it
# isn't a valid SDI format and because display_solid_color produces uint16
# (not uint8) for integer-code input, which the BGRA output path rejects.
PIXEL_FORMATS_FOR_PACKING = [
    PixelFormat.YUV8,
    PixelFormat.YUV10,
    PixelFormat.RGB10,
    PixelFormat.RGB12,
]

# All four (input_narrow_range, output_narrow_range) combinations.
RANGE_COMBINATIONS = [
    (True, True),
    (True, False),
    (False, True),
    (False, False),
]

# 10-bit input code values for the bit-exact round-trip matrix below. SDI
# 10-bit reserves codes 0-3 and 1020-1023 for sync words, so the permitted
# wire range is 4-1019. The inputs are chosen so that every test path
# produces wire codes WITHIN that permitted range — no SDI clamping is
# involved. The tests then verify the library's encode/decode pipeline
# in isolation, with the SDI wire acting as a clean passthrough.
#
# Per (input_narrow, output_narrow) combination, the chosen input is the
# largest (or smallest) 10-bit code that produces an SDI-permitted wire code
# at the encoder output:
#
#   (input_narrow=True,  output_narrow=True):  940 / 64   — wire narrow 940 / 64 (canonical narrow extent, well within SDI permitted)
#   (input_narrow=False, output_narrow=True):  1023 / 0   — wire narrow 940 / 64 (full → narrow via cross-range scaling; output narrow so no clamp)
#   (input_narrow=True,  output_narrow=False): 937 / 67   — wire full 1019 / 4   (sub-canonical narrow → SDI-permitted full via cross-range scaling)
#   (input_narrow=False, output_narrow=False): 1019 / 4   — wire full 1019 / 4   (SDI-permitted extent for full input, avoids clamping)
#
# `display_solid_color` always takes 10-bit code values per its docstring.

INPUT_HIGH_10BIT = {
    (True, True):   (940, 940, 940),
    (False, True):  (1023, 1023, 1023),
    (True, False):  (937, 937, 937),
    (False, False): (1019, 1019, 1019),
}

INPUT_LOW_10BIT = {
    (True, True):   (64, 64, 64),
    (False, True):  (0, 0, 0),
    (True, False):  (67, 67, 67),
    (False, False): (4, 4, 4),
}

# Expected captured uint16 for "high" and "low" greyscale, indexed by
# output range. Narrow output produces the canonical narrow 16-bit codes
# (940 << 6 = 60160 and 64 << 6 = 4096). Full output produces values
# scaled from the wire's SDI-permitted extents (1019/1023 × 65535 ≈ 65279,
# 4/1023 × 65535 ≈ 256). All bit-exact apart from a small ±1 matrix
# rounding for the YUV paths in full output.
EXPECTED_HIGH_UINT16 = {True: 60160, False: round(1019 / 1023 * 65535)}  # 60160, 65279
EXPECTED_LOW_UINT16  = {True: 4096,  False: round(4    / 1023 * 65535)}  # 4096,  256

# YUV encoders/decoders pass through float matrix math, which can introduce
# a ±1 16-bit code rounding when the result lands close to a half-step.
# RGB10 and RGB12 paths are pure integer (bit-shift / bit-replication) and
# round-trip bit-exact.
YUV_TOLERANCE = 1
RGB_TOLERANCE = 0


@pytest.mark.parametrize(
    "color_label,is_white",
    [("white", True), ("black", False)],
)
@pytest.mark.parametrize(
    "input_narrow,output_narrow",
    RANGE_COMBINATIONS,
    ids=[
        "narrowIn_narrowOut",
        "narrowIn_fullOut",
        "fullIn_narrowOut",
        "fullIn_fullOut",
    ],
)
@pytest.mark.parametrize(
    "pixel_format",
    PIXEL_FORMATS_FOR_PACKING,
    ids=lambda fmt: fmt.name,
)
def test_display_solid_color_greyscale_bit_exact(
    pixel_format, input_narrow, output_narrow, color_label, is_white
):
    """Solid greyscale through display_solid_color round-trips bit-exact.

    For every (pixel_format, input_narrow, output_narrow) combination,
    displays a 10-bit greyscale via display_solid_color, captures as
    uint16 with the matching output range, and asserts the captured
    value matches the canonical 16-bit code for the output range.

    Input values are chosen so that the encoder always writes wire codes
    within the SDI permitted range (4-1019), so the SDI wire acts as a clean
    passthrough and the test isolates the library's encode/decode
    pipeline rather than the SDI hardware's clamping behaviour. The
    canonical 16-bit extents 0/65535 are not used directly for full
    output because SDI would clamp them; SDI-permitted extents 4/1019 (and
    their narrow-input cross-range equivalents 67/937) are used instead.

    RGB10 and RGB12 paths round-trip via integer bit-shift / bit-
    replication and are bit-exact (zero tolerance). YUV8 and YUV10
    paths pass through float matrix math, which can drift by ±1 at the
    16-bit code level when the result lands near a half-step rounding
    boundary. Narrow output is always bit-exact even for YUV because
    the matrix produces exact codes for greyscale and the narrow
    extents are inside SDI permitted range.

    The 0.17.0b5-shipped packing bug (full-range `<< 6` undershoot)
    would have failed the narrow-output rows by 64 16-bit codes — well
    outside any tolerance — because the encoder produced Y' = 939 (etc.)
    instead of 940 for full-input narrow-output paths. The full-output
    rows now also catch the bug because they use SDI-permitted extents that
    bypass the masking effect of SDI clamping.
    """
    range_key = (input_narrow, output_narrow)
    if is_white:
        color = INPUT_HIGH_10BIT[range_key]
        expected = EXPECTED_HIGH_UINT16[output_narrow]
    else:
        color = INPUT_LOW_10BIT[range_key]
        expected = EXPECTED_LOW_UINT16[output_narrow]

    is_yuv = pixel_format in (PixelFormat.YUV8, PixelFormat.YUV10)
    tolerance = YUV_TOLERANCE if (is_yuv and not output_narrow) else RGB_TOLERANCE

    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            color, DISPLAY_MODE,
            pixel_format=pixel_format,
            input_narrow_range=input_narrow,
            output_narrow_range=output_narrow,
        )
        assert ok, (
            f"display_solid_color returned False for {pixel_format.name} "
            f"{color_label} input_narrow={input_narrow} "
            f"output_narrow={output_narrow}"
        )

        time.sleep(0.5)  # SDI signal lock

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), "Failed to initialise input on SDI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=output_narrow,
                output_narrow_range=output_narrow,
            )
            assert captured is not None, (
                f"capture_frame_as_uint16 returned None for "
                f"{pixel_format.name} {color_label}"
            )

            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                for ch in range(3):
                    drift = abs(int(pixel[ch]) - expected)
                    assert drift <= tolerance, (
                        f"{pixel_format.name} {color_label} "
                        f"input_narrow={input_narrow} "
                        f"output_narrow={output_narrow}: pixel sample {i} "
                        f"channel {ch}: expected {expected} "
                        f"(within ±{tolerance}), got {int(pixel[ch])} "
                        f"(drift {drift})"
                    )
    finally:
        output.cleanup()


# --- Per-source-format input_narrow_range default resolution ----------
# These tests pin the capture-side per-source-format defaults introduced
# in 0.18.0b1, mirroring the output-side `TestPrepareFrameDataRangeDefaults`
# in test_conversion_ranges.py. Pre-0.18.0b1 the capture API forced
# `input_narrow_range=True` uniformly, silently overriding the canonical
# RGB12-is-full convention used by the low-level wrappers. Now `None`
# resolves to the per-source-format default at dispatch time.
#
# The metadata-dict-based check exercises two layers in one assertion:
#   1. The signature default stays as the "unspecified" sentinel (None).
#   2. The resolver maps None to the right per-source-format value.
# If either layer regresses, the dict's `input_narrow_range` field will
# disagree with the documented expected default below.
#
# RGB12 is the regression guard against the asymmetry being silently
# re-introduced.


# (label, pixel_format, expected resolved default)
INPUT_RANGE_DEFAULTS = [
    ("YUV8",  PixelFormat.YUV8,  True),
    ("YUV10", PixelFormat.YUV10, True),
    ("RGB10", PixelFormat.RGB10, True),
    ("RGB12", PixelFormat.RGB12, False),
]


@pytest.mark.parametrize(
    "label,pixel_format,expected_default",
    INPUT_RANGE_DEFAULTS,
    ids=[c[0] for c in INPUT_RANGE_DEFAULTS],
)
def test_input_narrow_range_default_resolution(label, pixel_format, expected_default):
    """`input_narrow_range=None` resolves to the per-source-format default.

    Outputs a mid-grey patch in the requested format with each format's
    canonical default range, captures via SDI loopback with
    `input_narrow_range` omitted, and asserts the metadata dict records
    the documented per-format resolved default.
    """
    canonical_output_narrow = expected_default
    color = (512, 512, 512)

    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), \
        f"Failed to initialise output device for {label}"

    try:
        ok = output.display_solid_color(
            color, DISPLAY_MODE,
            pixel_format=pixel_format,
            input_narrow_range=False,
            output_narrow_range=canonical_output_narrow,
        )
        assert ok, f"display_solid_color returned False for {label}"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.SDI,
            ), f"Failed to initialise SDI input for {label}"

            result = input_device.capture_frame_as_uint16_with_metadata()
            assert result is not None, \
                f"capture_frame_as_uint16_with_metadata returned None for {label}"

            assert result["input_narrow_range"] is expected_default, (
                f"{label}: expected input_narrow_range default {expected_default} "
                f"(per-source-format resolution), got {result['input_narrow_range']}"
            )
    finally:
        output.cleanup()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
