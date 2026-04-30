# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `tests/_helpers.py` with shared `--no-wait` and `--no-display` CLI flags for hardware-dependent test scripts. With `--no-wait`, interactive Ctrl+C waits between phases auto-advance after a brief hold; with `--no-display`, `test_loopback.py` skips the matplotlib visual diff and reports pass/fail only. Lets the same scripts run interactively for visual confirmation and non-interactively for API smoke-testing.
- `tests/run_all_tests.py` — single entry point that smoke-runs every hardware-dependent test script in non-interactive mode and aggregates pass/fail. Designed to catch API-shape regressions (like the stale `narrow_range=` argument fixed in 0.17.0b2) before tagging a release. Prompts to confirm SDI BNC and HDMI loopback cables are connected before running.
- CI now runs the non-hardware test suite (`pytest tests/ -m "not hardware"`) on every push and PR, across macOS / Linux / Windows × Python 3.8–3.14. Hardware-dependent test files are tagged with `pytestmark = pytest.mark.hardware` so they're skipped automatically; previously, CI only confirmed that the wheel built and imported. `test_conversion_ranges.py` is the first non-hardware test exercised in CI.

### Changed
- Capability detection added to `test_resolutions.py`, `test_rgb10_colorbars.py`, and `test_rgb12_colorbars.py`: each test now checks `is_pixel_format_supported()` before attempting a mode/format combination and reports SKIP rather than FAIL if the device doesn't support it. Real failures still report FAIL. Test scripts now propagate exit codes correctly (`sys.exit(main())`) so `tests/run_all_tests.py` reflects the truth — previously these scripts always exited 0 regardless of internal failures.

### Fixed
- `[project.urls]` in `pyproject.toml` still pointed at the archived `blackmagic-output` repo. Updated to point at `blackmagic-io`. Affects the project page on PyPI.
- Timecode frames captured from HFR sources (50p, 59.94p, 60p) capped at 29 with each value appearing twice instead of counting 0–49 / 0–59. Per SMPTE 12M-1, HFR signals keep the binary frame counter at 0–29 and use the field-mark bit (`bmdTimecodeFieldMark`) as the LSB to distinguish the two halves of each frame pair. The DeckLink SDK exposes that bit on `IDeckLinkTimecode::GetFlags()` but does not fold it into `GetComponents()`. `onFrameArrived` now combines it when the detected framerate is >30 fps and the raw frame counter is <30 (sources that already emit the full 0–59 counter pass through unchanged). Reported by the team working on hdr-monitor.

## [0.17.0b2] - 2026-04-28

### Fixed
- `tests/test_rgb10_colorbars.py` and `tests/test_rgb12_colorbars.py` were calling `BlackmagicOutput.display_static_frame()` with a stale `narrow_range=` keyword argument that was renamed in 0.15.0b0 (split into `input_narrow_range` and `output_narrow_range`). The tests had been broken since that release but were never re-run because they require manual interaction. Updated to use `output_narrow_range=` (the correct mapping for the float-input output cases these tests exercise).

### Changed
- **BREAKING**: Renamed `HdrMetadataCustom` to `HdrStaticMetadata` and the corresponding setter method. The original "custom" name implied users could supply their own non-standard fields, which is misleading — the struct's fields are the fixed schema defined by SMPTE ST 2086 (mastering display) and CEA-861.3 (HDR Static Metadata Type 1 InfoFrame: MaxCLL, MaxFALL). The new name matches the standards' terminology and is consistent with Blackmagic's own use of "HDR Static" in `bmdDynamicRangeHDRStaticPQ` / `bmdDynamicRangeHDRStaticHLG`. Affected names:
  - `HdrMetadataCustom` (Python and C++ class) → `HdrStaticMetadata`
  - `set_hdr_metadata_custom()` (Python) / `setHdrMetadataCustom()` (C++) → `set_hdr_static_metadata()` / `setHdrStaticMetadata()`
  - `'custom'` key in the high-level `hdr_metadata` dict → `'static_metadata'`

### Migration

Anyone using HDR static metadata with versions 0.16.0b0 / 0.17.0b0 / 0.17.0b1 needs to update three things:

