# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.18.0b1] - 2026-05-21

### Changed (breaking)
- **Split the C++ `Gamut` enum into `Matrix` + `Gamut`.** The SDK conflates two distinct concepts under "colorimetry" / `BMDColorspace`: the Y'CbCr matrix (Rec.601/709/2020 coefficient set, signalled on the wire via VPID for SDI and the AVI InfoFrame for HDMI — needed by every Y'CbCr signal, SDR or HDR) and the HDR static-metadata colorimetry bundle (display primaries + white point, conveyed via the HDR Static Metadata InfoFrame — only meaningful for PQ output on tested hardware). The previous `Gamut` enum was used for both. Now: `Matrix` for the Y'CbCr matrix (used by the eight YUV↔RGB conversion functions and the captured-frame attribute), and `Gamut` reserved for HDR static-metadata signalling. Both enums carry the same `Rec601/Rec709/Rec2020` values; in Python they become distinct types (`isinstance(x, Gamut)` and `isinstance(x, Matrix)` are no longer interchangeable).
- **Renamed captured-frame `colorspace` → `matrix`** on the `CapturedFrame` C++ attribute and in the dict returned by every `capture_frame_*_with_metadata()` variant. The field has always been the Y'CbCr matrix, not the gamut — the rename matches the conceptual model.
- **Replaced bundled `setHdrMetadata` / `setHdrStaticMetadata` / `clearHdrMetadata` with per-field setters `setMatrix(Matrix)`, `setEotf(Eotf)`, `setStaticMetadata(HdrStaticMetadata)`.** The old setters bundled the matrix with the EOTF (forcing callers who wanted to signal a Rec.2020 matrix to also touch HDR fields), and the "Hdr" prefix mislabelled the matrix as HDR-specific — the SDK's matrix-tagging callback (`bmdDeckLinkFrameMetadataColorspace`) is the only path that signals the matrix in VPID / AVI InfoFrame regardless of EOTF, so the old setters had to be (mis)used for SDR Rec.2020 / Rec.601 signalling. The new setters address the fields independently. `setMatrix()` continues to default-fill HDR Static Metadata primaries / white point / mastering luminance from the matrix name (Rec.2020 → Rec.2020 primaries; else → Rec.709), preserving the "sane defaults for PQ output without explicit static metadata" behaviour. The metadata-extension wrapper that signals matrix + EOTF + static metadata to the SDK is engaged whenever any of the three setters has been called; if none has, the SDK's per-display-mode defaults apply. `clearHdrMetadata()` is no longer needed — to suppress the HDR Static Metadata InfoFrame, call `setEotf(Eotf.SDR)`; the SDK suppresses InfoFrame emission for SDR EOTF while continuing to signal the matrix tag. Same Python bindings: `set_matrix`, `set_eotf`, `set_static_metadata` on `DeckLinkOutput`.

### Removed
- `tests/run_all_tests.py` — was a thin cable-check prompt wrapper around `pytest tests/`. Cable requirements are now documented in the README's new "Running the Tests" section. Invoke `pytest tests/` directly.
- `tests/_helpers.py` — orphaned shared CLI helpers (`--no-wait` flag) for the interactive test scripts that were replaced by parametrised pytest in 0.17.0b5. No remaining callers.

