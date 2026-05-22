# Pixel Reader for Blackmagic DeckLink Devices

This tool reads the incoming signal on a Blackmagic DeckLink device and displays:
- The detected pixel format (including bit depth and color space)
- The code values at specified pixel coordinates
- Metadata (EOTF and matrix) when present

## Features

- **Automatic Format Detection**: Detects all supported YUV and RGB formats
- **Supported Formats**:
  - 8-bit YUV (4:2:2)
  - 10-bit YUV (4:2:2)
  - 10-bit YUVA (4:4:4:4)
  - 8-bit RGB (4:4:4)
  - 10-bit RGB (4:4:4)
  - 12-bit RGB (4:4:4)
- **Metadata Display**: Shows EOTF (SDR/PQ/HLG) and matrix (Rec.601/709/2020) when present
- **Real-time Display**: Continuously updates as frames arrive

## Building

`pixel_reader` is built automatically as part of the main library build. From the repository root:

```bash
pip install -e .
```

This runs the project's CMake build, which produces both the Python module and `pixel_reader` as a side effect. The executable lands at `tools/pixel_reader` (or `tools/pixel_reader.exe` on Windows). The same toolchain that compiles the library compiles the tool — no separate installation needed.

For an incremental rebuild without re-running the full pip install, invoke CMake directly against the existing build directory:

```bash
cmake --build build/<py-tag> --target pixel_reader
```

Substitute `<py-tag>` with whichever build directory scikit-build-core created (e.g. `cp313-cp313-macosx_13_0_arm64`, `cp314-cp314-win_amd64`).

## Usage

```bash
./pixel_reader [options] [x] [y]
```

### Options

- `-d <index>`: Select DeckLink device by index (see `-l` for device list). Default: first device with input capability
- `-i <input>`: Select input connection (sdi, hdmi, optical, component, composite, svideo). Default: uses currently active input on the device
- `--mode <name>`: Force a specific display mode and disable input format auto-detection. Required on cards that don't claim `BMDDeckLinkSupportsInputFormatDetection` (e.g. older DeckLinks). Supported names: NTSC, PAL, 720p50, 720p59.94, 720p60, 1080i50, 1080i59.94, 1080p25, 1080p29.97, 1080p30, 1080p50, 1080p59.94, 1080p60
- `-m`: Print all HDR metadata (display primaries, white point, mastering display luminance, content light levels) in addition to the matrix and EOTF
- `-l`: List all available DeckLink devices with their input capabilities and available inputs
- `-h`: Show help message

### Arguments

- `x`: X coordinate of pixel to read (default: 960)
- `y`: Y coordinate of pixel to read (default: 540)

### Examples

```bash
# List available devices
./pixel_reader -l

# Use first device with input capability (default), read pixel at (100, 100)
./pixel_reader 100 100

# Select device 1, use default position (960, 540)
./pixel_reader -d 1

# Select device 0, read pixel at position (100, 100)
./pixel_reader -d 0 100 100

# Use HDMI input
./pixel_reader -i hdmi

# Use device 0, SDI input, read pixel at (100, 200)
./pixel_reader -d 0 -i sdi 100 200

# Force 1080i50 mode (disables auto-detection; required on older cards)
./pixel_reader -i sdi --mode 1080i50

# Print full HDR metadata when present
./pixel_reader -m

# Show help
./pixel_reader -h
```

## Output

The tool displays:
1. **Format Detection**: When the input signal is detected or changes, it shows:
   - Signal format (YCbCr422, RGB444)
   - Bit depth (8-bit, 10-bit, 12-bit)

2. **Pixel Values**: Continuously updated pixel values at the specified coordinates
   - For YUV: Shows Y'CbCr values
   - For RGB: Shows R'G'B' values

3. **Metadata** (when present):
   - Matrix: Rec.601, Rec.709, or Rec.2020
   - EOTF: SDR, PQ, or HLG

### Example Output

```
Input display mode: 1080p50
Input signal detected:
  Signal format: RGB444
  Bit depth: 10-bit

R'G'B' (960, 540) = [940, 512, 64]
Matrix: Rec.709 | EOTF: SDR
```

## Technical Details

### Buffer Format Implementation

The tool uses little-endian buffer formats by default for easier unpacking:
- **8-bit YUV**: 2vuy (UYVY) format
- **10-bit YUV**: v210 format
- **10-bit YUVA**: Ay10 format
- **8-bit RGB**: ARGB/BGRA formats
- **10-bit RGB**: R10l (little-endian RGBX) format
- **12-bit RGB**: R12L (little-endian) format

Note: The buffer format variants (little/big-endian, different packing) are SDK implementation details, not signal format differences.

### Limitations

- By default, requires a DeckLink device that claims `BMDDeckLinkSupportsInputFormatDetection`. Older cards without this capability can still be used by passing `--mode <name>` to specify the input mode explicitly.
- Coordinates must be within the input frame dimensions

## Platform Support

- macOS (tested)
- Linux (untested, but should work)
- Windows (tested; built via MSVC + Windows SDK, same toolchain as the main library)

## Dependencies

- Blackmagic DeckLink SDK 14.1 (vendored under `_vendor/decklink_sdk/`)
- C++17 compatible compiler (MSVC for Windows, Clang or GCC for macOS / Linux)
- Platform-specific libraries (CoreFoundation on macOS, pthread/dl on Linux, ole32/oleaut32/comsuppw on Windows)

## License

Based on Blackmagic Design DeckLink SDK samples. This tool uses the DeckLink SDK which is subject to the Blackmagic Design End User License Agreement (see `Blackmagic Design EULA.pdf` in the repository root). The tool code itself is available under the license in the repository LICENSE file.