1. **Class name** — replace `HdrMetadataCustom()` with `HdrStaticMetadata()`. The fields are unchanged.

   ```diff
   - meta = decklink_io.HdrMetadataCustom()
   + meta = decklink_io.HdrStaticMetadata()
   ```

2. **Low-level method** — replace `set_hdr_metadata_custom(...)` with `set_hdr_static_metadata(...)`. Argument list is unchanged.

   ```diff
   - output.set_hdr_metadata_custom(Gamut.Rec2020, Eotf.PQ, meta)
   + output.set_hdr_static_metadata(Gamut.Rec2020, Eotf.PQ, meta)
   ```

3. **High-level dict key** — when calling `display_static_frame(...)` / `display_solid_color(...)` with `hdr_metadata`, the dict key changes from `'custom'` to `'static_metadata'`.

   ```diff
   - hdr_metadata={'eotf': Eotf.PQ, 'custom': meta}
   + hdr_metadata={'eotf': Eotf.PQ, 'static_metadata': meta}
   ```

No fields, behaviour, or signatures change beyond the names.

## [0.17.0b1] - 2026-04-28

### Added
- Pre-built wheels for Python 3.13 and 3.14 on macOS, Linux, and Windows. The Windows cp314 wheel is built but its in-CI self-test is skipped pending NumPy's release of stable Windows cp314 wheels (NumPy currently only ships an experimental MINGW-W64 build for that combination, which crashes on import). The wheel itself is functional and will be usable once NumPy releases proper MSVC cp314 wheels.

### Changed
- Bumped minimum supported Python from 3.7 to 3.8. PEP 440 metadata, README, and CI test matrix all updated to match. Python 3.7 reached end-of-life in June 2023 and was not in the wheel build matrix anyway.

### Documentation
- README installation section split into a recommended PyPI install option and a build-from-source option for contributors. Added explicit note that Blackmagic Desktop Video must be installed separately as the runtime DeckLink driver/framework — the SDK headers vendored in this repo are build-time only.

## [0.17.0b0] - 2026-04-27

### Added
- **HDMI input EDID dynamic range advertisement**: The HDMI EDID now advertises the transfer functions the input is willing to receive, so HDR sources transmit HDR Static Metadata. The SDK default omits HLG, which causes many HDMI sources to strip HDR Static Metadata when transmitting HLG signals.
  - New low-level method `DeckLinkInput::setHDMIInputDynamicRanges(int64_t bmdDynamicRangeMask)` (C++)
  - New Python binding `DeckLinkInput.set_hdmi_input_dynamic_ranges(dynamic_range_mask)`
  - Mask is a passthrough of `BMDDynamicRange` bits (`bmdDynamicRangeSDR | bmdDynamicRangeHDRStaticPQ | bmdDynamicRangeHDRStaticHLG`) so newer SDKs adding additional bits work without library changes
  - May be called before or after `initialize()`; soft-fails on non-HDMI connections and on hardware that does not expose `IDeckLinkHDMIInputEDID`
  - The library releases its EDID interface in `cleanup()`, restoring the default EDID per the SDK
- `tools/pixel_reader` writes the same default EDID dynamic range mask when the active input is HDMI, so the diagnostic tool reports HLG correctly out of the box
- New tests for HDR static metadata round-trip:
  - `tests/test_hdmi_metadata_loopback.py` — exercises SDR, HDR Traditional, PQ Rec.2020, PQ Rec.709, and HLG Rec.2020 over an HDMI loopback
  - `tests/test_sdi_metadata_loopback.py` — mirror over an SDI BNC loopback for transport-isolation diagnostics

### Changed
- **Default HDMI input EDID**: now advertises `SDR | HDR Static PQ | HDR Static HLG`, expanding the SDK default of `SDR | HDR Static PQ`. Existing consumers gain correct HLG detection without code changes; HDR-aware HDMI sources may now transmit HDR Static Metadata for HLG signals where they previously stripped it.

