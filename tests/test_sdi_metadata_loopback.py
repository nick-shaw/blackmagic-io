#!/usr/bin/env python3
"""SDI loopback test for HDR static metadata signaling.

Requires a BNC cable connecting an output to an input on the same DeckLink
device (or two devices on the same machine, with the input device passed via
INPUT_DEVICE_INDEX).

Iterates through several EOTF + colorimetry combinations, configures the
output's HDR static metadata, captures a frame on the SDI input, and
verifies the metadata round-trip. Mirror of test_hdmi_metadata_loopback.py
for diagnosing whether failures are specific to the HDMI InfoFrame path or
affect both transports.
"""

import decklink_io
from blackmagic_io import create_test_pattern
import numpy as np
import pytest
import time

pytestmark = pytest.mark.hardware

OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = decklink_io.DisplayMode.HD1080p25
PIXEL_FORMAT = decklink_io.PixelFormat.RGB10

PRIMARIES_REC2020 = dict(
    red_x=0.708, red_y=0.292,
    green_x=0.170, green_y=0.797,
    blue_x=0.131, blue_y=0.046,
)
PRIMARIES_REC709 = dict(
    red_x=0.640, red_y=0.330,
    green_x=0.300, green_y=0.600,
    blue_x=0.150, blue_y=0.060,
)
WHITE_D65 = dict(white_x=0.3127, white_y=0.3290)

PRIMARY_TOLERANCE = 0.001
LUMINANCE_TOLERANCE = 1.0
MIN_LUMINANCE_TOLERANCE = 0.001


def make_static_metadata(primaries, white, max_lum, min_lum, max_cll, max_fall):
    static_metadata = decklink_io.HdrStaticMetadata()
    static_metadata.display_primaries_red_x = primaries["red_x"]
    static_metadata.display_primaries_red_y = primaries["red_y"]
    static_metadata.display_primaries_green_x = primaries["green_x"]
    static_metadata.display_primaries_green_y = primaries["green_y"]
    static_metadata.display_primaries_blue_x = primaries["blue_x"]
    static_metadata.display_primaries_blue_y = primaries["blue_y"]
    static_metadata.white_point_x = white["white_x"]
    static_metadata.white_point_y = white["white_y"]
    static_metadata.max_display_mastering_luminance = max_lum
    static_metadata.min_display_mastering_luminance = min_lum
    static_metadata.max_content_light_level = max_cll
    static_metadata.max_frame_average_light_level = max_fall
    return static_metadata


# (case_name, gamut, eotf, static_metadata_kwargs_or_None, expect_full_mastering)
TEST_CASES = [
    (
        "SDR Rec.709 (no HDR metadata)",
        decklink_io.Gamut.Rec709,
        decklink_io.Eotf.SDR,
        None,
        False,
    ),
    (
        "SDR Rec.2020 (matrix signalling without HDR EOTF)",
        decklink_io.Gamut.Rec2020,
        decklink_io.Eotf.SDR,
        None,
        False,
    ),
    (
        "PQ Rec.2020 + full mastering display",
        decklink_io.Gamut.Rec2020,
        decklink_io.Eotf.PQ,
        dict(
            primaries=PRIMARIES_REC2020,
            white=WHITE_D65,
            max_lum=1000.0,
            min_lum=0.005,
            max_cll=800.0,
            max_fall=400.0,
        ),
        True,
    ),
    (
        "PQ Rec.709 + full mastering display",
        decklink_io.Gamut.Rec709,
        decklink_io.Eotf.PQ,
        dict(
            primaries=PRIMARIES_REC709,
            white=WHITE_D65,
            max_lum=600.0,
            min_lum=0.010,
            max_cll=500.0,
            max_fall=200.0,
        ),
        True,
    ),
    (
        "HLG Rec.2020",
        decklink_io.Gamut.Rec2020,
        decklink_io.Eotf.HLG,
        None,
        False,
    ),
]