### Fixed
- `examples/advanced/display_tpat.py` — `-r` override semantics. When a TPAT carries a `range` tag, the tag declares what the encoded code values mean (the interpretation / input range), while `-r` declares the desired wire output range. Previously `-r` overrode both, so input and output range always matched and no range conversion was ever performed — `-r narrow` on a full-range TPAT just reinterpreted the codes as narrow on both sides, passing them to the wire unchanged. The script now tracks `input_narrow_range` and `output_narrow_range` separately: `-r` overrides only the output when the TPAT has a `range` tag; with no tag, `-r` (or the default) provides both. The uint16 promotion of N-bit codes now uses `input_narrow_range` so encoded values are interpreted according to the TPAT, and a different `-r` actually performs the requested range conversion to the wire.
- `BlackmagicOutput.display_solid_color()` produced wrong wire codes for full-range integer input on non-RGB10 outputs. The 10-bit code → uint16 packing used unconditional `<< 6`, which is the canonical narrow-range representation but undershoots the canonical full-range one (10-bit `1023 << 6 = 65472`, not `65535`). The RGB10 same-range encoder's `>> 6` cancelled this exactly, masking the bug for RGB10 output. RGB12 (`>> 4`) and YUV (float `/ 65535`) consumers exposed it: full-range 10-bit white (1023) produced wire Y' = 939 instead of 940 for YUV10 narrow output, and the wire RGB12 code was 4092 instead of 4095 for full→full. Packing now branches on `input_narrow_range`: narrow uses `<< 6` (canonical narrow); full uses bit-replication `(c << 6) | (c >> 4)` (canonical full, mapping `1023 → 65535` exactly). Every downstream output path (RGB10, RGB12, YUV8/YUV10) now produces correct wire codes for both ranges. The same fix is applied to `examples/advanced/display_tpat.py:101`, generalised across bit depths — narrow uses `<< (16 - bits)`, full uses `(image << (16 - bits)) | (image >> (2 * bits - 16))`. The bug was latent before 0.17.0b5 (the symmetric capture-side bug compensated in test round-trips) and was inadvertently shipped after the 0.17.0b5 release fixed only the capture-side decoder.

## [0.17.0b5] - 2026-05-18

### Added
- New "HDMI Input Notes" section in README documenting behaviour observed on the tested DeckLink UltraStudio 4K Mini: EDID partial-controllability, cold-start format detection reliability, the HDMI/DVI protocol switch detection gap (only direction observed to fail is HDMI → DVI), 8-bit R'G'B' delivery as 10-bit R'G'B' with zero-LSB padding, the BGRA-from-Y'CbCr full-range hardware-conversion assumption (with caveats for full-range Y'CbCr sources and narrow-range footroom/headroom), and matrix-metadata honouring during Y'CbCr → BGRA conversion.
- New `output_narrow_range: bool = False` parameter on `BlackmagicInput.capture_frame_as_uint8()` and `capture_frame_as_uint8_with_metadata()`. Default `False` preserves the historical "ready to display" full-range uint8 output. Set to `True` for narrow-range 8-bit R'G'B' output (16-235 per channel) when feeding downstream processing that expects narrow-range conventions. The returned metadata dict from `capture_frame_as_uint8_with_metadata()` now includes an `'output_narrow_range'` key.
- New public `BlackmagicInput.start_capture(pixel_format=None)` wrapper method. Lets callers change pixel format mid-session without reaching into the private `_input` attribute. Tracks the requested format on the wrapper for the conversion paths.
- Automatic right-shift handling in `capture_frame_as_uint8()` / `capture_frame_as_rgb()` (and their `*_with_metadata` variants) when the user initialised capture with `pixel_format=PixelFormat.BGRA` and the SDK delivers 10-bit R'G'B' (typical for 8-bit R'G'B' HDMI sources on tested hardware). The library right-shifts each channel by 2 to recover the exact 8-bit values before any range or float conversion, avoiding the ~0.3% precision loss of decoding LSB-padded 8-bit content as native 10-bit.
- `tests/test_bgra_layout.py` — non-hardware unit tests for `rgb_to_bgra` byte ordering and for the new private `_adjust_range_uint8` helper (narrow/full range conversion at 8-bit precision, including clipping of out-of-range inputs and round-trip preservation).
- `tests/test_hdmi_bgra_loopback.py` — HDMI loopback test verifying BGRA output round-trips through `BlackmagicInput.capture_frame_as_uint8()` byte-exact for 75% colour bars (default full-range output) and for `output_narrow_range=True`. A second case sends a 0-255 greyscale ramp and verifies all 256 distinct values are preserved through the HDMI wire, catching any silent full-narrow-full scaling.
- `tests/test_hdmi_bgra_ycbcr_source.py` — HDMI loopback test for the BGRA-from-Y'CbCr-source path. Output narrow-range YUV10 with explicit Rec.709 and Rec.2020 matrix metadata, capture as BGRA, verify the SDK's hardware matrix + range conversion produces 8-bit full-range R'G'B' matching the source within ±3 (4:2:2 chroma subsampling + matrix rounding tolerance).
- `--input` / `-i` and `--device` / `-d` CLI flags on `examples/capture_preview.py` for choosing between SDI and HDMI input and selecting a specific DeckLink device. Replaces the previous positional-argument interface.
- `BlackmagicInput.capture_frame_as_uint16()` and `capture_frame_as_uint16_with_metadata()` — higher-precision counterparts to the uint8 methods. 10-bit (RGB10 / YUV10) and 12-bit (RGB12) sources keep their native precision in the uint16 result; 8-bit sources (BGRA, or RGB10-delivered-as-BGRA) are LSB-padded via `<< 8` so 0xff maps to 0xff00. Mirrors the existing `capture_frame_as_*` naming convention. Internally, `_convert_frame_to_uint8` has been refactored into a shared `_convert_frame_to_int(bit_depth)` helper used by both uint8 and uint16 public methods.
- `--mode <name>` CLI flag on `tools/pixel_reader` for manual display-mode selection. Bypasses `EnableVideoInput`'s format-detection requirement, making the tool usable on older DeckLinks that don't claim `BMDDeckLinkSupportsInputFormatDetection`. Supported names: NTSC, PAL, 720p50, 720p59.94, 720p60, 1080i50, 1080i59.94, 1080p25, 1080p29.97, 1080p30, 1080p50, 1080p59.94, 1080p60.
- `tools/pixel_reader` is now built automatically as part of `pip install -e .` on all platforms via integration into the main `CMakeLists.txt`. The executable lands at `tools/pixel_reader` (or `tools/pixel_reader.exe` on Windows), ready to run alongside the Python module. Replaces the separate Makefile-based build.

