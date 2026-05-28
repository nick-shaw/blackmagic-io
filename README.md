# Blackmagic DeckLink Python I/O Library

*Continuation of [blackmagic-output](https://github.com/nick-shaw/blackmagic-output) (now archived) with input/capture support added; the package was renamed in 0.16.0b0 to reflect the broader scope.*

A Python library for video I/O with Blackmagic DeckLink devices using the official DeckLink SDK. This library provides a simple interface for displaying static frames, solid colors, and dynamic content from NumPy arrays, as well as for capturing frames to NumPy arrays.

Written by Nick Shaw, www.antlerpost.com, with a lot of help from [Claude Code](https://www.claude.com/product/claude-code)!

**⚠️ Note:** The library has only had minimal testing at this time, and is under ongoing development. Please report any issues you encounter. I am particularly interested in feedback from Linux and Windows users.

## ⚠️ Breaking changes in 0.18.0b1

If upgrading from 0.17.x:

- Captured-frame metadata dict key `'colorspace'` is now `'matrix'`, aligning the capture side with the `matrix=` parameter already used by `display_static_frame()` / `display_solid_color()`. Affects every variant of `capture_frame_*_with_metadata()`.
- `captured_frame.colorspace` attribute on the low-level `CapturedFrame` struct is now `captured_frame.matrix`.
- The `Gamut` enum has been split into `Matrix` (Y'CbCr matrix selection for YUV↔RGB conversion) and `Gamut` (HDR static-metadata signalling). YUV↔RGB conversion functions now take `Matrix`.
- Low-level setters `setHdrMetadata` / `setHdrStaticMetadata` / `clearHdrMetadata` replaced by per-field `setMatrix` / `setEotf` / `setStaticMetadata` on `DeckLinkOutput`. The high-level `display_static_frame(matrix=..., hdr_metadata=...)` API is unchanged.
- `display_static_frame()` and `display_solid_color()` now use `output_narrow_range: Optional[bool] = None` (previously `bool = True`). `None` resolves to the per-format default — True for YUV8 / YUV10 / RGB10, **False for RGB12** — matching the canonical low-level wrappers and the documented per-format defaults. RGB12 callers who omitted `output_narrow_range` previously got narrow (256-3760); they now get full (0-4095). Pass `output_narrow_range=True` explicitly to preserve the old behaviour.
- `display_static_frame()` and `display_solid_color()` now honour `input_narrow_range` on the BGRA pixel-format path (previously silently ignored). Narrow-range input is expanded to full-range R'G'B' before packing. Passing `output_narrow_range` to a BGRA call now emits a `UserWarning` and is ignored — see [BGRA output is transport-asymmetric on the wire](#bgra-output-is-transport-asymmetric-on-the-wire) under BGRA and Range Behaviour for the rationale.
- `BlackmagicInput.capture_frame_as_uint8()` / `capture_frame_as_uint16()` / `capture_frame_as_rgb()` and their `_with_metadata` variants now use `input_narrow_range: Optional[bool] = None` (previously `bool = True`). `None` resolves to a per-source-format default after format detection — True for YUV8 / YUV10 / RGB10, **False for RGB12**, and False for the BGRA-requested-but-RGB10-delivered HDMI 8-bit R'G'B' path (symmetric with the library's own BGRA → HDMI output). RGB12 sources captured with `input_narrow_range` omitted previously had narrow input assumed (incorrect for the typical full-range 12-bit R'G'B' wire); they now have full input assumed. Pass `input_narrow_range=True` explicitly to preserve the old behaviour. The `_with_metadata` variants now record the **resolved** boolean in the returned dict's `'input_narrow_range'` field, not the user-supplied `None`.

See [CHANGELOG.md](CHANGELOG.md) for the full rationale and rename mapping.

## Features

### Output
- **Static Frame Output**: Display static images from NumPy arrays
- **Solid Colour Output**: Display solid colours for testing and calibration
- **Dynamic Updates**: Update currently displayed frame
- **Multiple Resolutions**: Support for all display modes supported by your DeckLink device (SD, HD, 2K, 4K, 8K, and PC modes)
- **8 and 10-bit Y'CbCr 4:2:2 output** (`PixelFormat.YUV8`, `PixelFormat.YUV10`; 10-bit is the default for uint16/float input)
- **8, 10 and 12-bit R'G'B' 4:4:4 output** (`PixelFormat.BGRA`, `PixelFormat.RGB10`, `PixelFormat.RGB12`; 8-bit HDMI only)
- **HDR Support**: SMPTE ST 2086 / CEA-861.3 HDR static metadata
- **Y'CbCr matrix control**: Rec.601 (SD only), Rec.709 (HD+), and Rec.2020 (HD+) matrix support

### Input
- **Video Capture**: Capture video frames from DeckLink devices
- **Automatic Format Conversion**: Convert all DeckLink pixel formats to R'G'B' float, uint16 or uint8 (for fast preview path)
- **Format Detection**: Automatic detection of signal properties (resolution, frame rate, pixel format / bit depth)
- **Metadata Access**: Access to signal metadata (Y'CbCr matrix, EOTF, HDR static metadata when present)
- **Range Interpretation**: Explicit user-specified narrow/full range parameters on every input and output conversion path, with correct mapping between range conventions. The DeckLink SDK does not surface source signal range via metadata, so the library defers to the caller, with defaults based on the conventions in the SDK documentation.
- **Timecode Capture**: Automatic extraction of embedded timecode (RP188 VITC/LTC/HFRTC)
- **HDMI EDID Configuration**: Advertises SDR, HDR PQ, and HDR HLG support over HDMI by default so HDR sources transmit HDR Static Metadata (the SDK default omits HLG); the advertised bitmask is configurable via `set_hdmi_input_dynamic_ranges()`

### General
- **Device Enumeration**: List connected DeckLink devices with their names and capabilities
- **Cross-Platform**: Works on Windows, macOS, and Linux. Hardware-test coverage is most extensive on macOS (SDI, HDMI, and HDR-metadata paths); on Windows, only the SDI loopback path is currently hardware-tested; Linux is build-verified via CI but hardware-untested.

## Requirements

### System Requirements
- Python 3.8 or higher
- Blackmagic DeckLink device (DeckLink, UltraStudio, or Intensity series)
- Blackmagic Desktop Video software installed

### Python Dependencies
Python dependencies (NumPy >= 1.19.0, pybind11 >= 2.6.0) are automatically installed (if needed) during the build process.

### DeckLink SDK
SDK v14.1 headers for all platforms are included in the repository - no separate download needed.

## Installation

### 1. DeckLink SDK

**All Platforms (macOS, Windows, Linux):**

- `_vendor/decklink_sdk/Mac/include/` - macOS headers
- `_vendor/decklink_sdk/Win/include/` - Windows headers
- `_vendor/decklink_sdk/Linux/include/` - Linux headers

The build system (CMake + scikit-build-core) automatically uses the correct platform-specific headers.

**⚠️ Important:** This library was built against SDK v14.1 to maintain compatibility with older macOS versions. If you need to download the SDK separately, ensure you get v14.1 from the [Blackmagic Design developer site](https://www.blackmagicdesign.com/developer/). Newer versions (v15.0+) may cause API compatibility issues and build failures.

### 2. Install the Library

**Option A (recommended for most users): from PyPI**

```bash
pip install blackmagic-io
```

This installs the latest beta. `pip` normally skips pre-releases, but falls back to them when no stable version is available — and every published version of this library is currently a beta (`0.18.0bN`). Once a stable `0.18.0` (or later) is published, `pip install blackmagic-io` will resolve to that stable version, and getting a future beta will require `pip install --pre blackmagic-io`. Pre-built wheels are available for Python 3.8–3.14 on macOS, Linux, and Windows; pip falls back to a source build on unsupported Pythons (which requires a C++ compiler — Xcode Command Line Tools on macOS, build-essential on Linux, or MSVC on Windows).

To use the library at runtime you also need Blackmagic Desktop Video installed on your system (separate from this Python package) — the runtime DeckLink driver and framework are provided by Desktop Video, available from [blackmagicdesign.com/support](https://www.blackmagicdesign.com/support).

**Option B (for contributors or for modifying the source): from a clone**

```bash
# Clone the repository
git clone https://github.com/nick-shaw/blackmagic-io.git
cd blackmagic-io

# Switch to the development branch
# (main holds released versions; work in progress lives on dev)
git checkout dev

# Initialize submodules (required for the advanced T-Pat example only)
git submodule update --init --recursive

# Install in development mode (this also installs numpy and pybind11 dependencies)
pip install -e .

# If upgrading from a previous development version, force reinstall:
pip install --force-reinstall -e .
```

### 3. Install Optional Dependencies

For examples and additional functionality:
```bash
pip install opencv-python imageio pillow jsonschema
```

**Note:** While imageio / PIL can load 16-bit TIFF files correctly, 16-bit PNG files are often converted to 8-bit during loading due to PIL limitations. For reliable 16-bit workflows, use TIFF format.

## Quick Start

Runnable example scripts live in [`examples/`](https://github.com/nick-shaw/blackmagic-io/tree/main/examples) in the repository. The snippets below are excerpts; the full scripts there cover static and dynamic output, solid colours, HDR, real-time capture preview, and TPAT-based test patterns (`examples/advanced/`).

### Output Example

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode

# Create a simple test image (1080p R'G'B', normalized float)
frame = np.ones((1080, 1920, 3), dtype=np.float32)
frame[:, :] = [1.0, 0.0, 0.0]  # Red frame

# Display the frame
with BlackmagicOutput() as output:
    # Initialize device (uses first available device)
    output.initialize()

    # Display static frame at 1080p25
    output.display_static_frame(frame, DisplayMode.HD1080p25)

    # Keep displaying (Enter to stop)
    input("Press Enter to stop...")
```

**Note:** The explicit `initialize()` call is optional - `display_static_frame()` will automatically initialize the first available device (device_index=0) if not already initialized. Explicit initialization is useful for device selection, better error handling, and timing control:

```python
# Simpler alternative - auto-initialization (uses first device)
with BlackmagicOutput() as output:
    output.display_static_frame(frame, DisplayMode.HD1080p25)
    input("Press Enter to stop...")
```

### Input Example

```python
from blackmagic_io import BlackmagicInput

# Capture a frame from DeckLink input
with BlackmagicInput() as input_device:
    # Initialize device (uses first available device)
    input_device.initialize()

    # Capture frame as R'G'B' float array (normalised 0.0-1.0)
    rgb_frame = input_device.capture_frame_as_rgb(timeout_ms=5000)

    if rgb_frame is not None:
        print(f"Captured frame: {rgb_frame.shape}, dtype: {rgb_frame.dtype}")
        print(f"Value range: {rgb_frame.min():.3f} - {rgb_frame.max():.3f}")
        # Process frame data...
    else:
        print("No signal or timeout")
```

**Capture with metadata:**

```python
from blackmagic_io import BlackmagicInput

with BlackmagicInput() as input_device:
    input_device.initialize()

    # Capture frame with format information
    frame_data = input_device.capture_frame_with_metadata(timeout_ms=5000)

    if frame_data is not None:
        print(f"Resolution: {frame_data['width']}x{frame_data['height']}")
        print(f"Format: {frame_data['format']}")
        print(f"Matrix: {frame_data['matrix']}")
        print(f"EOTF: {frame_data['eotf']}")

        # Access timecode if present
        if 'timecode' in frame_data:
            tc = frame_data['timecode']
            separator = ';' if tc['is_drop_frame'] else ':'
            print(f"Timecode: {tc['hours']:02d}:{tc['minutes']:02d}:{tc['seconds']:02d}{separator}{tc['frames']:02d}")

        # Access HDR metadata if present
        if 'hdr_metadata' in frame_data:
            hdr = frame_data['hdr_metadata']
            if 'display_primaries' in hdr:
                print(f"Display Primaries:")
                print(f"  Red:   ({hdr['display_primaries']['red']['x']:.4f}, "
                      f"{hdr['display_primaries']['red']['y']:.4f})")
                print(f"  Green: ({hdr['display_primaries']['green']['x']:.4f}, "
                      f"{hdr['display_primaries']['green']['y']:.4f})")
                print(f"  Blue:  ({hdr['display_primaries']['blue']['x']:.4f}, "
                      f"{hdr['display_primaries']['blue']['y']:.4f})")
            if 'mastering_luminance' in hdr:
                print(f"Mastering Luminance: {hdr['mastering_luminance']['max']:.1f} / "
                      f"{hdr['mastering_luminance']['min']:.4f} cd/m²")
            if 'content_light' in hdr:
                cl = hdr['content_light']
                if 'max_cll' in cl:
                    print(f"MaxCLL:  {cl['max_cll']} cd/m²")
                if 'max_fall' in cl:
                    print(f"MaxFALL: {cl['max_fall']} cd/m²")

        # Access R'G'B' data
        rgb = frame_data['rgb']  # float32 array (H×W×3)
        # Process frame...
```

## API Reference

The library provides APIs for both output and input:

**High-level Python wrappers:**
- `blackmagic_io.BlackmagicOutput` - Convenient API for video output
- `blackmagic_io.BlackmagicInput` - Convenient API for video capture

**Low-level direct access:**
- `decklink_io.DeckLinkOutput` - Fine-grained control for output
- `decklink_io.DeckLinkInput` - Fine-grained control for capture

### High-Level API: BlackmagicOutput Class

Convenient Python wrapper for most video output operations.

#### Methods

**`get_available_devices() -> List[str]`**
Get list of available DeckLink device names.

**`get_device_capabilities(device_index=0) -> dict`**
Get device capabilities (name and supported input/output).
- `device_index`: Index of device to query (default: 0)
- Returns: Dictionary with:
  - `'name'`: Device name
  - `'supports_input'`: True if device can capture video
  - `'supports_output'`: True if device can output video

**Example:**
```python
from blackmagic_io import BlackmagicOutput

output = BlackmagicOutput()
caps = output.get_device_capabilities(0)
print(f"Device: {caps['name']}")
print(f"Supports input: {caps['supports_input']}")
print(f"Supports output: {caps['supports_output']}")
```

**Note:** Some DeckLink devices are single-direction only (e.g., UltraStudio Monitor 3G supports output only, UltraStudio Recorder 3G supports input only). Use this method to check device capabilities before attempting to use them for input or output.

**`initialize(device_index=0) -> bool`**
Initialize the specified DeckLink device.
- `device_index`: Index of device to use (default: 0)
- Returns: True if successful

**Note:** Explicit initialization is optional. Methods like `display_static_frame()` and `display_solid_color()` will automatically initialize the first available device (device_index=0) if not already initialized. Explicit initialization is recommended when you need:
- To select a specific device (when multiple DeckLink devices are present)
- Separate error handling for device initialization vs. frame display
- Control over initialization timing (e.g., to avoid delays during first frame display)
- To verify device availability before preparing frame data

**`get_supported_display_modes() -> List[dict]`**
Get list of supported display modes for the initialized device.
- Returns: List of dictionaries, each containing:
  - `display_mode`: DisplayMode enum value
  - `name`: Human-readable mode name (e.g., "1080p25", "2160p59.94")
  - `width`: Frame width in pixels
  - `height`: Frame height in pixels
  - `framerate`: Frame rate in frames per second
- Raises: RuntimeError if device not initialized

**Example:**
```python
from blackmagic_io import BlackmagicOutput

with BlackmagicOutput() as output:
    output.initialize()

    modes = output.get_supported_display_modes()
    for mode in modes:
        print(f"{mode['name']}: {mode['width']}x{mode['height']} @ {mode['framerate']:.2f} fps")
```

**`is_pixel_format_supported(display_mode, pixel_format) -> bool`**
Check if a pixel format is supported for a given display mode.
- `display_mode`: Display mode to check
- `pixel_format`: Pixel format to check
- Returns: True if the mode / format combination is supported

**`display_static_frame(frame_data, display_mode, pixel_format=PixelFormat.YUV10, matrix=None, hdr_metadata=None, input_narrow_range=False, output_narrow_range=None) -> bool`**
Display a static frame continuously.
- `frame_data`: NumPy array with image data. Accepted shape and dtype depend on `pixel_format`:
  - `BGRA` (fast preview): shape (height, width, 3) R'G'B' or (height, width, 4) BGRA; dtype `uint8` only. `input_narrow_range` controls how the library interprets the input bytes — narrow 16-235 input is expanded to full 0-255 via `_adjust_range_uint8` before BGRA packing, mirroring the capture-side range handling. `output_narrow_range` is ignored on the BGRA path (a `UserWarning` is issued if explicitly passed): the SDK's hardware conversion produces narrow-range Y'CbCr 4:2:2 on the SDI wire and full-range R'G'B' 4:4:4 on the HDMI wire regardless of buffer contents. For controlled output range — including narrow-range R'G'B' on HDMI — use `YUV10` / `RGB10` / `RGB12` instead.
  - `YUV8`: shape (height, width, 3) R'G'B'; dtype `uint8`, `uint16`, `float32`, or `float64`.
  - `YUV10` / `RGB10` / `RGB12`: shape (height, width, 3) R'G'B'; dtype `uint16`, `float32`, or `float64`.
- `display_mode`: Video resolution and frame rate
- `pixel_format`: Pixel format (default: YUV10, automatically uses BGRA for uint8 data)
- `matrix`: Optional R'G'B' to Y'CbCr conversion matrix (`Matrix.Rec601`, `Matrix.Rec709` or `Matrix.Rec2020`). Only affects output code values with Y'CbCr output formats (YUV8 / YUV10); signalled in the SDI VPID and HDMI InfoFrame for all pixel formats. If not specified, auto-detects based on resolution: SD modes (NTSC, PAL) use Rec.601, HD and higher use Rec.709
- `hdr_metadata`: Optional HDR metadata dict with keys:
  - `'eotf'`: Eotf enum (SDR, PQ, or HLG)
  - `'static_metadata'`: Optional HdrStaticMetadata object with explicit display primaries, white point, mastering luminance, and content light level fields
- `input_narrow_range`: Whether to interpret integer `frame_data` as narrow range (float is always interpreted as full range). Default: False
- `output_narrow_range`: Whether to output a narrow range signal. Default: `None` — each format applies its own default (True for YUV8 / YUV10 / RGB10, False for RGB12). Ignored for BGRA (a warning is issued if explicitly passed); see the `BGRA` bullet above and the [PixelFormat](#blackmagicoutput---static-display) section for per-format details.
- Returns: True if successful

**`display_solid_color(color, display_mode, pixel_format=PixelFormat.YUV10, matrix=None, hdr_metadata=None, input_narrow_range=False, output_narrow_range=None, patch=None, background_color=None) -> bool`**
Display a solid colour continuously.
- `color`: R'G'B' tuple (r, g, b) with values:
  - Integer values (0-1023): Interpreted as 10-bit values
  - Float values (0.0-1.0): Interpreted as normalized full range values
- `display_mode`: Video resolution and frame rate
- `pixel_format`: Pixel format (default: YUV10)
- `matrix`: Optional R'G'B' to Y'CbCr conversion matrix (`Matrix.Rec601`, `Matrix.Rec709` or `Matrix.Rec2020`). Only affects output code values with Y'CbCr output formats (YUV8 / YUV10); signalled in the SDI VPID and HDMI InfoFrame for all pixel formats. If not specified, auto-detects based on resolution: SD modes (NTSC, PAL) use Rec.601, HD and higher use Rec.709
- `hdr_metadata`: Optional HDR metadata dict with 'eotf' (and optional 'static_metadata') keys
- `input_narrow_range`: Whether to interpret integer `color` values as narrow range (float is always interpreted as full range). Default: False
- `output_narrow_range`: Whether to output a narrow range signal. Default: `None` — each format applies its own default (True for YUV8 / YUV10 / RGB10, False for RGB12). Ignored for BGRA (a warning is issued if explicitly passed).
- `patch`: Optional tuple (center_x, center_y, width, height) with normalized coordinates (0.0-1.0):
  - center_x, center_y: Center position of the patch (0.5, 0.5 = center of screen)
  - width, height: Patch dimensions (1.0, 1.0 = full screen)
  - If None, displays full screen solid colour. Default: None
- `background_color`: R'G'B' tuple for background when using patch parameter. Uses same format as `color` parameter (respecting `input_narrow_range`). If None, defaults to black. Default: None
- Returns: True if successful

**`update_frame(frame_data) -> bool`**
Update currently displayed frame with new data. The pixel format, matrix, and range parameters from the most recent `display_static_frame()` call are reused. The new array must match the original's height and width and use a dtype that is valid for the configured pixel format (see `display_static_frame()` for per-format accepted dtypes). Raises `ValueError` on height/width / dtype / channel-count mismatch.
- `frame_data`: New frame data as NumPy array
- Returns: True if successful

**`get_display_mode_info(display_mode) -> dict`**
Get information about a display mode.
- Returns: Dictionary with 'width', 'height', 'framerate'

**`get_current_output_info() -> dict`**
Get information about the current output configuration.
- Returns: Dictionary with 'display_mode_name', 'pixel_format_name', 'width', 'height', 'framerate', 'rgb444_mode_enabled'

**`stop() -> bool`**
Stop video output.
- Returns: True if successful

Stops displaying frames but keeps the device initialized and ready for immediate reuse. After calling `stop()`, you can call `display_static_frame()` or `display_solid_color()` again without needing to re-initialize.

**`cleanup()`**
Cleanup resources and stop output.

Stops video output (if running) and releases all device resources. After `cleanup()`, the device must be re-initialized with `initialize()` before it can be used again. This method automatically calls `stop()` internally, so there is no need to call `stop()` first.

**Context Manager Support:**
```python
with BlackmagicOutput() as output:
    output.initialize()
    # ... use output ...
# Automatic cleanup() called on exit
```

The context manager automatically calls `cleanup()` when exiting, so explicit cleanup is not needed when using the `with` statement.

#### Utility Functions

**`create_test_pattern(width, height, pattern='gradient', grad_start=0.0, grad_end=1.0) -> np.ndarray`**
Create test patterns for display testing and calibration.
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `pattern`: Pattern type - `'gradient'`, `'bars'`, or `'checkerboard'`
- `grad_start`: Float starting value for gradient pattern (default: 0.0, use <0.0 for sub-black)
- `grad_end`: Float ending value for gradient pattern (default: 1.0, use >1.0 for super-white)
- Returns: R'G'B' array (H×W×3), dtype float32

### High-Level API: BlackmagicInput Class

Convenient Python wrapper for video capture operations.

#### Methods

**`get_available_devices() -> List[str]`**
Get list of available DeckLink device names.

**`get_device_capabilities(device_index=0) -> dict`**
Get device capabilities (name and supported input/output).
- `device_index`: Index of device to query (default: 0)
- Returns: Dictionary with:
  - `'name'`: Device name
  - `'supports_input'`: True if device can capture video
  - `'supports_output'`: True if device can output video

**`get_available_input_connections(device_index=0) -> List[InputConnection]`**
Get available input connections for a DeckLink device.
- `device_index`: Index of device to query (default: 0)
- Returns: List of InputConnection enum values (e.g., `[InputConnection.SDI, InputConnection.HDMI]`)

Use this to check which physical inputs are available on a device before selecting one with `initialize()`.

**`initialize(device_index=0, input_connection=None, pixel_format=None) -> bool`**
Initialize the specified DeckLink device for input and start capture.
- `device_index`: Index of device to use (default: 0)
- `input_connection`: Optional InputConnection enum to select specific input (e.g., `InputConnection.SDI`, `InputConnection.HDMI`). If None, uses the device's current input.
- `pixel_format`: Optional PixelFormat to request from hardware (default: YUV10)
- Returns: True if successful

Immediately activates capture mode, which will:
- Start accepting input signal
- Activate front panel display (if present)
- Enable format detection

**Performance Note:** Requesting `PixelFormat.BGRA` enables real-time preview by having the hardware deliver 8-bit BGRA frames directly, avoiding expensive colorspace conversions. This is ideal for monitoring and preview workflows. For high-quality capture, use the default YUV10 (or explicitly specify it) — the request is a hint, and the actual delivered format follows the wire signal: Y'CbCr sources arrive as YUV10, R'G'B' sources as RGB10 or RGB12 at their native bit depth. The library's `capture_frame_as_rgb()` / `capture_frame_with_metadata()` / `capture_frame_as_uint16()` paths dispatch on the delivered format and preserve its native precision (e.g. 12-bit for an RGB12 source).

**`capture_frame_as_uint8(timeout_ms=5000, input_narrow_range=None, output_narrow_range=False) -> Optional[np.ndarray]`**
Capture a single frame and convert to R'G'B' uint8 (faster than float conversion).
- `timeout_ms`: Timeout in milliseconds (default: 5000)
- `input_narrow_range`: Whether to interpret the wire signal as narrow range. `None` (default) resolves to a per-source-format default after format detection:
  - `YUV8` / `YUV10`: True (narrow Y'CbCr — broadcast convention)
  - `RGB10`: True (Blackmagic 10-bit R'G'B' convention)
  - `RGB12`: False (Blackmagic 12-bit R'G'B' convention)
  - `BGRA` requested but delivered as RGB10 (HDMI 8-bit R'G'B'): False (full-range "computer signal" convention, symmetric with the library's own BGRA → HDMI output)
  - `BGRA` delivered as BGRA: value is documentation-only on this path — SDK delivers BGRA only from Y'CbCr sources with hardware range expansion already applied, so the bytes are always full and the library ignores `input_narrow_range` for byte-level decoding
- `output_narrow_range`: If False (default), output uint8 is full range (0-255, "ready to display"). If True, output is narrow-range R'G'B' (16-235 per channel) — useful when feeding the result to further video processing that expects narrow-range conventions. Note: BGRA-delivered captures cannot preserve sub-blacks (0-15) or super-whites (236-255) on this path; the SDK's hardware range expansion clips them before the library sees the bytes. Use `capture_frame_as_uint16()` or capture as Y'CbCr to retain footroom/headroom. See [BGRA capture and the hardware conversion assumption](#bgra-capture-and-the-hardware-conversion-assumption) under BGRA and Range Behaviour for details.
- Returns: R'G'B' uint8 array (H×W×3), or None if timeout/no signal
- Automatically converts from any DeckLink pixel format to R'G'B'
- Faster than `capture_frame_as_rgb()` due to uint8 output, ideal for preview workflows
- When the capture was initialised with `pixel_format=PixelFormat.BGRA` and the SDK delivers 10-bit R'G'B' (the typical case for 8-bit R'G'B' sources on HDMI), the library automatically right-shifts each channel by 2 to recover the exact 8-bit values before applying any range conversion.

**`capture_frame_as_uint8_with_metadata(timeout_ms=5000, input_narrow_range=None, output_narrow_range=False) -> Optional[dict]`**
Capture a frame as R'G'B' uint8 with format metadata (fast preview with metadata access).
- `timeout_ms`: Timeout in milliseconds (default: 5000)
- `input_narrow_range`: Same per-source-format default semantics as `capture_frame_as_uint8()`. The returned dict's `'input_narrow_range'` field records the **resolved** boolean.
- `output_narrow_range`: If False (default), output uint8 is full range (0-255). If True, output is narrow-range R'G'B' (16-235 per channel). Note: BGRA-delivered captures cannot preserve sub-blacks (0-15) or super-whites (236-255) on this path; the SDK's hardware range expansion clips them before the library sees the bytes. Use `capture_frame_as_uint16_with_metadata()` or capture as Y'CbCr to retain footroom/headroom. See [BGRA capture and the hardware conversion assumption](#bgra-capture-and-the-hardware-conversion-assumption) under BGRA and Range Behaviour for details.
- Returns: Dictionary with frame data and metadata, or None if timeout/no signal

Dictionary keys:
- `'rgb'`: R'G'B' uint8 array (H×W×3)
- `'width'`: Frame width in pixels
- `'height'`: Frame height in pixels
- `'format'`: Pixel format name (e.g., "YUV10", "RGB10")
- `'mode'`: Display mode name (e.g., "HD1080p25")
- `'matrix'`: Y'CbCr matrix name (e.g., "Rec709", "Rec2020")
- `'eotf'`: Transfer function name (e.g., "SDR", "PQ", "HLG")
- `'input_narrow_range'`: Boolean indicating the input range used for conversion
- `'output_narrow_range'`: Boolean indicating the output range applied
- `'hdr_metadata'`: Dictionary with HDR metadata (only present if HDR metadata is in the signal)
  - Same structure as `capture_frame_with_metadata()` below

This function combines the performance of `capture_frame_as_uint8()` with metadata access, making it ideal for real-time preview applications that need to detect signal changes (resolution, matrix, EOTF) without the overhead of float conversion; see [`examples/capture_preview.py`](https://github.com/nick-shaw/blackmagic-io/blob/main/examples/capture_preview.py).

**`capture_frame_as_uint16(timeout_ms=5000, input_narrow_range=None, output_narrow_range=False) -> Optional[np.ndarray]`**
Capture a single frame and convert to R'G'B' uint16 (preserves native bit depth of the source).
- `timeout_ms`: Timeout in milliseconds (default: 5000)
- `input_narrow_range`: Same per-source-format default semantics as `capture_frame_as_uint8()`.
- `output_narrow_range`: If False (default), output uint16 is full range (0-65535 scaled). If True, output is narrow-range R'G'B' in canonical 16-bit form (nominal black 4096, nominal white 60160; 8/10/12-bit narrow codes LSB-padded to 16-bit) with sub-black and super-white preserved if present.
- Returns: R'G'B' uint16 array (H×W×3), or None if timeout/no signal
- Higher-precision counterpart to `capture_frame_as_uint8()`. 10-bit (RGB10 / YUV10) and 12-bit (RGB12) sources keep their native precision in the uint16 result. 8-bit sources (BGRA, or RGB10-delivered-as-BGRA) are LSB-padded via `<< 8` — `0xff` maps to `0xff00`, so the underlying precision is still 8-bit even though the dtype is uint16.

**`capture_frame_as_uint16_with_metadata(timeout_ms=5000, input_narrow_range=None, output_narrow_range=False) -> Optional[dict]`**
Capture a frame as R'G'B' uint16 with format metadata. Higher-precision counterpart to `capture_frame_as_uint8_with_metadata()`; see that method for the per-key dictionary structure (only the `'rgb'` value's dtype changes from uint8 to uint16) and the `input_narrow_range` per-source-format defaults. See `capture_frame_as_uint16()` above for notes on bit-depth handling per source format.

**`capture_frame_as_rgb(timeout_ms=5000, input_narrow_range=None) -> Optional[np.ndarray]`**
Capture a single frame and convert to R'G'B' float.
- `timeout_ms`: Timeout in milliseconds (default: 5000)
- `input_narrow_range`: Same per-source-format default semantics as `capture_frame_as_uint8()`.
- Returns: R'G'B' float32 array (H×W×3) mapped to 0.0-1.0 (nominal black to nominal white per the resolved `input_narrow_range`), or None if timeout/no signal
- Automatically converts from any DeckLink pixel format to R'G'B'
- When the capture was initialised with `pixel_format=PixelFormat.BGRA` and the SDK delivers 10-bit R'G'B' (the typical case for 8-bit R'G'B' sources on HDMI), the library automatically right-shifts each channel by 2 to recover the exact 8-bit values before float conversion. This avoids the small precision error that comes from decoding LSB-padded 8-bit content as if it were native 10-bit.

**`capture_frame_with_metadata(timeout_ms=5000, input_narrow_range=None) -> Optional[dict]`**
Capture a frame with format metadata.
- `timeout_ms`: Timeout in milliseconds (default: 5000)
- `input_narrow_range`: Same per-source-format default semantics as `capture_frame_as_uint8()`. The returned dict's `'input_narrow_range'` field records the **resolved** boolean.
- Returns: Dictionary with frame data and metadata, or None if timeout/no signal
- BGRA-requested handling: same automatic right-shift as `capture_frame_as_rgb()` above.

Dictionary keys:
- `'rgb'`: R'G'B' float32 array (H×W×3), normalised 0.0-1.0
- `'width'`: Frame width in pixels
- `'height'`: Frame height in pixels
- `'format'`: Pixel format name (e.g., "YUV10", "RGB10")
- `'mode'`: Display mode name (e.g., "1080p25")
- `'matrix'`: Y'CbCr matrix name (e.g., "Rec709", "Rec2020")
- `'eotf'`: Transfer function name (e.g., "SDR", "PQ", "HLG")
- `'input_narrow_range'`: Boolean indicating if input was narrow range
- `'hdr_metadata'`: Dictionary with HDR metadata (only present if HDR metadata is in the signal)
  - `'display_primaries'`: Dictionary with display primaries (if present)
    - `'red'`: Dictionary with `'x'` and `'y'` chromaticity coordinates
    - `'green'`: Dictionary with `'x'` and `'y'` chromaticity coordinates
    - `'blue'`: Dictionary with `'x'` and `'y'` chromaticity coordinates
  - `'white_point'`: Dictionary with `'x'` and `'y'` chromaticity coordinates (if present)
  - `'mastering_luminance'`: Dictionary with `'max'` and `'min'` luminance in cd/m² (if present)
  - `'content_light'`: Dictionary with content light levels (if present)
    - `'max_cll'`: Maximum content light level in cd/m² (MaxCLL) (if present)
    - `'max_fall'`: Maximum frame average light level in cd/m² (MaxFALL) (if present)

**`get_detected_format() -> Optional[dict]`**
Get information about the detected input signal.
- Returns: Dictionary with format information, or None if no signal

Dictionary keys:
- `'mode'`: Display mode name
- `'width'`: Frame width in pixels
- `'height'`: Frame height in pixels
- `'framerate'`: Frame rate in fps

**`cleanup()`**
Cleanup resources and stop capture.

**Context Manager Support:**
```python
with BlackmagicInput() as input_device:
    input_device.initialize()
    # ... use input ...
# Automatic cleanup() called on exit
```

The context manager automatically calls `cleanup()` when exiting.

### Low-Level API: DeckLinkOutput Class

Direct C++ API for more fine-grained control.

#### Methods

**`get_device_list() -> List[str]`**
Get list of available DeckLink devices.

**`initialize(device_index=0) -> bool`**
Initialize the specified DeckLink device.

**`get_supported_display_modes() -> List[DisplayModeInfo]`**
Get list of supported display modes for the initialized device.
- Returns: List of DisplayModeInfo objects with display_mode, name, width, height, framerate

**`is_pixel_format_supported(display_mode, pixel_format) -> bool`**
Check if a pixel format is supported for a given display mode.

**`get_video_settings(display_mode) -> VideoSettings`**
Get video settings object for a display mode.

**`set_matrix(matrix: Matrix)`**
Set the Y'CbCr matrix (Rec.601/709/2020) used for Y'CbCr encoding and signalled on the wire (VPID for SDI, AVI InfoFrame for HDMI). Not HDR-specific — every Y'CbCr signal needs a matrix. Also default-fills HDR Static Metadata primaries / white point / mastering luminance from the matrix name (only meaningful for PQ output; the SDK suppresses HDR static metadata for HLG and SDR). Call `set_static_metadata()` afterwards to override the defaults.

**`set_eotf(eotf: Eotf)`**
Set the EOTF (`SDR`, `PQ`, or `HLG`). Setting to non-`SDR` triggers HDR Static Metadata InfoFrame transmission on the next `display_frame()` emission; setting back to `SDR` suppresses it.

**`set_static_metadata(static_metadata: HdrStaticMetadata)`**
Set HDR Static Metadata (per SMPTE ST 2086 / CEA-861.3 Type 1) with explicit display primaries, white point, mastering display luminance, and content light level fields. Overrides the defaults set by `set_matrix()`. Only meaningful for PQ output.

**Changing HDR metadata mid-stream:** Every wire-frame the DeckLink emits carries the metadata from the last committed frame. Video data and metadata (matrix tag, EOTF, HDR static metadata) live in hardware registers / buffers that are updated atomically by `display_frame()`; the output continuously re-emits whatever's currently in them until the next commit. So `set_matrix()` / `set_eotf()` / `set_static_metadata()` stage changes in internal state but don't reach the wire until the next `display_frame()` call. Applies to both SDI and HDMI. The frame contents do not need to change — calling `display_frame()` with the existing buffer commits any pending metadata changes alongside it.

**`setup_output(settings: VideoSettings) -> bool`**
Setup output with detailed settings.

**`set_frame_data(data: np.ndarray) -> bool`**
Set frame data from NumPy array (must be in correct format).

**`display_frame() -> bool`**
Display the current frame synchronously. Call this after `set_frame_data()` to update the display.

**`get_current_output_info() -> OutputInfo`**
Get information about the current output configuration.
- Returns: OutputInfo struct with display_mode_name, pixel_format_name, width, height, framerate, rgb444_mode_enabled

**`stop_output() -> bool`**
Stop video output.
- Returns: True if successful

Stops displaying frames but keeps the device initialized and ready for immediate reuse. After calling `stop_output()`, you can call `setup_output()` and `display_frame()` again without needing to re-initialize.

**`cleanup()`**
Cleanup all resources.

Stops video output (if running) and releases all device resources. After `cleanup()`, the device must be re-initialized with `initialize()` before it can be used again. This method automatically calls `stop_output()` internally, so there is no need to call `stop_output()` first.

### Data Structures

**`VideoSettings`**
```python
class VideoSettings:
    mode: DisplayMode      # Video mode (resolution / framerate)
    format: PixelFormat    # Pixel format
    width: int             # Frame width in pixels
    height: int            # Frame height in pixels
    framerate: float       # Frame rate (e.g., 25.0, 29.97, 60.0)
    matrix: Matrix         # Y'CbCr matrix (Rec601 / Rec709 / Rec2020)
    eotf: Eotf             # Transfer function (SDR / PQ / HLG)
```

**Note:** The Blackmagic SDK uses the term "colorspace" (`BMDColorspace`) for the Y'CbCr matrix tag (Rec.601 / Rec.709 / Rec.2020) signalled on the wire. The gamut (primaries) of the image data is conveyed separately by the SDK as chromaticity coordinates in the HDR static metadata. For clarity, this library uses the term `matrix` since, for example, ARRI LogC3 is normally converted using a Rec.709 matrix, but the data is not "in the Rec.709 colour space".

**`HdrStaticMetadata`**

The fields described in SMPTE ST 2086 (mastering display) and CEA-861.3 (HDR Static Metadata Type 1 InfoFrame: MaxCLL, MaxFALL).

```python
class HdrStaticMetadata:
    # Display primaries (xy chromaticity coordinates)
    display_primaries_red_x: float
    display_primaries_red_y: float
    display_primaries_green_x: float
    display_primaries_green_y: float
    display_primaries_blue_x: float
    display_primaries_blue_y: float
    white_point_x: float
    white_point_y: float

    # Luminance values (nits)
    max_display_mastering_luminance: float
    min_display_mastering_luminance: float
    max_content_light_level: float
    max_frame_average_light_level: float
```

**`OutputInfo`**
```python
class OutputInfo:
    display_mode: DisplayMode         # Current display mode
    pixel_format: PixelFormat         # Current pixel format
    width: int                        # Frame width in pixels
    height: int                       # Frame height in pixels
    framerate: float                  # Frame rate (e.g., 25.0, 29.97, 60.0)
    rgb444_mode_enabled: bool         # Whether R'G'B' 4:4:4 mode is enabled
    display_mode_name: str            # Human-readable display mode name
    pixel_format_name: str            # Human-readable pixel format name
```

**`DisplayModeInfo`**
```python
class DisplayModeInfo:
    display_mode: DisplayMode         # Display mode enum value
    name: str                         # Human-readable mode name
    width: int                        # Frame width in pixels
    height: int                       # Frame height in pixels
    framerate: float                  # Frame rate (e.g., 25.0, 29.97, 60.0)
```

**`DeviceCapabilities`**
```python
class DeviceCapabilities:
    name: str                         # Device name
    supports_input: bool              # True if device can capture video
    supports_output: bool             # True if device can output video
```

Returned by `get_device_capabilities()` to query what a device supports before initializing it.

**`CapturedFrame`**
```python
class CapturedFrame:
    # Frame data
    data: List[uint8]                 # Raw frame data
    width: int                        # Frame width in pixels
    height: int                       # Frame height in pixels
    format: PixelFormat               # Pixel format
    mode: DisplayMode                 # Display mode
    valid: bool                       # Whether frame is valid

    # Format metadata
    matrix: Matrix                    # Y'CbCr matrix (Rec601/Rec709/Rec2020)
    eotf: Eotf                        # Transfer function (SDR/PQ/HLG)
    has_metadata: bool                # Whether metadata is present

    # Timecode (if present)
    has_timecode: bool                # Whether timecode is present
    timecode_hours: int               # Timecode hours (0-23)
    timecode_minutes: int             # Timecode minutes (0-59)
    timecode_seconds: int             # Timecode seconds (0-59)
    timecode_frames: int              # Timecode frames (frame number within second)
    timecode_is_drop_frame: bool      # True for drop frame timecode

    # HDR metadata (if present)
    display_primaries_red_x: float
    display_primaries_red_y: float
    display_primaries_green_x: float
    display_primaries_green_y: float
    display_primaries_blue_x: float
    display_primaries_blue_y: float
    has_display_primaries: bool

    white_point_x: float
    white_point_y: float
    has_white_point: bool

    max_display_mastering_luminance: float
    min_display_mastering_luminance: float
    has_mastering_luminance: bool

    max_content_light_level: float
    has_max_cll: bool

    max_frame_average_light_level: float
    has_max_fall: bool
```

Used by the low-level `DeckLinkInput.capture_frame()` method. Contains raw frame data plus all detected metadata including timecode and HDR information.

### Low-Level API: DeckLinkInput Class

Direct C++ API for more fine-grained control over video capture.

#### Methods

**`get_device_list() -> List[str]`**
Get list of available DeckLink devices.

**`get_available_input_connections(device_index=0) -> List[InputConnection]`**
Get available input connections for a DeckLink device.
- `device_index`: Index of device to query (default: 0)
- Returns: List of InputConnection enum values

**`initialize(device_index=0, input_connection=None) -> bool`**
Initialize the specified DeckLink device for input.
- `device_index`: Index of device to use (default: 0)
- `input_connection`: Optional InputConnection enum to select specific input. If None, uses device's current input.
- Returns: True if successful

**`start_capture(format=PixelFormat.Format10BitYUV) -> bool`**
Start capturing with specified or auto-detected format.
- `format`: Optional PixelFormat to request from hardware (default: Format10BitYUV)
- Returns: True if successful

Use `PixelFormat.Format8BitBGRA` for preview workflows where 8-bit precision is acceptable. This avoids expensive colorspace conversions and enables real-time capture (achievable frame rate is system-dependent).

**`capture_frame(frame, timeout_ms=5000) -> bool`**
Capture a single frame.
- `frame`: CapturedFrame object to populate
- `timeout_ms`: Timeout in milliseconds (default: 5000)
- Returns: True if successful

**`stop_capture() -> bool`**
Stop video capture.
- Returns: True if successful

**`get_detected_format() -> VideoSettings`**
Get the detected video format.
- Returns: VideoSettings object with format information

**`get_detected_pixel_format() -> PixelFormat`**
Get the detected pixel format.
- Returns: PixelFormat enum value

**`get_video_settings(mode) -> VideoSettings`**
Get video settings for a display mode.

**`get_supported_display_modes() -> List[DisplayModeInfo]`**
Get list of supported display modes for the initialized device.

**`set_hdmi_input_dynamic_ranges(dynamic_range_mask: int) -> bool`**
Set the BMDDynamicRange bitmask advertised in the HDMI input EDID. Sources read this to decide which transfer functions they may transmit. Pass any combination of BMDDynamicRange bits as a single int — values are passed through to the SDK so newer SDKs adding additional bits work without library changes.
- `dynamic_range_mask`: Bitwise OR of `bmdDynamicRangeSDR` (0), `bmdDynamicRangeHDRStaticPQ` (1 << 29), and/or `bmdDynamicRangeHDRStaticHLG` (1 << 30)
- Returns: True if the mask was stored or applied successfully

The library defaults to advertising `SDR | HDR Static PQ | HDR Static HLG`. The SDK default omits HLG, which causes many HDMI sources to strip HDR Static Metadata when transmitting HLG; the library's default fixes that. May be called before or after `initialize()`. Has no effect on non-HDMI connections or on hardware that does not expose `IDeckLinkHDMIInputEDID` (older devices) — these cases soft-fail and capture proceeds normally. The library releases its EDID interface in `cleanup()`, which restores the default EDID per the SDK.

**`cleanup()`**
Cleanup and release resources.

### Utility Functions

**`rgb_to_bgra(rgb_array, width, height) -> np.ndarray`**
Convert RGB to BGRA format.
- `rgb_array`: NumPy array (H×W×3), dtype uint8
- This function is a pure byte-reorder + alpha-padding (R'G'B' → BGRA layout). It does no range conversion; the input bytes are passed through to the output bytes unchanged. Range handling for the BGRA path is done at the wrapper layer (`display_static_frame(output_narrow_range=...)` for output; `capture_frame_as_uint8(output_narrow_range=...)` for capture).
- Returns: BGRA array (H×W×4), dtype uint8

**`rgb_uint8_to_yuv8(rgb_array, width, height, matrix=Matrix.Rec709, input_narrow_range=False, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' uint8 to 8-bit Y'CbCr (2vuy) format.
- `rgb_array`: NumPy array (H×W×3), dtype uint8 (0-255 range)
- `matrix`: R'G'B' to Y'CbCr conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the `rgb_array` as narrow range (16-235). Default: False
- `output_narrow_range`: Whether to encode the Y'CbCr as narrow range (Y: 16-235, CbCr: 16-240; clamped to [0, 255], so super-blacks/super-whites are preserved). Default: True
- Returns: Packed 2vuy array

**`rgb_uint16_to_yuv8(rgb_array, width, height, matrix=Matrix.Rec709, input_narrow_range=False, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' uint16 to 8-bit Y'CbCr (2vuy) format.
- `rgb_array`: NumPy array (H×W×3), dtype uint16 (0-65535 range)
- `matrix`: R'G'B' to Y'CbCr conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the `rgb_array` as narrow range. Default: False
- `output_narrow_range`: Whether to encode the Y'CbCr as narrow range (Y: 16-235, CbCr: 16-240; clamped to [0, 255], so super-blacks/super-whites are preserved). Default: True
- Returns: Packed 2vuy array

**`rgb_float_to_yuv8(rgb_array, width, height, matrix=Matrix.Rec709, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' float to 8-bit Y'CbCr (2vuy) format.
- `rgb_array`: NumPy array (H×W×3), dtype float32 (0.0-1.0 range)
- `matrix`: R'G'B' to Y'CbCr conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `output_narrow_range`: Whether to encode the Y'CbCr as narrow range (Y: 16-235, CbCr: 16-240; clamped to [0, 255], so super-blacks/super-whites are preserved). Default: True
- Returns: Packed 2vuy array

**`rgb_uint16_to_yuv10(rgb_array, width, height, matrix=Matrix.Rec709, input_narrow_range=False, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' uint16 to 10-bit Y'CbCr (v210) format.
- `rgb_array`: NumPy array (H×W×3), dtype uint16 (0-65535 range)
- `matrix`: R'G'B' to Y'CbCr conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the `rgb_array` as narrow range. Default: False
- `output_narrow_range`: Whether to encode the Y'CbCr as narrow range. Default: True
- Returns: Packed v210 array

**`rgb_float_to_yuv10(rgb_array, width, height, matrix=Matrix.Rec709, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' float to 10-bit Y'CbCr (v210) format.
- `rgb_array`: NumPy array (H×W×3), dtype float32 (0.0-1.0 range)
- `matrix`: R'G'B' to Y'CbCr conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `output_narrow_range`: Whether to encode the Y'CbCr as narrow range. Default: True
- Returns: Packed v210 array

**`rgb_uint16_to_rgb10(rgb_array, width, height, input_narrow_range=True, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' uint16 to 10-bit R'G'B' (bmdFormat10BitRGBXLE) format.
- `rgb_array`: NumPy array (H×W×3), dtype uint16 (0-65535 range)
- `input_narrow_range`: Whether to interpret the `rgb_array` as narrow range. Default: True
- `output_narrow_range`: Whether to output narrow range. Default: True
- Returns: Packed 10-bit R'G'B' array

**`rgb_float_to_rgb10(rgb_array, width, height, output_narrow_range=True) -> np.ndarray`**
Convert R'G'B' float to 10-bit R'G'B' (bmdFormat10BitRGBXLE) format.
- `rgb_array`: NumPy array (H×W×3), dtype float32 (0.0-1.0 range)
- `output_narrow_range`: Whether to output narrow range. Default: True
- Returns: Packed 10-bit R'G'B' array

**`rgb_uint16_to_rgb12(rgb_array, width, height, input_narrow_range=False, output_narrow_range=False) -> np.ndarray`**
Convert R'G'B' uint16 to 12-bit R'G'B' (bmdFormat12BitRGBLE) format.
- `rgb_array`: NumPy array (H×W×3), dtype uint16 (0-65535 range)
- `input_narrow_range`: Whether to interpret the `rgb_array` as narrow range. Default: False
- `output_narrow_range`: Whether to output narrow range. Default: False
- Returns: Packed 12-bit R'G'B' array

**`rgb_float_to_rgb12(rgb_array, width, height, output_narrow_range=False) -> np.ndarray`**
Convert R'G'B' float to 12-bit R'G'B' (bmdFormat12BitRGBLE) format.
- `rgb_array`: NumPy array (H×W×3), dtype float32 (0.0-1.0 range)
- `output_narrow_range`: Whether to output narrow range. Default: False
- Returns: Packed 12-bit R'G'B' array

**`yuv10_to_rgb_uint16(yuv_array, width, height, matrix=Matrix.Rec709, input_narrow_range=True, output_narrow_range=False, row_bytes=None) -> np.ndarray`**
Convert 10-bit Y'CbCr (v210) format to R'G'B' uint16.
- `yuv_array`: NumPy array containing packed v210 data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `matrix`: Y'CbCr to R'G'B' conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the Y'CbCr as narrow range. Default: True
- `output_narrow_range`: Whether to encode the uint16 R'G'B' output as narrow range (4096-60160 @ 16-bit). Default: False
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `((width + 47) // 48) * 128` (the v210-native stride).
- Returns: NumPy array (H×W×3), dtype uint16 (0-65535 range)

**`yuv10_to_rgb_float(yuv_array, width, height, matrix=Matrix.Rec709, input_narrow_range=True, row_bytes=None) -> np.ndarray`**
Convert 10-bit Y'CbCr (v210) format to R'G'B' float.
- `yuv_array`: NumPy array containing packed v210 data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `matrix`: Y'CbCr to R'G'B' conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the Y'CbCr as narrow range. Default: True
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `((width + 47) // 48) * 128` (the v210-native stride).
- Returns: NumPy array (H×W×3), dtype float32, normalised 0.0-1.0

**`yuv8_to_rgb_uint16(yuv_array, width, height, matrix=Matrix.Rec709, input_narrow_range=True, output_narrow_range=False, row_bytes=None) -> np.ndarray`**
Convert 8-bit Y'CbCr (2vuy) format to R'G'B' uint16.
- `yuv_array`: NumPy array containing packed 2vuy data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `matrix`: Y'CbCr to R'G'B' conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the Y'CbCr as narrow range (Y: 16-235, CbCr: 16-240). Default: True
- `output_narrow_range`: Whether to encode the uint16 R'G'B' output as narrow range (4096-60160 @ 16-bit). Default: False
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `width * 2`.
- Returns: NumPy array (H×W×3), dtype uint16 (0-65535 range)

**`yuv8_to_rgb_float(yuv_array, width, height, matrix=Matrix.Rec709, input_narrow_range=True, row_bytes=None) -> np.ndarray`**
Convert 8-bit Y'CbCr (2vuy) format to R'G'B' float.
- `yuv_array`: NumPy array containing packed 2vuy data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `matrix`: Y'CbCr to R'G'B' conversion matrix (Matrix.Rec601, Matrix.Rec709 or Matrix.Rec2020). Default: Matrix.Rec709
- `input_narrow_range`: Whether to interpret the Y'CbCr as narrow range (Y: 16-235, CbCr: 16-240). Default: True
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `width * 2`.
- Returns: NumPy array (H×W×3), dtype float32, normalised 0.0-1.0

**`rgb10_to_uint16(rgb_array, width, height, input_narrow_range=True, output_narrow_range=False, row_bytes=None) -> np.ndarray`**
Convert 10-bit R'G'B' (bmdFormat10BitRGBXLE) format to R'G'B' uint16.
- `rgb_array`: NumPy array containing packed 10-bit R'G'B' data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `input_narrow_range`: Whether to interpret the 10-bit R'G'B' as narrow range. Default: True
- `output_narrow_range`: Whether to output narrow range. Default: False
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `width * 4`.
- Returns: NumPy array (H×W×3), dtype uint16 (0-65535 range)

**`rgb10_to_float(rgb_array, width, height, input_narrow_range=True, row_bytes=None) -> np.ndarray`**
Convert 10-bit R'G'B' (bmdFormat10BitRGBXLE) format to R'G'B' float.
- `rgb_array`: NumPy array containing packed 10-bit R'G'B' data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `input_narrow_range`: Whether to interpret the 10-bit R'G'B' as narrow range. Default: True
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `width * 4`.
- Returns: NumPy array (H×W×3), dtype float32, normalised 0.0-1.0

**`rgb12_to_uint16(rgb_array, width, height, input_narrow_range=False, output_narrow_range=False, row_bytes=None) -> np.ndarray`**
Convert 12-bit R'G'B' (bmdFormat12BitRGBLE) format to R'G'B' uint16.
- `rgb_array`: NumPy array containing packed 12-bit R'G'B' data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `input_narrow_range`: Whether to interpret the 12-bit R'G'B' as narrow range. Default: False
- `output_narrow_range`: Whether to output narrow range. Default: False
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `((width + 7) // 8) * 36` (the R12L-native stride).
- Returns: NumPy array (H×W×3), dtype uint16 (0-65535 range)

**`rgb12_to_float(rgb_array, width, height, input_narrow_range=False, row_bytes=None) -> np.ndarray`**
Convert 12-bit R'G'B' (bmdFormat12BitRGBLE) format to R'G'B' float.
- `rgb_array`: NumPy array containing packed 12-bit R'G'B' data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `input_narrow_range`: Whether to interpret the 12-bit R'G'B' as narrow range. Default: False
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `((width + 7) // 8) * 36` (the R12L-native stride).
- Returns: NumPy array (H×W×3), dtype float32, normalised 0.0-1.0

**`unpack_v210(v210_array, width, height, row_bytes=None) -> dict`**
Unpack 10-bit Y'CbCr (v210) format to Y', Cb, Cr component arrays.
- `v210_array`: NumPy array containing packed v210 data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `((width + 47) // 48) * 128` (the v210-native stride).
- Returns: Dictionary with `'y'`, `'cb'`, `'cr'` keys, each containing an H×W NumPy array, dtype uint16 (0-1023 range, 10-bit values)

**`unpack_2vuy(yuv_array, width, height, row_bytes=None) -> dict`**
Unpack 8-bit Y'CbCr (2vuy) format to Y', Cb, Cr component arrays.
- `yuv_array`: NumPy array containing packed 2vuy data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `width * 2`.
- Returns: Dictionary with `'y'`, `'cb'`, `'cr'` keys, each containing an H×W NumPy array, dtype uint8

**`unpack_rgb10(rgb_array, width, height, row_bytes=None) -> dict`**
Unpack 10-bit R'G'B' (bmdFormat10BitRGBXLE) format to R', G', B' component arrays.
- `rgb_array`: NumPy array containing packed 10-bit R'G'B' data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `width * 4`.
- Returns: Dictionary with `'r'`, `'g'`, `'b'` keys, each containing an H×W NumPy array, dtype uint16 (0-1023 range, 10-bit values)

**`unpack_rgb12(rgb_array, width, height, row_bytes=None) -> dict`**
Unpack 12-bit R'G'B' (bmdFormat12BitRGBLE) format to R', G', B' component arrays.
- `rgb_array`: NumPy array containing packed 12-bit R'G'B' data
- `width`: Frame width in pixels
- `height`: Frame height in pixels
- `row_bytes`: Bytes per row in the source buffer. Pass `captured_frame.row_bytes` for captured frames whose stride may include padding. If None, defaults to `((width + 7) // 8) * 36` (the R12L-native stride).
- Returns: Dictionary with `'r'`, `'g'`, `'b'` keys, each containing an H×W NumPy array, dtype uint16 (0-4095 range, 12-bit values)

### Enums

**`DisplayMode`**

The library supports all display modes available on your DeckLink device. Display mode settings (resolution, frame rate) are queried dynamically from the hardware. Common examples include:
- `HD1080p25`: 1920×1080 @ 25fps
- `HD1080p30`: 1920×1080 @ 30fps
- `HD1080p50`: 1920×1080 @ 50fps
- `HD1080p60`: 1920×1080 @ 60fps
- `HD720p50`: 1280×720 @ 50fps
- `HD720p60`: 1280×720 @ 60fps

Additional modes are available including SD (NTSC, PAL), 2K, 4K, 8K, and PC display modes. The complete list of DisplayMode values can be found in `src/blackmagic_io/blackmagic_io.py`.

**Querying Available Display Modes:**

You can query which display modes are supported by your specific DeckLink device using `get_supported_display_modes()`:

```python
from blackmagic_io import BlackmagicOutput

with BlackmagicOutput() as output:
    output.initialize()

    # Get all supported display modes
    modes = output.get_supported_display_modes()
    print(f"Device supports {len(modes)} display modes:\n")
    for mode in modes:
        print(f"{mode['name']}: {mode['width']}x{mode['height']} @ {mode['framerate']:.2f} fps")
```

To determine which pixel formats are supported for a specific display mode, use `is_pixel_format_supported()`:

```python
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat

with BlackmagicOutput() as output:
    output.initialize()

    # Test pixel format support for a specific mode
    print("Pixel formats supported for HD1080p25:")
    test_formats = [PixelFormat.YUV10, PixelFormat.RGB10, PixelFormat.RGB12]
    for fmt in test_formats:
        supported = output.is_pixel_format_supported(DisplayMode.HD1080p25, fmt)
        print(f"{fmt.name}: {'supported' if supported else 'not supported'}")
```

**`PixelFormat`**
- `BGRA`: 8-bit BGRA (automatically used for uint8 data)
  - uint8 input: Configurable interpretation via `input_narrow_range` parameter (narrow input is expanded to full-range BGRA before packing; sub-blacks and super-whites are clipped at the 0-255 boundary)
  - `output_narrow_range` is ignored (a `UserWarning` is issued if explicitly passed). The SDK's hardware conversion produces transport-asymmetric output: narrow Y'CbCr 4:2:2 on the SDI wire and full R'G'B' 4:4:4 on the HDMI wire, regardless of buffer contents. For controlled output range, use `YUV10` / `RGB10` / `RGB12`. See [BGRA output is transport-asymmetric on the wire](#bgra-output-is-transport-asymmetric-on-the-wire) under BGRA and Range Behaviour for details.
- `YUV8`: 8-bit Y'CbCr 4:2:2 (2vuy) - direct 8-bit Y'CbCr output
  - uint8 input: Configurable interpretation via `input_narrow_range` parameter
  - uint16 input: Configurable interpretation via `input_narrow_range` parameter
  - float input: Always interpreted as full range (0.0-1.0)
  - Output range configurable via `output_narrow_range` parameter
  - Defaults: `input_narrow_range=False, output_narrow_range=True`
  - More efficient than BGRA for 8-bit Y'CbCr workflows (avoids hardware conversion)
- `YUV10`: 10-bit Y'CbCr 4:2:2 (v210) - default for uint16 / float data
  - Defaults to narrow range: Y: 64-940, UV: 64-960. Supports full range Y'CbCr (0-1023, as per [Rec. ITU-T H.273](https://www.itu.int/rec/T-REC-H.273)) if `output_narrow_range` is False in the high level API
- `RGB10`: 10-bit R'G'B' (bmdFormat10BitRGBXLE) - native R'G'B' output without Y'CbCr conversion
  - uint16 input: Configurable interpretation via `input_narrow_range` parameter
  - float input: Always interpreted as full range (0.0-1.0)
  - Output range configurable via `output_narrow_range` parameter
  - Defaults: `input_narrow_range=True, output_narrow_range=True`
- `RGB12`: 12-bit R'G'B' (bmdFormat12BitRGBLE) - native R'G'B' output with 12-bit precision
  - uint16 input: Configurable interpretation via `input_narrow_range` parameter
  - float input: Always interpreted as full range (0.0-1.0)
  - Output range configurable via `output_narrow_range` parameter
  - Defaults: `input_narrow_range=False, output_narrow_range=False`

### Range Signalling Limitations

**Important:** While this library supports both narrow and full range output encoding via the `output_narrow_range` parameter, the Blackmagic DeckLink SDK (v14.1) does not provide APIs to control the bit-depth / range field in the VPID — a 2-bit field per SMPTE ST 425-1:2017 (Table 5, byte 4, bits 1:0).

- **YUV10**: The library can encode full range Y'CbCr (0-1023) with `output_narrow_range=False`, but cannot set the full range flag in the VPID. Downstream devices may well assume narrow range.

- **RGB10**: The convention is that 10-bit R'G'B' is narrow range, as described in the Blackmagic SDK documentation, so using `output_narrow_range=False` may cause downstream devices to misinterpret the signal.

- **RGB12**: The convention is that 12-bit R'G'B' is full range, as described in the Blackmagic SDK documentation, so using `output_narrow_range=True` may cause downstream devices to misinterpret the signal.

The `output_narrow_range` parameter controls the **actual encoded values** in the output stream, not metadata signalling. Use it when you know the downstream device will correctly interpret the range, or when the receiving device allows manual range configuration.

#### SDI Protected Code Values (SDI only)

Independent of the range-signalling question above, SDI 10-bit reserves code values 0-3 and 1020-1023 for sync words (per SMPTE ST 425-1), so the permitted active-video range on the SDI wire is 4-1019. If you drive an SDI output with the canonical full-range extents — for example float `1.0` → wire code 1023 — the SDI hardware clamps the wire to 1019 (and 0 to 4) before transmission.

This is a property of the SDI link itself, not the library. **HDMI is unaffected**: the HDMI (TMDS / FRL) transport carries sync information in separate periods rather than reserved code values, so the full active codespace (0-1023 for 10-bit, 0-4095 for 12-bit) is preserved end-to-end for R'G'B' formats (Y'CbCr mirrors the SDI clipping). Verified empirically by `tests/test_hdmi_full_range_round_trip.py`: full white over HDMI round-trips bit-exact to captured uint16 65535. If you need the full extents preserved on the wire, use HDMI; if you use SDI, expect the wire-level clamp.

**SDI Full:** Because `output_narrow_range=False` passes values through unscaled and the SDI hardware clamps codes outside 4-1019 at the wire, an "SDI Full" signal can be produced by pre-scaling your data so its extents land inside the active-video range — e.g. mapping `[0.0, 1.0]` to `[4/1023, 1019/1023]` for 10-bit (or the equivalent for 12-bit) and then outputting with `output_narrow_range=False`.

**`Matrix`**
The Y'CbCr matrix — the coefficient set used for R'G'B' ↔ Y'CbCr conversion, and signalled on the wire (VPID for SDI, AVI InfoFrame for HDMI). Not HDR-specific: every Y'CbCr signal needs a matrix.
- `Rec601`: ITU-R BT.601 (SD)
- `Rec709`: ITU-R BT.709 (standard HD)
- `Rec2020`: ITU-R BT.2020 (UHD / HDR)

**`Gamut`**
The HDR static-metadata colorimetry-bundle identifier — display primaries and white point conveyed via the HDR Static Metadata InfoFrame. Only meaningful for PQ output on tested hardware; the SDK zeroes the InfoFrame for HLG and SDR.
- `Rec709`: BT.709 primaries + D65 white point
- `Rec2020`: BT.2020 primaries + D65 white point

Best practice for real HDR delivery is to call `set_static_metadata()` with explicit primaries (e.g. P3-D65 inside a Rec.2020 container) rather than relying on the matrix-name defaults that `set_matrix()` fills.

**`Eotf`**
- `SDR`: Standard Dynamic Range (BT.1886 transfer function)
- `PQ`: Perceptual Quantizer (SMPTE ST 2084, HDR10)
- `HLG`: Hybrid Log-Gamma (HDR broadcast standard)

**`InputConnection`**

Physical input connections available on DeckLink devices. Use `get_available_input_connections()` to query which inputs are available on a specific device.

- `SDI`: SDI input (Serial Digital Interface)
- `HDMI`: HDMI input
- `OpticalSDI`: Optical SDI input
- `Component`: Component video input (Y, Pb, Pr)
- `Composite`: Composite video input (CVBS)
- `SVideo`: S-Video input (Y/C)

**Example:**
```python
from blackmagic_io import BlackmagicInput, InputConnection

with BlackmagicInput() as input_device:
    # Query available inputs
    inputs = input_device.get_available_input_connections(0)
    print(f"Available inputs: {[str(inp) for inp in inputs]}")

    # Initialize with HDMI input
    if InputConnection.HDMI in inputs:
        input_device.initialize(0, InputConnection.HDMI)
    else:
        # Use default input
        input_device.initialize(0)

    # Capture frame
    rgb = input_device.capture_frame_as_rgb()
```

## Examples

### Example 1: Colour Bars Test Pattern

```python
from blackmagic_io import BlackmagicOutput, DisplayMode, create_test_pattern

# Create colour bars test pattern
frame = create_test_pattern(1920, 1080, 'bars')

with BlackmagicOutput() as output:
    output.initialize()  # Optional - auto-initializes on first display if omitted
    output.display_static_frame(frame, DisplayMode.HD1080p25)
    input("Press Enter to stop...")
```

### Example 2: Dynamic Animation

```python
import numpy as np
import time
from blackmagic_io import BlackmagicOutput, DisplayMode

with BlackmagicOutput() as output:
    # Start with black frame
    frame = np.zeros((1080, 1920, 3), dtype=np.float32)
    output.display_static_frame(frame, DisplayMode.HD1080p25)

    # Animate
    for i in range(100):
        # Create moving pattern
        frame.fill(0.0)
        offset = i * 10
        frame[:, offset:offset+100] = [1.0, 1.0, 1.0]  # White bar

        output.update_frame(frame)
        time.sleep(1 / 25)  # Limit update rate (actual rate will be lower due to processing overhead)
```

### Example 3: Load Image from File

```python
import imageio.v3 as iio
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode

# Load image (preserves bit depth for 16-bit TIFFs, etc.)
# Note: Use TIFF for reliable 16-bit support (PNGs may convert to 8-bit)
frame = iio.imread('your_image.tif')

# Resize if needed
if frame.shape[0] != 1080 or frame.shape[1] != 1920:
    from PIL import Image
    img = Image.fromarray(frame)
    img = img.resize((1920, 1080), Image.Resampling.LANCZOS)
    frame = np.array(img)

# Remove alpha channel if present
if frame.shape[2] == 4:
    frame = frame[:, :, :3]

# Display image (format auto-detected from dtype)
with BlackmagicOutput() as output:
    output.display_static_frame(frame, DisplayMode.HD1080p25)
    input("Press Enter to stop...")
```

### Example 4: 10-bit Y'CbCr Output from Float Data

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode

# Create float R'G'B' image (0.0-1.0 range)
frame = np.zeros((1080, 1920, 3), dtype=np.float32)

# Example: gradient in float space
for y in range(1080):
    for x in range(1920):
        frame[y, x] = [
            x / 1920,           # Red gradient
            y / 1080,           # Green gradient
            0.5                 # Blue constant
        ]

# Output as 10-bit Y'CbCr (automatically selected for float data)
with BlackmagicOutput() as output:
    output.display_static_frame(frame, DisplayMode.HD1080p25)
    input("Press Enter to stop...")
```

### Example 5: 10-bit Y'CbCr from uint16 Data

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode

# Create uint16 R'G'B' image (0-65535 range)
# Useful for 10-bit / 12-bit / 16-bit image processing pipelines
frame = np.zeros((1080, 1920, 3), dtype=np.uint16)

# Full range gradient
for x in range(1920):
    frame[:, x, 0] = int(x / 1920 * 65535)  # Red gradient

# Output as 10-bit Y'CbCr (automatically selected for uint16 data)
with BlackmagicOutput() as output:
    output.display_static_frame(frame, DisplayMode.HD1080p25)
    input("Press Enter to stop...")
```

### Example 5a: 10-bit R'G'B' from uint16 Data

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat

# Create uint16 R'G'B' image (0-65535 range)
frame = np.zeros((1080, 1920, 3), dtype=np.uint16)

# Full range gradient
for x in range(1920):
    frame[:, x, 0] = int(x / 1920 * 65535)  # Red gradient

# Output as 10-bit R'G'B' (bit-shifted from 16-bit to 10-bit)
with BlackmagicOutput() as output:
    output.display_static_frame(frame, DisplayMode.HD1080p25, PixelFormat.RGB10)
    input("Press Enter to stop...")
```

### Example 5b: 10-bit R'G'B' (Narrow Range) from Float Data

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat

# Create float R'G'B' image (0.0-1.0 range)
frame = np.zeros((1080, 1920, 3), dtype=np.float32)

# Gradient
for x in range(1920):
    frame[:, x, 0] = x / 1920  # Red gradient

# Output as 10-bit R'G'B' with narrow range (0.0-1.0 maps to 64-940)
with BlackmagicOutput() as output:
    output.display_static_frame(
        frame,
        DisplayMode.HD1080p25,
        PixelFormat.RGB10,
        output_narrow_range=True  # Default: narrow range
    )
    input("Press Enter to stop...")
```

### Example 5c: 10-bit R'G'B' (Full Range) from Float Data

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat

# Create float R'G'B' image (0.0-1.0 range)
frame = np.zeros((1080, 1920, 3), dtype=np.float32)

# Gradient
for x in range(1920):
    frame[:, x, 0] = x / 1920  # Red gradient

# Output as 10-bit R'G'B' with full range (0.0-1.0 maps to 0-1023)
with BlackmagicOutput() as output:
    output.display_static_frame(
        frame,
        DisplayMode.HD1080p25,
        PixelFormat.RGB10,
        output_narrow_range=False  # Full range
    )
    input("Press Enter to stop...")
```

### Example 6: 8-bit BGRA Output

For simple applications or quick testing, 8-bit R'G'B' data can be used directly without conversion to float or uint16. Note that 8-bit data is always treated as full range R'G'B' input and output as narrow range 8-bit Y'CbCr 4:2:2 over SDI.

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode

# Create 8-bit R'G'B' image (0-255 range, full range)
frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

# Simple gradient
for x in range(1920):
    frame[:, x, 0] = int(255 * x / 1920)  # Red gradient

# Output as 8-bit (BGRA format automatically selected for uint8 data)
with BlackmagicOutput() as output:
    output.display_static_frame(frame, DisplayMode.HD1080p25)
    input("Press Enter to stop...")
```

### Example 7: HDR Output with Rec.2020 and HLG (Simplified API)

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode, Matrix, Eotf

# Create HDR content in normalised float (0.0-1.0 range)
frame = np.zeros((1080, 1920, 3), dtype=np.float32)

# Example: HDR gradient with extended range
for y in range(1080):
    for x in range(1920):
        frame[y, x] = [
            x / 1920,           # Red gradient
            y / 1080,           # Green gradient
            0.5                 # Blue constant
        ]

# Configure for HLG HDR output using the simplified API
with BlackmagicOutput() as output:
    # Single call with matrix and HDR metadata
    # YUV10 automatically selected for float data
    output.display_static_frame(
        frame,
        DisplayMode.HD1080p25,
        matrix=Matrix.Rec2020,           # Use Rec.2020 matrix
        hdr_metadata={'eotf': Eotf.HLG}  # HLG with default metadata
    )

    input("Press Enter to stop...")
```

**Alternative: Low-level API for more control**

```python
import numpy as np
import decklink_io as dl

# Create HDR content
frame = np.zeros((1080, 1920, 3), dtype=np.float32)
# ... fill frame ...

# Configure for HLG HDR output using low-level API
output = dl.DeckLinkOutput()
output.initialize()

# Set signal metadata BEFORE setup_output()
output.set_matrix(dl.Matrix.Rec2020)
output.set_eotf(dl.Eotf.HLG)

# Setup output
settings = output.get_video_settings(dl.DisplayMode.HD1080p25)
settings.format = dl.PixelFormat.YUV10
output.setup_output(settings)

# Convert R'G'B' to Y'CbCr using Rec.2020 matrix
yuv_data = dl.rgb_float_to_yuv10(frame, 1920, 1080, dl.Matrix.Rec2020)
output.set_frame_data(yuv_data)

# Display the frame
output.display_frame()
input("Press Enter to stop...")
output.stop_output()
output.cleanup()
```

### Example 8: HDR10 (PQ) Output (Simplified API)

```python
import numpy as np
from blackmagic_io import BlackmagicOutput, DisplayMode, Matrix, Eotf

# Create HDR10 content with PQ transfer function applied
frame = np.zeros((1080, 1920, 3), dtype=np.float32)

# Fill with PQ-encoded HDR content
# A library such as Colour Science for Python (https://www.colour-science.org/) is needed for PQ encoding
# frame = colour.eotf(linear_rgb_data, 'ST 2084')

# Configure for HDR10 (PQ) output using the simplified API
with BlackmagicOutput() as output:
    # Single call with Rec.2020 matrix and PQ metadata
    # YUV10 automatically selected for float data
    output.display_static_frame(
        frame,
        DisplayMode.HD1080p25,
        matrix=Matrix.Rec2020,
        hdr_metadata={'eotf': Eotf.PQ}
    )

    input("Press Enter to stop...")
```

**Alternative: Low-level API**

```python
import numpy as np
import decklink_io as dl

# Create HDR10 content
frame = np.zeros((1080, 1920, 3), dtype=np.float32)
# ... fill frame ...

# Configure for HDR10 (PQ) output
output = dl.DeckLinkOutput()
output.initialize()

# IMPORTANT: Set signal metadata BEFORE setup_output()
# set_matrix() also default-fills Rec.2020 primaries / D65 / mastering luminance
# in the HDR Static Metadata InfoFrame for PQ output.
output.set_matrix(dl.Matrix.Rec2020)
output.set_eotf(dl.Eotf.PQ)

# Setup output settings
settings = output.get_video_settings(dl.DisplayMode.HD1080p25)
settings.format = dl.PixelFormat.YUV10
output.setup_output(settings)

# Convert to Y'CbCr with Rec.2020 matrix
yuv_data = dl.rgb_float_to_yuv10(frame, 1920, 1080, dl.Matrix.Rec2020)
output.set_frame_data(yuv_data)

# Display the frame
output.display_frame()
input("Press Enter to stop...")
output.stop_output()
output.cleanup()
```

### Example 9: Colour Patches for Testing and Calibration

The `display_solid_color()` method supports displaying color patches smaller than full screen, useful for testing, calibration, and creating custom test patterns.

```python
import time
from blackmagic_io import BlackmagicOutput, DisplayMode

with BlackmagicOutput() as output:
    # Full screen white (default behaviour)
    output.display_solid_color((1.0, 1.0, 1.0), DisplayMode.HD1080p25)
    time.sleep(2)

    # Centred 50% white patch on black background
    output.display_solid_color(
        (1.0, 1.0, 1.0),
        DisplayMode.HD1080p25,
        patch=(0.5, 0.5, 0.5, 0.5)  # (center_x, center_y, width, height)
    )
    time.sleep(2)

    # Small centred white patch (10% size) on gray background
    output.display_solid_color(
        (1.0, 1.0, 1.0),
        DisplayMode.HD1080p25,
        patch=(0.5, 0.5, 0.1, 0.1),
        background_color=(0.5, 0.5, 0.5)
    )
    time.sleep(2)

    # Red patch in top-left quadrant on blue background
    output.display_solid_color(
        (1.0, 0.0, 0.0),
        DisplayMode.HD1080p25,
        patch=(0.25, 0.25, 0.3, 0.3),
        background_color=(0.0, 0.0, 1.0)
    )
    time.sleep(2)

    # Horizontal bar across center (full width, half height)
    # Using integer 10-bit values with narrow range
    output.display_solid_color(
        (940, 940, 64),
        DisplayMode.HD1080p25,
        patch=(0.5, 0.5, 1.0, 0.5),
        background_color=(400, 400, 400),
        input_narrow_range=True
    )
    time.sleep(2)
```

**Patch coordinates:**
- All values are normalized (0.0-1.0) for resolution independence
- `center_x, center_y`: Position of patch center (0.0 = left/top, 1.0 = right/bottom)
- `width, height`: Patch dimensions as fraction of screen (1.0 = full width/height)
- Example: `(0.5, 0.5, 0.25, 0.25)` = centred patch, 25% of screen size

**Background colour:**
- Uses same format as foreground `color` (integers 0-1023 or floats 0.0-1.0)
- Defaults to black if not specified
- For integer colors with `input_narrow_range=True`, black defaults to 64 instead of 0

## HDR Metadata

The library exposes per-field signal-metadata setters: `set_matrix()` (Y'CbCr matrix), `set_eotf()` (EOTF identifier), `set_static_metadata()` (display primaries, white point, mastering display luminance, MaxCLL, MaxFALL). Once any has been called, the library wraps every emitted frame via the DeckLink SDK's `IDeckLinkVideoFrameMetadataExtensions` interface. The matrix tag and EOTF identifier reach the wire for any EOTF (in VPID on SDI, the AVI InfoFrame on HDMI); the HDR Static Metadata InfoFrame fields are transmitted only for PQ — HLG is SDK-suppressed (see Important Notes point 8 below), SDR has no HDR InfoFrame.

### Metadata Includes:

- **Display Primaries**: Independent of the Y'CbCr matrix. When not provided explicitly via `set_static_metadata()` (low-level) or the `'static_metadata'` key of `hdr_metadata` (high-level), `set_matrix()` default-fills primaries from the matrix name as a convenience — see Default HDR Metadata Values below.
- **White Point**: D65 (0.3127, 0.3290) default-fill (unless explicitly specified).
- **EOTF**: Electro-Optical Transfer Function (`Eotf.SDR`, `Eotf.PQ`, or `Eotf.HLG`).
- **Mastering Display Info**: Default-filled max / min luminance; override via `set_static_metadata()`.
- **Content Light Levels**: MaxCLL and MaxFALL; default-filled, override via `set_static_metadata()`.

### Default HDR Metadata Values (PQ only — SDK suppresses for SDR and HLG):

`set_matrix()` populates the HDR Static Metadata struct from the matrix name as a convenience for callers who don't supply explicit static metadata. **This is a default-fill, not a conceptual coupling between matrix and primaries.** For real HDR delivery the mastering display's primaries are typically different from the Y'CbCr matrix (P3-D65 primaries inside a Rec.2020 container is the common case — no mastering display has actual BT.2020 primaries). Override the defaults via `set_static_metadata()` or the `'static_metadata'` key in the `hdr_metadata` dict.

The default-fill rule:

- `Matrix.Rec2020` → BT.2020 primaries: R(0.708, 0.292), G(0.170, 0.797), B(0.131, 0.046)
- `Matrix.Rec601` or `Matrix.Rec709` → BT.709 primaries: R(0.64, 0.33), G(0.30, 0.60), B(0.15, 0.06)

In all cases: white point D65 (0.3127, 0.3290), max mastering luminance 1000 nits, min 0.0001 nits, MaxCLL 1000 nits, MaxFALL 50 nits.

### Customizing HDR Metadata Values:

**High-level API:**

```python
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat, Matrix, Eotf, HdrStaticMetadata

# Build HDR Static Metadata for the source's mastering display
static_metadata = HdrStaticMetadata()
static_metadata.display_primaries_red_x = 0.708
static_metadata.display_primaries_red_y = 0.292
# ... set other values ...
static_metadata.max_display_mastering_luminance = 1000.0
static_metadata.min_display_mastering_luminance = 0.0001

# Use in simplified API
with BlackmagicOutput() as output:
    output.initialize()
    output.display_static_frame(
        frame,
        DisplayMode.HD1080p25,
        pixel_format=PixelFormat.YUV10,
        matrix=Matrix.Rec2020,
        hdr_metadata={'eotf': Eotf.PQ, 'static_metadata': static_metadata}
    )
    input("Press Enter to stop...")
```

**Low-level API:**

For precise control over HDR Static Metadata with the low-level API, use `set_static_metadata()` after `set_matrix()` and `set_eotf()`:

```python
import decklink_io as dl

# Build HDR Static Metadata for the mastering display
static_metadata = dl.HdrStaticMetadata()

# Display primaries (chromaticity coordinates)
static_metadata.display_primaries_red_x = 0.708
static_metadata.display_primaries_red_y = 0.292
static_metadata.display_primaries_green_x = 0.170
static_metadata.display_primaries_green_y = 0.797
static_metadata.display_primaries_blue_x = 0.131
static_metadata.display_primaries_blue_y = 0.046
static_metadata.white_point_x = 0.3127
static_metadata.white_point_y = 0.3290

# Mastering display luminance
static_metadata.max_display_mastering_luminance = 4000.0      # 4000 nits peak (e.g., for HDR10+ content)
static_metadata.min_display_mastering_luminance = 0.0005      # 0.0005 nits black level

# Content light levels
static_metadata.max_content_light_level = 2000.0     # 2000 nits max content (MaxCLL)
static_metadata.max_frame_average_light_level = 400.0 # 400 nits average (MaxFALL)

output = dl.DeckLinkOutput()
output.initialize()
output.set_matrix(dl.Matrix.Rec2020)
output.set_eotf(dl.Eotf.PQ)
output.set_static_metadata(static_metadata)
```

### Available HDR Metadata Fields:

All 14 SMPTE ST 2086 / CEA-861.3 HDR static metadata fields are supported:

**Display Primaries (xy chromaticity coordinates):**
- `display_primaries_red_x`, `display_primaries_red_y`
- `display_primaries_green_x`, `display_primaries_green_y`
- `display_primaries_blue_x`, `display_primaries_blue_y`
- `white_point_x`, `white_point_y`

**Mastering Display Luminance:**
- `max_display_mastering_luminance` (nits) - Peak luminance of mastering display
- `min_display_mastering_luminance` (nits) - Minimum luminance of mastering display

**Content Light Levels:**
- `max_content_light_level` (nits) - Maximum luminance of any pixel (MaxCLL)
- `max_frame_average_light_level` (nits) - Maximum average luminance of any frame (MaxFALL)

### Important Notes:

1. **Simplified API**: With `display_static_frame()`, HDR metadata and matrix are set in a single call
2. **Low-level API call order**: When using the low-level API, the setters affect the metadata used by the next `display_frame()` emission. See the "Changing HDR metadata mid-stream" callout below for the snapshot mechanism.
3. **Frame-level metadata**: Metadata is embedded in every video frame, not set globally
4. **Matrix consistency**: When using the simplified API, the same `matrix` parameter is used for both signalled-matrix metadata and R'G'B' → Y'CbCr conversion. With the low-level API, ensure consistency between `set_matrix()` and the conversion functions you call.
5. **Transfer function**: The library only sets the metadata - you must apply the actual transfer function (PQ / HLG curve) to your R'G'B' data before conversion
6. **All 14 metadata fields supported**: The library implements all SMPTE ST 2086 / CEA-861.3 HDR metadata fields including display primaries, white point, mastering display luminance, and content light levels
7. **Matrix / Resolution restrictions**:
   - **Rec.601** is only supported for SD display modes (NTSC, PAL, etc.) and is the only matrix supported for SD
   - **Rec.709** and **Rec.2020** are only supported for HD and higher resolutions (720p, 1080p, 2K, 4K, 8K, etc.)
8. **HLG static metadata is suppressed on transmit by the Blackmagic SDK**: When EOTF is HLG, the SDK transmits zero values for all HDR static metadata fields (display primaries, white point, mastering display luminance, MaxCLL, MaxFALL) over HDMI, even when populated explicitly via `set_static_metadata()`. This applies to anything built on the Blackmagic SDK, not just this library — confirmed by Blackmagic-to-Blackmagic loopback. The receive side reads non-zero HLG static metadata faithfully when present in an incoming signal (primaries, white point, mastering display luminance all arrive intact), so the suppression is transmit-side, not receive-side. SDI conveys HDR static metadata via SMPTE ST 2108 ANC packets (separate from VPID, which carries only EOTF and matrix) for PQ. For HLG on SDI, the SDK does not transmit ST 2108 packets, so no HDR static metadata reaches the receiver — only EOTF and matrix come through. The transmit-side suppression is consistent with the view that HLG does not require mastering display information at the receiver, but stricter than CTA-861.3 permits.

## BGRA and Range Behaviour

This section documents observed SDK behaviour around the BGRA path and per-source-format range defaults. Items here apply to both SDI and HDMI on tested hardware. HDMI-specific behaviour is covered in the next section.

### BGRA capture and the hardware conversion assumption

When capturing with `pixel_format=PixelFormat.BGRA`, the SDK on tested hardware delivers actual BGRA frames only when the source is Y'CbCr — performing the matrix conversion **and** range expansion in hardware, yielding full-range 8-bit BGRA. (8-bit R'G'B' sources are delivered as 10-bit R'G'B' with LSB padding; see "8-bit R'G'B' sources arrive as 10-bit R'G'B' with LSB padding" under HDMI Notes for how the library handles that case.) The library therefore treats BGRA-delivered bytes as full range and applies any `input_narrow_range`-related conversion accordingly (`input_narrow_range` describes the wire signal, not the bytes the library receives). This matches observed behaviour on tested hardware but isn't a documented SDK guarantee; if a future driver or hardware delivered narrow-range BGRA from a Y'CbCr source, output from `capture_frame_as_uint8` / `capture_frame_as_rgb` would be incorrectly ranged.

**Caveat — full-range Y'CbCr sources: behaviour unverified.** The SDK's hardware Y'CbCr → BGRA conversion has been observed to assume narrow range (64-940 luma in 10-bit mapped to 0-255 BGRA) with the conventional broadcast Y'CbCr sources we tested. Whether the SDK reads the HDMI AVI InfoFrame's YCC Quantization Range (YQ) field and handles correctly-flagged full-range Y'CbCr sources (e.g. computer GPU output configured for Y'CbCr-Full, certain pattern generators) differently is untested and unknown at this time. If YQ is ignored, full-range Y'CbCr values outside 64-940 would be clipped in hardware (0-63 → 0, 941-1023 → 255) before the library sees the frame; no software-side `input_narrow_range=False` could recover those values. To be safe with potentially full-range Y'CbCr sources, capture as `PixelFormat.YUV10` or `PixelFormat.YUV8` instead of `PixelFormat.BGRA` and convert with `input_narrow_range=False` at the library level — that path preserves the original code values regardless of how the hardware interprets YQ.

**Caveat — narrow-range sub-blacks and super-whites are lost in BGRA.** Narrow-range Y'CbCr legitimately carries codes below 64 (sub-blacks, footroom) and above 940 (super-whites, headroom). The SDK's narrow-assumed Y'CbCr → BGRA conversion clips these to 0 or 255 at the BGRA output. If you then request `output_narrow_range=True` to recover an 8-bit R'G'B' representation, the nominal 16-235 range round-trips faithfully but the sub-black region (codes 0-15) and super-white region (236-255) will be empty — that signal was lost in hardware. Less serious than the full-range case (nominal content is preserved), but if you need to retain footroom/headroom information, capture as `PixelFormat.YUV10` or `PixelFormat.YUV8` and convert in software.

### Y'CbCr → BGRA hardware conversion honours signalled matrix metadata

When capturing as BGRA from a Y'CbCr source, the SDK's hardware Y'CbCr → R'G'B' conversion uses the matrix coefficients (Rec.601, Rec.709, or Rec.2020) signalled in the source's frame metadata. Verified via SDI and HDMI loopback with Rec.709 and Rec.2020 sources. Applications working with BGRA captures don't need to apply their own matrix conversion.

### BGRA output is transport-asymmetric on the wire

Symmetric with the capture-side behaviour above. On output, the SDK fans a single BGRA buffer out to SDI and HDMI with *different* range characteristics on the two transports:

- **SDI**: the SDK hardware-converts the BGRA buffer to **narrow-range Y'CbCr 4:2:2** for the wire, treating the buffer as full-range R'G'B' for the matrix math. The SDI wire is always narrow Y'CbCr when output via BGRA, regardless of buffer contents.
- **HDMI**: the SDK transmits the BGRA buffer as **R'G'B' 4:4:4** on the wire. Buffer values pass through to the wire (verified by the 256-value ramp test in `tests/test_hdmi_bgra_loopback.py`).

Because the same buffer produces different wire ranges on the two transports, there is no single BGRA buffer composition that is correct for both SDI and HDMI for arbitrary range combinations. The library therefore:

- **Honours `input_narrow_range`**: narrow-range input bytes are expanded to full-range R'G'B' via `_adjust_range_uint8` before BGRA packing, mirroring the capture-side range handling.
- **Ignores `output_narrow_range`**: a `UserWarning` is issued if the parameter is explicitly passed. There is no buffer-level interpretation that produces correct wire output on both transports.

Sub-blacks (codes 0-15) and super-whites (codes 236-255) in narrow-range input are clipped at the narrow → full expansion stage (BGRA's 0-255 range cannot represent them); this matches the symmetric capture-side caveat above.

For controlled output range — including narrow-range R'G'B' on HDMI — use `PixelFormat.YUV10` / `PixelFormat.RGB10` / `PixelFormat.RGB12` instead. These are higher-precision formats with transport-uniform range control.

If you need narrow-range 8-bit R'G'B' on HDMI (a niche workflow), the workaround is to "lie" about the input range: pass narrow-range bytes (already 16-235) with `input_narrow_range=False`. The library treats them as already-full and packs them unchanged; HDMI then transmits them as narrow R'G'B'. SDI receives doubly-narrowed Y'CbCr in that case — the cost of the lie.

### Capture-side `input_narrow_range` defaults are per-source-format

Symmetric with the output-side `output_narrow_range` per-format defaults documented above. From 0.18.0b1 the high-level capture API uses `input_narrow_range: Optional[bool] = None`, resolved at runtime after the source pixel format is known:

- `YUV8` / `YUV10`: True (narrow Y'CbCr — broadcast convention).
- `RGB10`: True (Blackmagic 10-bit R'G'B' is conventionally narrow per the SDK).
- `RGB12`: False (Blackmagic 12-bit R'G'B' is conventionally full per the SDK).
- BGRA requested but delivered as RGB10 (the 8-bit R'G'B' HDMI source path): **False**. The SDK transmits the library's own BGRA output as full-range R'G'B' on HDMI (see "BGRA output is transport-asymmetric on the wire" above), and 8-bit R'G'B' on HDMI is conventionally a full-range "computer signal" — the DVI-D heritage the SDK appears to honour in both directions. Capturing one symmetric to producing one means assuming full range. This intentionally diverges from the sibling 10-bit RGB10 default (which keeps narrow) — the source bit-depth is the discriminator: 8-bit-via-RGB10-padding is full, native 10-bit RGB10 is narrow.
- BGRA delivered as BGRA: documentation-only. The SDK delivers BGRA from Y'CbCr sources only, having already applied hardware range expansion. The bytes the library receives are always full-range, so `input_narrow_range` doesn't gate byte-level decoding on this path; it describes the wire signal upstream of the SDK's conversion.

The structural difference from the output side: on output, the caller picks `pixel_format` at the API boundary so the per-format default applies immediately; on capture, the source format is detected from the wire, so resolution happens inside `_convert_frame_to_int` / `_convert_frame_to_rgb` after format detection. The `_with_metadata` capture variants record the **resolved** boolean in the returned dict's `'input_narrow_range'` field, so callers can see what was actually applied.

If the caller knows the wire signal's range and it differs from the per-format default (e.g. narrow-range RGB12 from a niche source, or full-range Y'CbCr from a GPU), pass `input_narrow_range` explicitly — the resolved default only kicks in when the argument is omitted or `None`.

## HDMI Notes

This section documents HDMI-specific behaviour observed on tested hardware (DeckLink UltraStudio 4K Mini), both input and output. Transport-agnostic SDK behaviour (BGRA path, range defaults, HDR static metadata) is in the preceding sections.

### EDID is partially controllable

The permutations of EDID negotiation between source and sink mean there is always some degree of uncertainty with HDMI capture; you should test your own setup to confirm behaviour.

The DeckLink HDMI input advertises an EDID to source devices. The library writes the dynamic-range advertisement to enable SDR + HDR PQ + HLG (the SDK default omits HLG). Other EDID parameters are not exposed through the SDK and are therefore not available in this library.

### Format detection at cold start

Connect your source before starting capture for reliable format detection. The SDK's wire-format auto-detection runs cleanly at the start of a capture session and identifies the input as Y'CbCr or R'G'B' based on the source's HDMI signalling.

### Some mid-stream source switches are not detected

Most wire-format changes during an active capture — Y'CbCr ↔ R'G'B' transitions within the HDMI signalling protocol — are detected correctly by the SDK and the capture format updates accordingly.

The exception is the HDMI ↔ DVI **protocol** switching exposed in the AJA Control Panel for AJA devices. On tested hardware the HDMI → DVI direction is not reliably detected — the SDK continues to interpret incoming bytes in the previous format until capture is restarted. The reverse direction (DVI → HDMI) is detected correctly. If you switch source protocol mid-capture, stop and restart capture.

### 8-bit R'G'B' sources arrive as 10-bit R'G'B' with LSB padding

Sources sending 8-bit R'G'B' over HDMI (DVI computer signals, AJA devices configured for DVI output in the AJA Control Panel, etc.) arrive as 10-bit R'G'B' with the source's 8-bit values in the high 8 bits and zero LSBs. No information is lost; this is a faithful representation.

The maximum reachable 10-bit value from an 8-bit source is 1020 (= 255 × 4), not 1023. Naively treating LSB-padded 8-bit content as native 10-bit (dividing by 1023) gives values systematically ~0.3% lower than the equivalent 8-bit code divided by 255 — at every non-zero point, not just at peak. `(x<<2)/1023 ≠ x/255` for any `x` except zero; the two denominators are just incompatible.

When the user requests `pixel_format=PixelFormat.BGRA` at `start_capture`, the library handles this automatically: each channel is right-shifted by 2 before float conversion (÷ 255) or uint8 extraction, so `capture_frame_as_rgb` and `capture_frame_as_uint8` recover the exact 0.0–1.0 (or 0–255) mapping for content originating from 8-bit.

### RGB range signalling on transmit (AVI InfoFrame Q)

The Blackmagic SDK does not expose the HDMI AVI InfoFrame's RGB Quantization Range (Q) field for control.

Empirical observation on an LG OLED: with HDMI Black Level set to Auto, the displayed result matched the manual Limited setting across RGB10 and RGB12. The Full setting produced a different result. This suggests that the Q field may be fixed to signalling **Limited** (narrow) range.

## Troubleshooting

### Common Issues

**"DeckLink output module not found"**
- Build and install the C++ extension: `pip install -e .`
- Check that pybind11 is installed: `pip install pybind11`

**"Could not create DeckLink iterator"**
- Install Blackmagic Desktop Video software
- Ensure DeckLink device is connected and recognized by the system
- Check device drivers are properly installed

**"Could not find DeckLink device"**
- Verify device is connected and powered
- Check device appears in Blackmagic software (Media Express, etc.)
- Try different device index: `output.initialize(device_index=1)`

**Build errors about missing headers**
- The SDK headers are included in the repository under `_vendor/decklink_sdk/`
- If you need to use a different SDK version, update the paths in `CMakeLists.txt`
- On Linux, ensure headers are accessible to the build system

**Permission errors (Linux)**
- Add user to appropriate groups: `sudo usermod -a -G video $USER`
- Log out and back in for group changes to take effect

**HDR output not displaying correctly**
- **Simplified API**: Pass both `matrix` and `hdr_metadata` (specifying the EOTF) to `display_static_frame()`
- **Low-level API**: Call `set_matrix()` / `set_eotf()` / `set_static_metadata()` before the `display_frame()` call you want them to take effect from — metadata is snapshotted at frame-emission time and embedded in each emitted frame.
- Ensure matrix consistency: same value in both metadata and R'G'B' → Y'CbCr conversion

### Testing Your Installation

Run the example script to test your installation:

```bash
python examples/example_usage.py
```

This will show available devices and let you test various output modes.

## Tools

### pixel_reader

The `pixel_reader` tool captures and analyses video input from a DeckLink device, displaying pixel values and metadata. This is useful for verifying output from the library by looping a DeckLink output back to its own input.

**Build:** `pixel_reader` is built automatically as part of `pip install -e .` (or any wheel install) via the main `CMakeLists.txt`. The executable lands at `tools/pixel_reader` (or `tools/pixel_reader.exe` on Windows), ready to run alongside the Python module.

**Usage:**
```bash
tools/pixel_reader [device_index]
```
See `tools/README.md` for more detail.

The tool displays:
- **Pixel format** and **colour space** (R'G'B' 4:4:4, Y'CbCr 4:2:2, etc.)
- **Resolution** and **frame rate**
- **Metadata**: EOTF (SDR / PQ / HLG), matrix (Rec.601 / Rec.709 / Rec.2020)
- **Pixel values** at selected coordinates in native format (code values)

Use this tool to verify that matrix and EOTF metadata are being set correctly by the output library.

## Platform-Specific Notes

### Windows
- Requires Visual Studio Build Tools or Visual Studio with C++ support
- DeckLink SDK typically installs to Program Files

### macOS  
- Requires Xcode Command Line Tools
- May need to codesign the built extension for some versions

### Linux
- Requires build-essential package
- May need to configure udev rules for device access
- Some distributions require additional video group membership

## Running the Tests

The test suite lives in `tests/` and is run with pytest:

```bash
pytest tests/                          # everything (skips hardware tests if no DeckLink)
pytest tests/ -m "not hardware"        # non-hardware tests only (math, byte layouts, etc.)
pytest tests/ -m "hardware"            # hardware loopback tests only
pytest tests/ -m "hardware and sdi"       # SDI signal-path tests only
pytest tests/ -m "hardware and hdmi"      # HDMI signal-path tests only
pytest tests/ -m "hardware and not hdmi"  # SDI + transport-agnostic hardware tests (device enumeration, resolutions); excludes HDMI
pytest tests/ -m "hardware and not loopback"  # detection / enumeration / initialisation only — for output-only devices or no-loopback setups
```

The non-hardware tests run anywhere — they exercise the C++ conversion functions, byte ordering, range helpers, and similar pure-software paths. CI runs these on every push across macOS, Linux, and Windows.

The hardware loopback tests require:

- A DeckLink device (any model) with Blackmagic Desktop Video installed.
- An **SDI BNC cable** looped from `SDI OUT` → `SDI IN`, for the SDI-marked tests.
- An **HDMI cable** looped from `HDMI OUT` → `HDMI IN`, for the HDMI-marked tests.

Each hardware test file is marked with `sdi` or `hdmi` so the suite can be filtered to match the cards/cables available — useful for cards that don't have both transports, or for partial-loopback rigs. `test_hdr_metadata_loopback.py` parametrises over both transports, with per-parametrise marks, so the HDMI half and SDI half can be selected independently via the same `-m` filter. Without the required cable a hardware test will time out waiting for a capture, so it's worth confirming the right cables are in place — or filtering with `-m` — before invoking the full suite.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

### Blackmagic DeckLink SDK License

This repository includes header files from the Blackmagic DeckLink SDK v14.1. These header files are redistributable under the terms of the Blackmagic DeckLink SDK End User License Agreement (Section 0.1), which specifically exempts the Include folder headers from the more restrictive licensing terms that apply to other parts of the SDK.

**Important notes about the SDK headers:**
- The header files in `_vendor/decklink_sdk/{Mac,Win,Linux}/include/` directories are from the Blackmagic DeckLink SDK
- These headers are required only for **building** the library from source
- **Runtime usage requires** the Blackmagic Desktop Video software to be installed separately
- The SDK headers are provided under Blackmagic Design's EULA - see `_vendor/Blackmagic Design EULA.pdf` for full terms
- Download the complete SDK and Desktop Video software from: https://www.blackmagicdesign.com/developer

The Blackmagic DeckLink SDK is © Blackmagic Design Pty. Ltd. All rights reserved.

## Support

- Check the [Issues](https://github.com/nick-shaw/blackmagic-io/issues) page for known problems
- Review Blackmagic's official DeckLink SDK documentation
- Ensure your DeckLink device is supported by the SDK version

## Acknowledgments

- Blackmagic Design for the DeckLink SDK
- pybind11 project for the C++/Python bindings
- Contributors and testers
- Special thanks to [Zach Lewis](https://github.com/zachlewis) and [Gino Bollaert](https://github.com/yergin)