def configure_output_metadata(output_device, gamut, eotf, static_metadata_kwargs):
    if eotf == decklink_io.Eotf.SDR and gamut == decklink_io.Gamut.Rec709:
        output_device.clear_hdr_metadata()
        return None

    if static_metadata_kwargs is None:
        output_device.set_hdr_metadata(gamut, eotf)
        return None

    static_metadata = make_static_metadata(**static_metadata_kwargs)
    output_device.set_hdr_static_metadata(gamut, eotf, static_metadata)
    return static_metadata


def push_frame(output_device, settings):
    rgb_pattern = create_test_pattern(settings.width, settings.height, pattern="bars") * 0.75
    frame_data = decklink_io.rgb_float_to_rgb10(
        rgb_pattern, settings.width, settings.height, output_narrow_range=True
    )
    if not output_device.set_frame_data(frame_data):
        return False
    return output_device.display_frame()


def capture_frame(input_device):
    frame = decklink_io.CapturedFrame()
    if not input_device.capture_frame(frame, 10000):
        return None
    if not frame.valid:
        return None
    return frame


def verify_metadata(case_name, gamut, eotf, static_metadata_kwargs, expect_full_mastering, frame):
    failures = []

    if frame.eotf != eotf:
        failures.append(f"EOTF mismatch: expected {eotf}, got {frame.eotf}")

    if frame.colorspace != gamut:
        failures.append(f"Colorspace mismatch: expected {gamut}, got {frame.colorspace}")

    if expect_full_mastering:
        primaries = static_metadata_kwargs["primaries"]
        white = static_metadata_kwargs["white"]

        if not frame.has_display_primaries:
            failures.append("Display primaries missing")
        else:
            primary_pairs = [
                ("red_x", frame.display_primaries_red_x),
                ("red_y", frame.display_primaries_red_y),
                ("green_x", frame.display_primaries_green_x),
                ("green_y", frame.display_primaries_green_y),
                ("blue_x", frame.display_primaries_blue_x),
                ("blue_y", frame.display_primaries_blue_y),
            ]
            for key, received in primary_pairs:
                expected = primaries[key]
                if abs(received - expected) > PRIMARY_TOLERANCE:
                    failures.append(
                        f"Primary {key} mismatch: expected {expected:.4f}, got {received:.4f}"
                    )

        if not frame.has_white_point:
            failures.append("White point missing")
        else:
            if abs(frame.white_point_x - white["white_x"]) > PRIMARY_TOLERANCE \
                    or abs(frame.white_point_y - white["white_y"]) > PRIMARY_TOLERANCE:
                failures.append(
                    f"White point mismatch: expected ({white['white_x']:.4f}, {white['white_y']:.4f}), "
                    f"got ({frame.white_point_x:.4f}, {frame.white_point_y:.4f})"
                )

        if not frame.has_mastering_luminance:
            failures.append("Mastering luminance missing")
        else:
            if abs(frame.max_display_mastering_luminance - static_metadata_kwargs["max_lum"]) > LUMINANCE_TOLERANCE:
                failures.append(
                    f"Max mastering luminance mismatch: expected {static_metadata_kwargs['max_lum']:.1f}, "
                    f"got {frame.max_display_mastering_luminance:.1f}"
                )
            if abs(frame.min_display_mastering_luminance - static_metadata_kwargs["min_lum"]) > MIN_LUMINANCE_TOLERANCE:
                failures.append(
                    f"Min mastering luminance mismatch: expected {static_metadata_kwargs['min_lum']:.4f}, "
                    f"got {frame.min_display_mastering_luminance:.4f}"
                )

        if not frame.has_max_cll:
            failures.append("MaxCLL missing")
        elif abs(frame.max_content_light_level - static_metadata_kwargs["max_cll"]) > LUMINANCE_TOLERANCE:
            failures.append(
                f"MaxCLL mismatch: expected {static_metadata_kwargs['max_cll']:.1f}, "
                f"got {frame.max_content_light_level:.1f}"
            )

        if not frame.has_max_fall:
            failures.append("MaxFALL missing")
        elif abs(frame.max_frame_average_light_level - static_metadata_kwargs["max_fall"]) > LUMINANCE_TOLERANCE:
            failures.append(
                f"MaxFALL mismatch: expected {static_metadata_kwargs['max_fall']:.1f}, "
                f"got {frame.max_frame_average_light_level:.1f}"
            )

    return failures


