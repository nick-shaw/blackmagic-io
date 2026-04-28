#!/usr/bin/env python3
"""Test dynamic resolution support by outputting test images in various resolutions.

Each requested mode is checked against the device's capabilities first. Modes
the device does not support are SKIPPED (not counted as failures). Modes the
device claims to support but fail to display are FAILures.

Exit code: 0 if no failures (skips are fine), non-zero if any real failure.
"""

import sys
import time
import numpy as np
import pytest
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat

pytestmark = pytest.mark.hardware


TEST_MODES = [
    DisplayMode.HD1080p25,
    DisplayMode.HD720p60,
    DisplayMode.Mode4K2160p30,
    DisplayMode.Mode8K4320p25,
    DisplayMode.NTSC,
    DisplayMode.Mode2560x1440p60,
]


def main():
    print("Testing dynamic resolution support with hardware output:\n")

    output = BlackmagicOutput()
    if not output.initialize(device_index=0):
        print("ERROR: Failed to initialize DeckLink device")
        print("Make sure a DeckLink device is connected.")
        return 1

    print("✓ DeckLink device initialized\n")
    print("Testing resolutions:\n")

    ok_count = 0
    skip_count = 0
    fail_count = 0

    for mode in TEST_MODES:
        try:
            info = output.get_display_mode_info(mode)
            width = info["width"]
            height = info["height"]
            framerate = info["framerate"]

            label = f"{mode.name:20s} -> {width:4d}x{height:4d} @ {framerate:6.2f}fps"

            if not output.is_pixel_format_supported(mode, PixelFormat.BGRA):
                print(f"{label} ... — SKIP (mode not supported by this device)")
                skip_count += 1
                continue

            # Create vertical color bars
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            bar_width = width // 8
            colors = [
                [255, 255, 255],  # White
                [255, 255, 0],    # Yellow
                [0, 255, 255],    # Cyan
                [0, 255, 0],      # Green
                [255, 0, 255],    # Magenta
                [255, 0, 0],      # Red
                [0, 0, 255],      # Blue
                [0, 0, 0],        # Black
            ]
            for i, color in enumerate(colors):
                x_start = i * bar_width
                x_end = min((i + 1) * bar_width, width)
                frame[:, x_start:x_end] = color

            if output.display_static_frame(frame, mode):
                time.sleep(1.0)  # Let hardware settle after mode change
                print(f"{label} ... ✓ OK")
                ok_count += 1
                time.sleep(3)  # Display for 3 seconds for visual inspection
                output.stop()
                time.sleep(1.0)  # Give hardware time to fully stop
            else:
                print(f"{label} ... ✗ FAIL (display_static_frame returned False despite reported support)")
                fail_count += 1

        except Exception as e:
            print(f"{mode.name} ... ✗ ERROR: {e}")
            fail_count += 1

    output.cleanup()

    print(f"\n{ok_count} ok, {skip_count} skipped, {fail_count} failed")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
