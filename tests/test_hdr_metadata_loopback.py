"""HDR static metadata loopback test, parametrised over HDMI and SDI.

Iterates EOTF + matrix combinations through both transports, configures
the output's HDR static metadata, captures a frame on the corresponding input,
and verifies the metadata round-trip.

A full hardware pass requires both an HDMI and an SDI loopback cable
connected. Tests for either transport will fail if its cable isn't in place;
the test ID makes the transport visible in pytest's report
(e.g. ``test_hdr_metadata_roundtrip[HDMI-PQ Rec.2020 ...]``).

The HLG case on HDMI specifically exercises the EDID dynamic-range
advertisement fix — without that fix the source strips HDR Static Metadata
for HLG signals.
"""

import time

import decklink_io
import pytest

from blackmagic_io import create_test_pattern


pytestmark = pytest.mark.hardware


OUTPUT_DEVICE_INDEX = 0
INPUT_DEVICE_INDEX = 0
DISPLAY_MODE = decklink_io.DisplayMode.HD1080p25
PIXEL_FORMAT = decklink_io.PixelFormat.RGB10
CAPTURE_TIMEOUT_MS = 10000

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


# (transport_name, input_connection) — per-param marks let users filter via
# `pytest -m "hardware and sdi"` etc. so SDI-only and HDMI-only cards don't
# emit failures for the unavailable transport.
TRANSPORTS = [
    pytest.param(("HDMI", decklink_io.InputConnection.HDMI), marks=pytest.mark.hdmi, id="HDMI"),
    pytest.param(("SDI",  decklink_io.InputConnection.SDI),  marks=pytest.mark.sdi,  id="SDI"),
]


# (case_name, matrix, eotf, static_metadata_kwargs_or_None, expect_full_mastering)
TEST_CASES = [
    (
        "SDR Rec.709 (no HDR metadata)",
        decklink_io.Matrix.Rec709,
        decklink_io.Eotf.SDR,
        None,
        False,
    ),
    (
        "SDR Rec.2020 (matrix signalling without HDR EOTF)",
        decklink_io.Matrix.Rec2020,
        decklink_io.Eotf.SDR,
        None,
        False,
    ),
    (
        "PQ Rec.2020 + full mastering display",
        decklink_io.Matrix.Rec2020,
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
        decklink_io.Matrix.Rec709,
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
        decklink_io.Matrix.Rec2020,
        decklink_io.Eotf.HLG,
        None,
        False,
    ),
]


def _make_static_metadata(primaries, white, max_lum, min_lum, max_cll, max_fall):
    md = decklink_io.HdrStaticMetadata()
    md.display_primaries_red_x = primaries["red_x"]
    md.display_primaries_red_y = primaries["red_y"]
    md.display_primaries_green_x = primaries["green_x"]
    md.display_primaries_green_y = primaries["green_y"]
    md.display_primaries_blue_x = primaries["blue_x"]
    md.display_primaries_blue_y = primaries["blue_y"]
    md.white_point_x = white["white_x"]
    md.white_point_y = white["white_y"]
    md.max_display_mastering_luminance = max_lum
    md.min_display_mastering_luminance = min_lum
    md.max_content_light_level = max_cll
    md.max_frame_average_light_level = max_fall
    return md


def _configure_output_metadata(output_device, matrix, eotf, static_metadata_kwargs):
    output_device.set_matrix(matrix)
    output_device.set_eotf(eotf)
    if static_metadata_kwargs is not None:
        output_device.set_static_metadata(_make_static_metadata(**static_metadata_kwargs))


def _push_frame(output_device, width, height):
    rgb_pattern = create_test_pattern(width, height, pattern="bars") * 0.75
    frame_data = decklink_io.rgb_float_to_rgb10(
        rgb_pattern, width, height, output_narrow_range=True,
    )
    assert output_device.set_frame_data(frame_data), "Failed to set frame data"
    assert output_device.display_frame(), "Failed to display frame"