def run_case(output_device, input_device, settings, case):
    case_name, gamut, eotf, static_metadata_kwargs, expect_full_mastering = case

    print(f"\n{'=' * 70}")
    print(f"Case: {case_name}")
    print(f"{'=' * 70}")

    static_metadata = configure_output_metadata(output_device, gamut, eotf, static_metadata_kwargs)

    settings.format = PIXEL_FORMAT
    if not output_device.setup_output(settings):
        print("  ✗ Failed to setup output")
        return False

    if not push_frame(output_device, settings):
        print("  ✗ Failed to push frame")
        output_device.stop_output()
        return False

    time.sleep(0.5)

    if not input_device.start_capture():
        print("  ✗ Failed to start capture")
        output_device.stop_output()
        return False

    frame = capture_frame(input_device)

    input_device.stop_capture()
    output_device.stop_output()

    if frame is None:
        print("  ✗ Failed to capture frame")
        return False

    print(f"  Captured EOTF:       {frame.eotf}")
    print(f"  Captured colorspace: {frame.colorspace}")
    if frame.has_display_primaries:
        print(
            f"  Display primaries:   R({frame.display_primaries_red_x:.4f}, {frame.display_primaries_red_y:.4f}) "
            f"G({frame.display_primaries_green_x:.4f}, {frame.display_primaries_green_y:.4f}) "
            f"B({frame.display_primaries_blue_x:.4f}, {frame.display_primaries_blue_y:.4f})"
        )
    if frame.has_white_point:
        print(f"  White point:         ({frame.white_point_x:.4f}, {frame.white_point_y:.4f})")
    if frame.has_mastering_luminance:
        print(
            f"  Mastering luminance: max {frame.max_display_mastering_luminance:.1f} cd/m², "
            f"min {frame.min_display_mastering_luminance:.4f} cd/m²"
        )
    if frame.has_max_cll:
        print(f"  MaxCLL:              {frame.max_content_light_level:.1f} cd/m²")
    if frame.has_max_fall:
        print(f"  MaxFALL:             {frame.max_frame_average_light_level:.1f} cd/m²")

    failures = verify_metadata(case_name, gamut, eotf, static_metadata_kwargs, expect_full_mastering, frame)

    if failures:
        print("\n  ✗ FAILED:")
        for failure in failures:
            print(f"    - {failure}")
        return False

    print("\n  ✓ PASSED")
    return True


def main():
    print("Blackmagic SDI HDR Metadata Loopback Test")
    print("=" * 70)
    print("Requires a BNC cable from output to input.")
    print(f"Output device index: {OUTPUT_DEVICE_INDEX}")
    print(f"Input device index:  {INPUT_DEVICE_INDEX}")
    print("=" * 70)

    output_device = decklink_io.DeckLinkOutput()
    input_device = decklink_io.DeckLinkInput()

    if not output_device.initialize(OUTPUT_DEVICE_INDEX):
        print("ERROR: Failed to initialize output device")
        return 1

    if not input_device.initialize(INPUT_DEVICE_INDEX, decklink_io.InputConnection.SDI):
        print("ERROR: Failed to initialize input device on SDI")
        output_device.cleanup()
        return 1

    settings = output_device.get_video_settings(DISPLAY_MODE)
    print(f"\nResolution: {settings.width}x{settings.height} @ {settings.framerate} fps")

    results = []
    for case in TEST_CASES:
        success = run_case(output_device, input_device, settings, case)
        results.append((case[0], success))

    input_device.cleanup()
    output_device.cleanup()

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for case_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {case_name}")

    all_passed = all(success for _, success in results)
    print("=" * 70)
    if all_passed:
        print("All tests PASSED!")
        return 0
    print("Some tests FAILED!")
    return 1


if __name__ == "__main__":
    exit(main())