### Fixed
- **Capture returning BMD no-signal placeholder frames**: `onFrameArrived` now checks the `bmdFrameHasNoInputSource` flag on each incoming frame and skips placeholder frames entirely, signalling format-detection on the first real-signal frame. This replaces an earlier workaround that set the format-detected flag unconditionally after `StartStreams()`, which caused `captureFrame()` to return uniform-black placeholder frames when called before BMD had locked onto the source. The new approach also fixes the original "format-detected callback never fires when the signal mode matches the initial enable mode" timeout bug that the workaround was trying to address.
- Mode change detection in `DeckLinkOutput::setupOutput()`: the `m_currentSettings = settings` assignment was being made before the `m_currentSettings.mode != settings.mode` comparison, so the comparison was always equal and the output was never disabled/re-enabled when the display mode changed. Assignment is now made after the comparison.
- Capture buffer alignment: `DeckLinkInput` now uses `IDeckLinkVideoFrame::GetRowBytes()` rather than computing row size from width and pixel format, so capture buffers correctly account for any driver-applied row padding.
- Output range preservation: super-whites (above the narrow-range maximum) and sub-blacks (below the narrow-range minimum) are no longer clamped to the legal range during float-to-integer conversion.
- Windows build: added `#include <comutil.h>` to `decklink_output.cpp` so `_bstr_t` resolves on Windows, and added `NOMINMAX` to the Windows compile definitions in `CMakeLists.txt` so the `min` / `max` preprocessor macros from `windows.h` no longer collide with `std::min` / `std::max`. macOS and Linux builds were unaffected.

### Documentation
- Documented HDMI vs SDI behaviour when changing HDR static metadata mid-stream: SDI carries metadata per-frame in the VPID and updates immediately on the next frame, but the HDMI HDR Static Metadata InfoFrame is sticky and does not refresh until new video data is sent. Consumers updating metadata mid-stream over HDMI must call `display_frame()` again (the same frame contents are sufficient) for the new metadata to reach the sink. Captured in the `set_hdr_metadata*()` docstrings and the README.

### Notes
- Verified end-to-end on the SDI and HDMI metadata loopback tests: SDR, PQ Rec.2020, PQ Rec.709, and HLG Rec.2020 round-trip correctly.
- `tests/test_loopback.py` now covers only 10-bit YUV, 10-bit RGB, and 12-bit RGB; 8-bit BGRA and 8-bit YUV were dropped since their loopback round-trip error is precision-limited rather than a regression signal — they are not production formats for this library and a pass/fail threshold is not meaningful.
- `tests/test_hdmi_metadata_loopback.py` and `tests/test_sdi_metadata_loopback.py` now cover SDR Rec.709, SDR Rec.2020, PQ Rec.2020, PQ Rec.709, and HLG Rec.2020. HDR Traditional Gamma was dropped as it is not a format used in practice. SDR Rec.2020 verifies matrix/colorimetry signalling without an HDR EOTF.

## [0.16.0b0] - 2025-12-03

### Added
- **Video capture support**: New `BlackmagicInput` class for capturing video from DeckLink devices
  - `capture_frame_as_rgb()`: Capture and convert to RGB float array
  - `capture_frame_with_metadata()`: Capture with format metadata (resolution, colorspace, EOTF, etc.)
  - `get_detected_format()`: Query detected input signal format
  - Automatic format conversion from all DeckLink pixel formats to RGB
  - Context manager support for automatic resource cleanup
- Low-level `DeckLinkInput` C++ class for direct capture control
- `CapturedFrame` data structure containing frame data and metadata
- **Full HDR metadata capture**: `capture_frame_with_metadata()` now includes complete SMPTE ST 2086 / CEA-861.3 HDR static metadata when present in the input signal
  - Display primaries (red, green, blue X/Y chromaticity coordinates)
  - White point (X/Y chromaticity coordinates)
  - Mastering display luminance (max/min in cd/m²)
  - Content light levels (MaxCLL and MaxFALL in cd/m²)
  - All metadata fields are optional and only included when present in the signal
  - Accessible via `'hdr_metadata'` dictionary key in returned frame data
