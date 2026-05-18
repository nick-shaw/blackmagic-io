"""Verify dynamic resolution support by displaying a frame in each requested mode.

Each requested mode is checked against the device's capabilities first.
Modes the device does not support are SKIPPED. Modes the device claims to
support but fail to display are FAILures.
"""

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


@pytest.fixture(scope="module")
def output_device():
    out = BlackmagicOutput()
    assert out.initialize(device_index=0), "Failed to initialise DeckLink device"
    yield out
    out.cleanup()


def _make_colorbars(width, height):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    bar_width = width // 8
    colors = [
        [255, 255, 255], [255, 255, 0], [0, 255, 255], [0, 255, 0],
        [255, 0, 255], [255, 0, 0], [0, 0, 255], [0, 0, 0],
    ]
    for i, color in enumerate(colors):
        x_start = i * bar_width
        x_end = min((i + 1) * bar_width, width)
        frame[:, x_start:x_end] = color
    return frame


@pytest.mark.parametrize("mode", TEST_MODES, ids=lambda m: m.name)
def test_display_mode(output_device, mode):
    """Verify display_static_frame succeeds for each supported mode."""
    if not output_device.is_pixel_format_supported(mode, PixelFormat.BGRA):
        pytest.skip(f"{mode.name} not supported by this device")

    info = output_device.get_display_mode_info(mode)
    frame = _make_colorbars(info["width"], info["height"])
    try:
        assert output_device.display_static_frame(frame, mode), (
            f"display_static_frame returned False for {mode.name} despite reported support"
        )
        time.sleep(0.5)  # let hardware transmit a few frames before tearing down
    finally:
        output_device.stop()
        time.sleep(0.5)  # let hardware fully stop before the next case