### Changed
- `BlackmagicInput.initialize()` and the auto-start paths in `capture_frame_as_*` methods now delegate to the new public `start_capture()` wrapper for consistent format tracking. No behaviour change for existing callers.
- BGRA-delivered capture path now uses the new `_adjust_range_uint8` helper internally and treats the bytes as full range regardless of `input_narrow_range` (which describes the wire signal, not the bytes the library receives). The behaviour is unchanged for the default `output_narrow_range=False`, but the rationale is now documented in both the code and the README: BGRA-delivered frames are only ever produced from Y'CbCr sources on tested hardware, and the SDK's hardware Y'CbCr → R'G'B' conversion includes range expansion.
- `examples/capture_preview.py` now uses the wrapper's public `start_capture(pixel_format=...)` method throughout instead of reaching into `input_device._input.start_capture(...)` and manually setting `_capturing`. Demonstrates the idiomatic way to change pixel format mid-session.
- Relaxed numpy upper bound from `<2.3` to `<3.0` in `pyproject.toml`. The `<2.3` cap was added in 0.17.0b1 to dodge numpy's experimental MINGW-W64 cp314 builds; with numpy 2.4 now shipping stable MSVC cp314 wheels for Python 3.14 / Windows, the old cap forced Windows / Python 3.14 users onto the older numpy 2.2 line which contains exactly the longdouble-precision import crash the cap was meant to avoid.
- `tools/pixel_reader.cpp` — kept the per-format-update diagnostics added during the 8-bit RGB input investigation (raw detection-flag hex, requested pixel format, EnableVideoInput HRESULT failure prints); reverted the experimental per-frame instrumentation and signal-recovery workaround (which never produced the intended SDK re-detection on the tested hardware).
- `tools/`: removed both the standalone `CMakeLists.txt` (parallel CMake build path that wasn't being used) and `tools/Makefile` (Windows-broken even with `make` installed: it required MinGW's `g++`, but `pixel_reader.cpp` includes `<comutil.h>` which is MSVC-only, and the expected `DeckLinkAPI.h` doesn't exist in the Windows SDK — that header is generated by MIDL at build time). `pixel_reader` is now built by the main `CMakeLists.txt` instead, reusing the per-platform variables (DeckLink include dir, generated `DeckLinkAPI_i.c` on Windows, platform libs) that the Python module already sets up.
- `README.md` cross-platform claim updated from "only macOS build fully tested so far" to reflect basic Windows verification: library output and `pixel_reader` build are now confirmed with hardware on Windows; Linux remains untested with hardware.
- Refactored the four RGB10 and four RGB12 conversion functions onto the same idiom as the YUV refactor in 0.17.0b4: range constants (`in_min`, `in_range`, `out_min`, `out_range`) hoisted out of the per-pixel loop, consistent variable naming (`rf`, `gf`, `bf`) between encoders and decoders, broadcast-familiar code-value constants (876, 64, 1023 for 10-bit; 3504, 256, 4095 for 12-bit) inline in their canonical positions. Each encoder now reads as a term-for-term inverse of its decoder. Mathematically identical to the previous code; round-trip and bit-shift fast paths unchanged.
- Full-range `rgb10_to_uint16` and `rgb12_to_uint16` (`input_narrow_range=False, output_narrow_range=False`) now use arithmetic scaling `code * 65535 / (2^bits - 1)` instead of bit-shift `<<6` / `<<4`, so full-white 10-bit code 1023 / 12-bit code 4095 map to uint16 65535 rather than 65472 / 65520. Required for `capture_frame_as_uint16` full-range output to satisfy the "full white = 65535" convention. Narrow→narrow path, range-conversion paths, and the encoder direction (`rgb_uint16_to_rgb10` / `rgb_uint16_to_rgb12`) are unaffected.
- Full→full decoder branch in `rgb10_to_uint16` and `rgb12_to_uint16` switched from arithmetic scaling to bit-replication (`(N << 6) | (N >> 4)` for 10-bit, `(N << 4) | (N >> 8)` for 12-bit). Two integer ops per channel, no float math, no clamp needed (the result is bounded in `[0, 65535]` by construction). Maps the source maximum exactly (`1023 → 65535`, `4095 → 65535`); the captured 10/12-bit code round-trips exactly through either downstream path.
- Hardware-dependent test scripts modernised to parametrised pytest. `tests/test_loopback.py` and `tests/test_resolutions.py` now use `@pytest.mark.parametrize` with module-scoped device fixtures rather than `main()` drivers iterating over format / mode lists. Bespoke pass/fail summary prints removed; pytest's native PASSED / FAILED / SKIPPED reporting carries the signal. `pytestmark = pytest.mark.hardware` is unchanged so CI continues to skip these without hardware. Unicode `✓` / `✗` glyphs in legacy print output replaced with ASCII (`[PASS]` / `[FAIL]`) — the previous glyphs crashed Python on Windows when `sys.stdout.encoding` defaulted to `cp1252`.
- `tests/test_hdmi_metadata_loopback.py` and `tests/test_sdi_metadata_loopback.py` merged into a single `tests/test_hdr_metadata_loopback.py` with transport (HDMI / SDI) as a fixture-level parametrise dimension. Pytest produces IDs like `test_hdr_metadata_roundtrip[HDMI-PQ Rec.2020 ...]` and `[SDI-PQ Rec.2020 ...]`; single source of truth for the assertion logic. Previously the two files were near-identical at ~340 lines each.
- `tests/run_all_tests.py` simplified from a per-script subprocess driver into a thin cable-check prompt wrapper around `pytest tests/`. Now ~70 lines instead of ~125; gains pytest's native parametrise reporting and colour output. Users who don't need the cable-check can invoke `pytest tests/` directly.
- Removed the matplotlib visual-diff display from `tests/test_loopback.py` (a nice-to-have once but redundant now that the numeric pass/fail thresholds carry the signal). The associated `--no-display` CLI flag was removed from `tests/_helpers.py` and from `run_all_tests.py`.
- `tests/test_rgb10_colorbars.py`, `tests/test_rgb12_colorbars.py`, and `tests/test_support_query.py` moved out of the public test suite. The colorbars files were output-only visual-inspection demos with no automated assertions; their coverage is now subsumed by `tests/test_loopback.py` (verifies RGB10 / RGB12 wire output via loopback) and `tests/test_conversion_ranges.py` (verifies the conversion math with bit-exact assertions). `test_support_query.py` was a temporary diagnostic dump from when the support-query API was being developed; it had no assertions.

### Fixed
- `examples/capture_preview.py` "Capture Full" 16-bit TIFF output rendered with wrong colours (cyan as pink, magenta as mint, blue as cream) due to uint16 wraparound. Tiny sub-zero values from Y'CbCr → R'G'B' float conversion rounding (e.g. -0.0008) wrapped to near-maximum uint16 values when cast via `(rgb_float * 65535).astype(np.uint16)`. Now clipped to `[0, 65535]` before casting; the narrow-range path also gained a defensive `np.clip` even though its `+ 4096` offset usually absorbs sub-zero floats.
- Windows: COM was never initialised on the calling thread before `CoCreateInstance` in `src/decklink_common.cpp::CreateDeckLinkIteratorInstance`. The function now calls `CoInitializeEx(nullptr, COINIT_MULTITHREADED)` first; the call is idempotent (all three of `S_OK`, `S_FALSE`, and `RPC_E_CHANGED_MODE` leave a usable apartment). Without this, any Python script calling `BlackmagicOutput()` or `BlackmagicInput()` `.initialize()` on Windows failed with "Could not create DeckLink iterator" and exited. macOS path is unaffected (the SDK's `::CreateDeckLinkIteratorInstance()` doesn't go through COM).
- `tools/pixel_reader.cpp`: three latent MSVC compile errors that prevented Windows compilation since the tool's first commit — redefinition of `BOOL` (which `<windows.h>` already provides), missing `strcasecmp` (replaced with `_stricmp` via `#define`), and an implicit `int → BMDVideoConnection` conversion that MSVC rejects.
- `tools/pixel_reader.cpp`: inverted iterator-creation check on Windows that fired the error block on success since the tool's first commit. The Windows-branch `GetDeckLinkIterator(iter)` macro evaluated to an `HRESULT` rather than the iterator pointer; `S_OK == 0 == NULL`, so the existing `if (... == NULL)` check at the call sites interpreted success as failure. Macro now evaluates to the iterator pointer (`NULL` on failure), matching the Mac/Linux convention. Symptom was identical to the COM-init bug — "Could not create DeckLink iterator" on Windows — but the root cause is independent.
- `tools/pixel_reader.cpp`: format-detection capability check (`BMDDeckLinkSupportsInputFormatDetection`) now skipped when `--mode` is supplied, since manual mode bypasses detection. Previously the early-bail fired before `--mode` could take effect, making the flag dead code on the very cards it was added to support.
- `tools/pixel_reader.cpp`: scrolling artefact on the dashboard when transitioning between formats. Per-frame output cleared its own lines but left stale lines below when a new frame rendered fewer lines than the previous one (e.g. HDR → SDR, where the SDR frame omits HDR-specific lines). Now uses `\x1b[J` to clear from cursor to end of screen on every refresh, so the dashboard is always clean.
- `CMakeLists.txt`: `RUNTIME_OUTPUT_DIRECTORY` for `pixel_reader` set per-config so the binary lands in `tools/` on multi-config generators (Visual Studio, Xcode, Ninja Multi-Config) as well as single-config ones. Previously the binary landed at `tools/Release/pixel_reader.exe` on Windows because the Visual Studio generator auto-appends `/Release` to the generic property.
- `BlackmagicOutput._prepare_frame_data` no longer silently truncates non-uint8 input on the `PixelFormat.BGRA` path. Previously, passing float or uint16 frame data to a BGRA output silently `.astype(np.uint8)`'d the array — `0.0`-to-`1.0` floats became `0` or `1`, producing near-black BGRA garbage with no error raised; uint16 silently lost the high byte. The library now raises `ValueError` for any non-uint8 dtype on the BGRA path, with a message pointing at YUV10 / RGB10 / RGB12 for higher-precision input. BGRA is intended for fast preview-quality work (it ends up as 8-bit 2vuy over SDI on tested hardware); higher-precision input there would only cause double quantisation. Docstring and README dtype-compatibility table updated accordingly.

## [0.17.0b4] - 2026-05-11

### Changed
- Refactored all nine RGB↔YUV conversion functions (`rgb_*_to_yuv8`, `rgb_*_to_yuv10`, `yuv8_to_rgb_*`, `yuv10_to_rgb_*`) onto a single shared idiom: `Kr/Kb/Kg` matrix algebra computed once per frame, chroma normalised to `[-1, +1]`, the `(1-Kr)` matrix form, and broadcast-familiar code-value constants (876, 896, 1023 for 10-bit; 219, 224, 255 for 8-bit) inline at their canonical positions. Each encoder is now a term-for-term inverse of its decoder, and the 8-bit and 10-bit functions differ only in the bit-depth constants. Mathematically identical to the previous hardcoded numerical coefficients (Rec.601, Rec.709, Rec.2020 all preserved). The YUV8 encoder previously clamped narrow-range Y to `[16, 235]` and chroma to `[16, 240]`; it now clamps only to the byte range `[0, 255]`, matching the YUV10 encoder and preserving super-blacks / super-whites in narrow-range output.

### Fixed
- `yuv8_to_rgb_uint16` and `yuv8_to_rgb_float` decoded captured 8-bit Y'CbCr (2vuy) frames with chroma scaled 2× too large, producing visibly wrong colours (over-saturated reds/blues, with sub-zero clamping) compared to the same scene captured as 10-bit Y'CbCr. The decoders normalised Cb/Cr to [-1, 1] before applying matrix coefficients that expect [-0.5, 0.5]. Round-tripping pure red (R=255,G=0,B=0) returned roughly (1.79, -0.07, -0.20) instead of (1, 0, 0). The corresponding YUV8 encoders were correct, so output paths were unaffected; only capture decoding was wrong. The YUV10 decoder uses the correct scaling and was unaffected.

### Added
- Non-hardware round-trip test coverage in `tests/test_conversion_ranges.py` for every packed pixel format. `TestYUV8RoundTrip` and `TestYUV10RoundTrip` exercise the encoder + decoder for primaries / mid-gray across narrow and full range and Rec.601 / Rec.709 / Rec.2020 matrices (the YUV8 class would have caught the chroma-scaling bug above; YUV10 previously had encoder-only coverage and the decoder ran only under the hardware loopback). `TestRGB10RoundTrip` and `TestRGB12RoundTrip` round-trip uint16 RGB and assert bit-exact equality on the same-range bit-shift fast path, plus ≤1-code drift on cross-range conversions. Runs in CI on every push and PR.
- 8-bit YUV (2vuy) re-added to `tests/test_loopback.py`; previously dropped under the (mistaken) belief that visible round-trip error was 8-bit precision loss rather than a real decoder bug. Tolerance is set to account for both 4:2:2 chroma subsampling and 8-bit Y quantisation.
- Optional `row_bytes=` parameter on the eight `*_to_uint16` / `*_to_float` decoder wrappers (`yuv8`, `yuv10`, `rgb10`, `rgb12`) and on the four `unpack_*` helpers in `blackmagic_io.__init__`. Previously, only the high-level `captured_frame_to_*` paths could forward `captured_frame.row_bytes` to the C extension; direct callers fell back to a width-derived stride that happens to be correct for HD1080 but can mismatch BMD's actual stride at other widths (HD720 v210 in particular). The same parameter and `-1` sentinel was already accepted by the underlying C++ functions and is now also exposed on the four `unpack_*` C++ entry points. Defaults are unchanged, so existing callers are unaffected. `tests/test_loopback.py` now passes `captured_frame.row_bytes` for all four packed-format paths.
- `tests/test_colour_science_parity.py` cross-checks our RGB↔YUV math against the [colour-science](https://github.com/colour-science/colour) library at byte-exact precision. For every combination of (Rec.601 / Rec.709 / Rec.2020) × (narrow / full range) × (white / black / mid-gray / R / G / B), our `rgb_float_to_yuv8`, `rgb_float_to_yuv10`, `yuv8_to_rgb_float`, and `yuv10_to_rgb_float` produce results identical to `colour.RGB_to_YCbCr` / `colour.YCbCr_to_RGB`. Catches the kind of factor-of-2 / wrong-normalisation drift that an internal round-trip test misses (encoder and decoder can both be wrong in compensating ways and round-trip cleanly). Skipped automatically if `colour-science` is not installed; opt-in via `pip install colour-science`. Not currently run in CI.

## [0.17.0b3] - 2026-04-30

### Added
- `tests/_helpers.py` with shared `--no-wait` CLI flag for hardware-dependent test scripts. With `--no-wait`, interactive Ctrl+C waits between phases auto-advance after a brief hold. Lets the same scripts run interactively for visual confirmation and non-interactively for API smoke-testing.
- `tests/run_all_tests.py` — single entry point that smoke-runs every hardware-dependent test script in non-interactive mode and aggregates pass/fail. Designed to catch API-shape regressions (like the stale `narrow_range=` argument fixed in 0.17.0b2) before tagging a release. Prompts to confirm SDI BNC and HDMI loopback cables are connected before running.
- CI now runs the non-hardware test suite (`pytest tests/ -m "not hardware"`) on every push and PR, across macOS / Linux / Windows × Python 3.8–3.14. Hardware-dependent test files are tagged with `pytestmark = pytest.mark.hardware` so they're skipped automatically; previously, CI only confirmed that the wheel built and imported. `test_conversion_ranges.py` is the first non-hardware test exercised in CI.

### Changed
- Capability detection added to `test_resolutions.py`, `test_rgb10_colorbars.py`, and `test_rgb12_colorbars.py`: each test now checks `is_pixel_format_supported()` before attempting a mode/format combination and reports SKIP rather than FAIL if the device doesn't support it. Real failures still report FAIL. Test scripts now propagate exit codes correctly (`sys.exit(main())`) so `tests/run_all_tests.py` reflects the truth — previously these scripts always exited 0 regardless of internal failures.

### Fixed
- `[project.urls]` in `pyproject.toml` still pointed at the archived `blackmagic-output` repo. Updated to point at `blackmagic-io`. Affects the project page on PyPI.
- Timecode frames captured from HFR sources (50p, 59.94p, 60p) capped at 29 with each value appearing twice instead of counting 0–49 / 0–59. Per SMPTE 12M-1, HFR signals keep the binary frame counter at 0–29 and use the field-mark bit (`bmdTimecodeFieldMark`) as the LSB to distinguish the two halves of each frame pair. The DeckLink SDK exposes that bit on `IDeckLinkTimecode::GetFlags()` but does not fold it into `GetComponents()`. `onFrameArrived` now combines it when the detected framerate is >30 fps. The fold is also gated on the raw counter being <30 as a defensive guard, so the code remains correct if a future SDK version or a non-standard source pre-folds the bit and returns the full 0–59 counter directly.

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
- Output range preservation: super-whites (above nominal white) and sub-blacks (below nominal black) are no longer clamped to the nominal range during float-to-integer conversion.
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
  - Background colour defaults to black (0 or 64 depending on `input_narrow_range`)
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
- Default behaviour maintained for backward compatibility:
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