- **Timecode capture**: Input API now captures timecode from incoming video signals
  - Automatically extracts timecode from RP188 VITC, LTC, or high frame rate timecode sources
  - Accessible via `'timecode'` dictionary key in `capture_frame_with_metadata()` and `capture_frame_as_uint8_with_metadata()`
  - Includes hours, minutes, seconds, frames, and drop frame flag
  - Low-level API exposes timecode through `CapturedFrame` struct fields

### Changed
- **BREAKING**: Library renamed from `blackmagic-output` to `blackmagic-io` to reflect input/output support
  - Python package: `blackmagic_output` → `blackmagic_io`
  - C++ module: `decklink_output` → `decklink_io`
  - Import statements must be updated: `from blackmagic_io import ...` and `import decklink_io`
- **Internal refactoring**: Restructured C++ codebase to support both input and output
  - Extracted shared code into `decklink_common.{hpp,cpp}` (device enumeration, format definitions, utility functions)
  - Renamed `decklink_wrapper.{hpp,cpp}` to `decklink_output.{hpp,cpp}` for clarity
  - Added `decklink_input.{hpp,cpp}` for capture functionality
  - Consolidated platform-specific implementations (macOS, Windows, Linux) into unified source files

### Fixed
- **RGB10 and RGB12 rounding**: Fixed rounding errors in float to 10-bit and 12-bit RGB conversions
  - Now uses proper rounding (add 0.5 before truncation) instead of truncation
  - Ensures correct code values, especially at boundaries (e.g., 0.5 → 512 not 511 for 10-bit)

### Removed
- Removed internal platform-specific wrapper files (`decklink_wrapper_mac.cpp`)
  - Functionality consolidated into `decklink_output.cpp`

### Notes
- Breaking change: Update import statements when upgrading
- All existing output functionality preserved and tested
- All tests pass (device detection, format support, conversions, metadata, diagnostics, loopback)

## [0.15.0b0] - 2025-01-22

### Added
- `get_supported_display_modes()` method to query device capabilities
  - Returns list of all display modes supported by the initialized device
  - Each mode includes: display_mode enum, name, width, height, framerate
  - Useful for populating display mode dropdowns in GUI applications
  - Exposes SDK's `GetDisplayModeIterator()` functionality
- Color patch support in `display_solid_color()` method
  - New `patch` parameter: tuple (center_x, center_y, width, height) with normalized coordinates (0.0-1.0)
  - New `background_color` parameter: R'G'B' tuple for background when using patches
  - Useful for testing, calibration, and creating custom test patterns
  - Background color defaults to black (0 or 64 depending on `input_narrow_range`)
- Comprehensive test suite for range conversions (24 tests covering all range combinations)
- RGB12 documentation sections in README (previously missing)

### Changed
- **BREAKING**: Replaced ambiguous `narrow_range` parameter with explicit `input_narrow_range` and `output_narrow_range` parameters
  - Affects high-level API methods: `display_static_frame()` and `display_solid_color()`
  - Affects low-level conversion functions: `rgb_uint16_to_yuv10()`, `rgb_float_to_yuv10()`, `rgb_uint16_to_rgb10()`, `rgb_float_to_rgb10()`, `rgb_uint16_to_rgb12()`, `rgb_float_to_rgb12()`
  - `input_narrow_range`: Controls interpretation of uint16 input values (narrow: 64-940 @10-bit, i.e., 4096-60160 @16-bit; full: 0-65535)
  - `output_narrow_range`: Controls output encoding (narrow or full range)
  - Float inputs always interpreted as full range (0.0-1.0), no `input_narrow_range` parameter
- **Improved**: YUV10 output now supports full range Y'CbCr (0-1023) via `output_narrow_range=False`
  - Previously only narrow range (64-940/64-960) was supported
- **Optimized**: uint16 RGB conversions use efficient bit-shift when input and output ranges match, float conversion when they differ

### Fixed
- Removed manual range conversion code from high-level API that prevented full range YUV10 output

### Notes
- Default behavior maintained for backward compatibility:
  - `input_narrow_range=False` (full range 16-bit input)
  - `output_narrow_range=True` for YUV10 and RGB10 (narrow range output)
  - `output_narrow_range=False` for RGB12 (full range output)
