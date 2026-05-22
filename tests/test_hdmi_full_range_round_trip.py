"""HDMI loopback test pinning DeckLink's full-range extent behaviour.

SDI 10-bit reserves codes 0-3 and 1020-1023 for sync words, so the library's
canonical full-range extents (0, 1023) emerge from the SDI wire as (4, 1019)
— the wire physically can't carry the reserved codes. The companion test
file `test_capture_as_uint16.py` works around this by choosing inputs that
produce SDI-permitted wire codes.

HDMI does not have this constraint. HDMI (TMDS / FRL) transports the full
active codespace in-band, with sync information carried in separate periods
rather than reserved values. Empirically pinned here: DeckLink writes the
full 10-bit / 12-bit extents to the wire and HDMI delivers them unchanged
end-to-end. This proves the SDI sync-code clamp is an SDI-link-specific
behaviour rather than a DeckLink encoder-side policy.

Three focused cases:

1. `test_hdmi_rgb10_full_white` — full white over RGB10 via HDMI. Captures
   bit-exact `65535` (= bit-replication of wire 1023). Pin against
   regression toward SDI-equivalent clamping (which would produce 65279).
2. `test_hdmi_rgb12_full_white` — full white over RGB12 via HDMI. Captures
   bit-exact `65535` (= bit-replication of wire 4095).
3. `test_hdmi_yuv10_narrow_output_sanity` — sanity check that HDMI loopback
   round-trips at all: YUV10 with narrow output (well within any reasonable
   code range, so clamping isn't a confound).

All three drive the output via `display_solid_color((1.0, 1.0, 1.0), ...)`
— float input goes through the float-path encoders (`rgb_float_to_rgb10`
etc.) which scale `1.0` directly to the wire maximum for the format
(1023, 4095, or 940 for narrow-Y). This avoids any intermediate 10-bit
code packing question and tests the encoder + HDMI wire + decoder
pipeline as a single unit.

Requires an HDMI loopback cable connecting HDMI OUT to HDMI IN.
"""

import sys
import time

import decklink_io
import pytest

from blackmagic_io import BlackmagicInput, BlackmagicOutput, DisplayMode, PixelFormat


pytestmark = [pytest.mark.hardware, pytest.mark.hdmi]


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = DisplayMode.HD1080p25

# Predicted captures for full-range white if HDMI preserves the full extent,
# vs if BMD mirrors the SDI sync-code clamp on HDMI. The actual observed
# value is what these tests pin.
HDMI_FULL_WHITE_UNCLAMPED = 65535  # bit-rep of wire 1023 (10-bit) or 4095 (12-bit)
HDMI_FULL_WHITE_SDI_CLAMPED_10BIT = round(1019 / 1023 * 65535)  # 65279


def test_hdmi_rgb10_full_white():
    """HDMI RGB10 full white round-trips bit-exact to uint16 65535.

    Sends float `(1.0, 1.0, 1.0)` via RGB10 HDMI output and asserts the
    captured uint16 equals 65535 bit-exact. This pins the empirical
    finding that HDMI preserves the full 10-bit extent (1023 on the wire),
    in contrast with SDI which clamps to 1019 via the sync-code reservation.
    Captured 65535 (= bit-replication of wire 1023) confirms that the SDI
    sync-code clamp is an SDI-link-specific behaviour and is not enforced
    by DeckLink's encoder pipeline.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            (1.0, 1.0, 1.0), DISPLAY_MODE,
            pixel_format=PixelFormat.RGB10,
            output_narrow_range=False,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)  # signal lock

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.HDMI,
            ), "Failed to initialise input on HDMI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=False,
                output_narrow_range=False,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"

            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                for ch in range(3):
                    assert int(pixel[ch]) == HDMI_FULL_WHITE_UNCLAMPED, (
                        f"HDMI RGB10 full white pixel sample {i} channel {ch}: "
                        f"expected {HDMI_FULL_WHITE_UNCLAMPED} (HDMI preserves "
                        f"full 10-bit extent), got {int(pixel[ch])}. A value of "
                        f"{HDMI_FULL_WHITE_SDI_CLAMPED_10BIT} would indicate "
                        f"BMD has started mirroring the SDI sync-code clamp on "
                        f"HDMI — a behaviour change worth investigating."
                    )
    finally:
        output.cleanup()


def test_hdmi_rgb12_full_white():
    """HDMI RGB12 full white round-trips bit-exact to uint16 65535.

    Sends float `(1.0, 1.0, 1.0)` via RGB12 HDMI output. `rgb_float_to_rgb12`
    packs 1.0 → wire 4095 directly. Asserts the captured uint16 equals 65535
    (bit-replication of wire 4095). Confirms that DeckLink preserves the
    full 12-bit extent over HDMI just as it does for 10-bit RGB.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            (1.0, 1.0, 1.0), DISPLAY_MODE,
            pixel_format=PixelFormat.RGB12,
            output_narrow_range=False,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.HDMI,
            ), "Failed to initialise input on HDMI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=False,
                output_narrow_range=False,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"

            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                for ch in range(3):
                    assert int(pixel[ch]) == HDMI_FULL_WHITE_UNCLAMPED, (
                        f"HDMI RGB12 full white pixel sample {i} channel {ch}: "
                        f"expected {HDMI_FULL_WHITE_UNCLAMPED} (HDMI preserves "
                        f"full 12-bit extent), got {int(pixel[ch])}"
                    )
    finally:
        output.cleanup()


def test_hdmi_yuv10_narrow_output_sanity():
    """Sanity check: HDMI YUV10 narrow output round-trips bit-exact.

    Narrow Y'CbCr values (Y in 64-940) sit well within any reasonable wire
    code range, so clamping isn't a confound. Failure here means something
    more fundamental is wrong with the HDMI loopback, not the extent
    behaviour the other two tests are investigating.
    """
    output = BlackmagicOutput()
    assert output.initialize(OUTPUT_DEVICE_INDEX), "Failed to initialise output device"

    try:
        ok = output.display_solid_color(
            (1.0, 1.0, 1.0), DISPLAY_MODE,
            pixel_format=PixelFormat.YUV10,
            output_narrow_range=True,
        )
        assert ok, "display_solid_color returned False"

        time.sleep(0.5)

        with BlackmagicInput() as input_device:
            assert input_device.initialize(
                INPUT_DEVICE_INDEX,
                input_connection=decklink_io.InputConnection.HDMI,
            ), "Failed to initialise input on HDMI"

            captured = input_device.capture_frame_as_uint16(
                input_narrow_range=True,
                output_narrow_range=True,
            )
            assert captured is not None, "capture_frame_as_uint16 returned None"

            samples = captured[100:105, 100:105, :].reshape(-1, 3)
            for i, pixel in enumerate(samples):
                for ch in range(3):
                    assert int(pixel[ch]) == 60160, (
                        f"YUV10 narrow output white sanity check failed: "
                        f"pixel sample {i} channel {ch}: expected 60160, "
                        f"got {int(pixel[ch])}"
                    )
    finally:
        output.cleanup()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