def _capture_frame(input_device):
    frame = decklink_io.CapturedFrame()
    assert input_device.capture_frame(frame, CAPTURE_TIMEOUT_MS), "Failed to capture frame"
    assert frame.valid, "Captured frame is invalid"
    return frame


def _assert_full_mastering(frame, kwargs):
    primaries = kwargs["primaries"]
    white = kwargs["white"]

    assert frame.has_display_primaries, "Display primaries missing"
    for key, received in (
        ("red_x", frame.display_primaries_red_x),
        ("red_y", frame.display_primaries_red_y),
        ("green_x", frame.display_primaries_green_x),
        ("green_y", frame.display_primaries_green_y),
        ("blue_x", frame.display_primaries_blue_x),
        ("blue_y", frame.display_primaries_blue_y),
    ):
        expected = primaries[key]
        assert abs(received - expected) <= PRIMARY_TOLERANCE, (
            f"Primary {key}: expected {expected:.4f}, got {received:.4f}"
        )

    assert frame.has_white_point, "White point missing"
    assert abs(frame.white_point_x - white["white_x"]) <= PRIMARY_TOLERANCE
    assert abs(frame.white_point_y - white["white_y"]) <= PRIMARY_TOLERANCE

    assert frame.has_mastering_luminance, "Mastering luminance missing"
    assert abs(frame.max_display_mastering_luminance - kwargs["max_lum"]) <= LUMINANCE_TOLERANCE
    assert abs(frame.min_display_mastering_luminance - kwargs["min_lum"]) <= MIN_LUMINANCE_TOLERANCE

    assert frame.has_max_cll, "MaxCLL missing"
    assert abs(frame.max_content_light_level - kwargs["max_cll"]) <= LUMINANCE_TOLERANCE

    assert frame.has_max_fall, "MaxFALL missing"
    assert abs(frame.max_frame_average_light_level - kwargs["max_fall"]) <= LUMINANCE_TOLERANCE


@pytest.fixture(scope="module", params=TRANSPORTS)
def decklink_devices(request):
    transport_name, input_connection = request.param
    output_device = decklink_io.DeckLinkOutput()
    input_device = decklink_io.DeckLinkInput()
    assert output_device.initialize(OUTPUT_DEVICE_INDEX), (
        f"Failed to initialise output device for {transport_name}"
    )
    assert input_device.initialize(INPUT_DEVICE_INDEX, input_connection), (
        f"Failed to initialise input device on {transport_name}"
    )
    yield output_device, input_device, transport_name
    input_device.cleanup()
    output_device.cleanup()


@pytest.mark.parametrize(
    "case_name, matrix, eotf, static_metadata_kwargs, expect_full_mastering",
    TEST_CASES,
    ids=[c[0] for c in TEST_CASES],
)
def test_hdr_metadata_roundtrip(
    decklink_devices, case_name, matrix, eotf, static_metadata_kwargs, expect_full_mastering,
):
    """Round-trip HDR static metadata through one transport (HDMI or SDI) for one EOTF + matrix combination."""
    output_device, input_device, _transport = decklink_devices

    _configure_output_metadata(output_device, matrix, eotf, static_metadata_kwargs)

    settings = output_device.get_video_settings(DISPLAY_MODE)
    settings.format = PIXEL_FORMAT
    assert output_device.setup_output(settings), "Failed to setup output"

    try:
        _push_frame(output_device, settings.width, settings.height)
        time.sleep(0.5)

        assert input_device.start_capture(), "Failed to start capture"
        try:
            frame = _capture_frame(input_device)

            assert frame.eotf == eotf, f"EOTF: expected {eotf}, got {frame.eotf}"
            assert frame.matrix == matrix, (
                f"Matrix: expected {matrix}, got {frame.matrix}"
            )

            if expect_full_mastering:
                _assert_full_mastering(frame, static_metadata_kwargs)
        finally:
            input_device.stop_capture()
    finally:
        output_device.stop_output()