- Applications using default parameters do not require code changes

## [0.14.0b0] - 2025-10-17

### Changed
- **Build system**: Switched from setuptools to CMake + scikit-build-core
  - Provides better cross-platform build support
  - Improved Linux compatibility
- **Directory structure**: Moved SDK headers from `decklink_sdk/` to `_vendor/decklink_sdk/`
- **C++ improvements**: Enhanced cross-platform support for Linux builds
  - Uses `memcmp` for `REFIID` comparison on Linux
  - Platform-specific string handling for device and display mode names

### Notes
- No breaking changes to the Python API
- Users building from source will need CMake (automatically handled by scikit-build-core)
- Installation command remains the same: `pip install -e .`

## [0.13.0-beta] - 2025-01-16

### Added
- New `pixel_reader` utility tool for reading and verifying SDI/HDMI output
  - Displays pixel values, metadata (EOTF, matrix), and video format information
  - Supports input selection for devices with multiple inputs
  - Useful for validating output from this library

### Removed
- **BREAKING**: Removed `is_display_mode_supported()` method from high-level API (`BlackmagicOutput`)
  - Use `is_pixel_format_supported(display_mode, pixel_format)` instead for more specific hardware capability checking
  - The removed method only checked if a display mode exists in the enum, not if hardware actually supports it
- **BREAKING**: Removed 8-bit YUV pixel format support
  - This needed to be supplied with packed 8-bit YUV data, which there were no helper functions to support
  - 8-bit data (uint8 dtype) uses BGRA format, which is converted by the SDK to 8-bit YCbCr output
  - Simplifies API by removing redundant pixel format

## [0.12.0-beta] - 2025-01-12

### Removed
- **BREAKING**: Removed `setup_output()` method from high-level API (`BlackmagicOutput`)
  - The method had no practical use case - `display_static_frame()` and `display_solid_color()` handle setup automatically
  - For applications that need to setup output without displaying (e.g., testing), use the low-level API (`decklink_io.DeckLinkOutput`)
  - Tests updated to use low-level API for setup-only operations

## [0.11.0-beta] - 2025-01-12

### Removed
- **BREAKING**: Removed timecode support entirely
  - Removed `set_timecode()` and `get_timecode()` methods from low-level API
  - Removed `Timecode` class
  - Removed `timecode_example.py` example
  - Rationale: Timecode requires real-time scheduled playback to be accurate. The current API only supports manual frame display (not scheduled playback), making timecode unreliable as it simply increments per `display_frame()` call rather than tracking actual elapsed time. Since the library is designed for manual frame display use cases (video routing, still frames, test patterns), timecode support is unnecessary complexity.

## [0.10.0-beta] - 2025-01-11

### Changed
- **BREAKING**: Replaced asynchronous scheduled playback with synchronous frame display
- **BREAKING**: Removed `start_output()` method from low-level API
- **BREAKING**: Timecode now increments per `display_frame()` call instead of automatically in the background
- Display mode switching is now instant with no delays or black screens
- Simplified internal implementation by removing ~200 lines of callback and scheduling code

### Added
- New `display_frame()` method for synchronous frame display in low-level API
- Support for instant display mode switching without stopping/restarting output

### Fixed
- Display mode switching now works correctly without black screens or delays
- Eliminated timing issues related to asynchronous hardware operations

### Notes
- For timecode to advance in real-time, applications must call `display_frame()` at the appropriate frame rate (e.g., 25 times per second for 25fps video)
- High-level `display_static_frame()` API remains unchanged and handles this automatically

## [0.9.0-beta] - 2025-01-10

### Added
- 12-bit RGB support
- 10-bit RGB output
- Hardware capability checking methods: `is_display_mode_supported()` and `is_pixel_format_supported()`

### Changed
- Renamed `video_range` parameter to `narrow_range` throughout the API

### Fixed
- HDR metadata now correctly omits luminance values for HLG (only sets for PQ)

## Earlier versions

See git history for changes prior to 0.9.0-beta.