def test_metadata_snapshot_persists_until_display_frame(decklink_devices):
    """Mid-stream metadata changes only reach the wire after ``display_frame()``.

    Verifies the SDK's snapshot behaviour for HDR / matrix metadata:
    ``set_matrix()`` / ``set_eotf()`` / ``set_static_metadata()`` update
    internal state, but the wire signal keeps carrying the snapshot from
    the most recent ``display_frame()`` call until the next one is made.
    Applies to both SDI and HDMI (parametrised via the ``decklink_devices``
    fixture); the README's earlier HDMI-vs-SDI distinction was wrong, as
    SDI also requires the explicit refresh.

    Phases:

    1. **Baseline.** Push a frame with ``SDR + Rec.709``. Capture and
       confirm the wire reports those values.
    2. **Setters without ``display_frame()``.** Call
       ``set_matrix(Rec.2020)`` and ``set_eotf(PQ)``. Capture again and
       assert the wire **still** reports ``SDR + Rec.709`` — the previous
       snapshot persists.
    3. **Refresh.** Call ``display_frame()`` with the same frame data.
       Capture again and assert the wire now reports ``PQ + Rec.2020``.

    If phase 2 fails (wire updated without refresh), the snapshot
    semantics are wrong for that transport. If phase 3 fails (wire
    didn't update after refresh), the refresh recommendation is wrong.
    """
    output_device, input_device, transport = decklink_devices

    _configure_output_metadata(
        output_device,
        matrix=decklink_io.Matrix.Rec709,
        eotf=decklink_io.Eotf.SDR,
        static_metadata_kwargs=None,
    )
    settings = output_device.get_video_settings(DISPLAY_MODE)
    settings.format = PIXEL_FORMAT
    assert output_device.setup_output(settings), \
        f"Failed to setup output for {transport}"

    try:
        # Phase 1: baseline. Push frame with the initial metadata.
        _push_frame(output_device, settings.width, settings.height)
        time.sleep(0.5)

        assert input_device.start_capture(), \
            f"Failed to start capture for {transport}"
        try:
            baseline = _capture_frame(input_device)
            assert baseline.matrix == decklink_io.Matrix.Rec709, (
                f"{transport} baseline matrix: expected Rec709, "
                f"got {baseline.matrix}"
            )
            assert baseline.eotf == decklink_io.Eotf.SDR, (
                f"{transport} baseline EOTF: expected SDR, got {baseline.eotf}"
            )

            # Phase 2: change metadata WITHOUT calling display_frame().
            # Wire should still carry the baseline snapshot.
            output_device.set_matrix(decklink_io.Matrix.Rec2020)
            output_device.set_eotf(decklink_io.Eotf.PQ)
            time.sleep(0.5)  # let several wire-frames flow

            after_setter = _capture_frame(input_device)
            assert after_setter.matrix == decklink_io.Matrix.Rec709, (
                f"{transport}: matrix changed on the wire without a "
                f"display_frame() call — expected sticky Rec709, "
                f"got {after_setter.matrix}. The snapshot semantics "
                f"described in the README do not hold on this transport."
            )
            assert after_setter.eotf == decklink_io.Eotf.SDR, (
                f"{transport}: EOTF changed on the wire without a "
                f"display_frame() call — expected sticky SDR, "
                f"got {after_setter.eotf}."
            )

            # Phase 3: push the same frame to commit the new metadata.
            _push_frame(output_device, settings.width, settings.height)
            time.sleep(0.5)

            after_push = _capture_frame(input_device)
            assert after_push.matrix == decklink_io.Matrix.Rec2020, (
                f"{transport}: matrix did not update on the wire after "
                f"display_frame() — expected Rec2020, "
                f"got {after_push.matrix}."
            )
            assert after_push.eotf == decklink_io.Eotf.PQ, (
                f"{transport}: EOTF did not update on the wire after "
                f"display_frame() — expected PQ, got {after_push.eotf}."
            )
        finally:
            input_device.stop_capture()
    finally:
        output_device.stop_output()
