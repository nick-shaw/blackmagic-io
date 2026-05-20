#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include "decklink_output.hpp"
#include "decklink_input.hpp"

// Windows doesn't have ssize_t, but pybind11/numpy uses it for strides
#ifdef _WIN32
    #include <BaseTsd.h>
    typedef SSIZE_T ssize_t;
#endif

namespace py = pybind11;

std::pair<const uint8_t*, size_t> numpy_to_raw(py::array_t<uint8_t> input) {
    py::buffer_info buf_info = input.request();
    return std::make_pair(static_cast<const uint8_t*>(buf_info.ptr), buf_info.size);
}

py::array_t<uint8_t> rgb_to_bgra(py::array_t<uint8_t> rgb_array, int width, int height) {
    auto buf = rgb_array.request();
    
    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }
    
    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }
    
    auto result = py::array_t<uint8_t>({height, width, 4});
    auto res_buf = result.request();
    
    const uint8_t* src = static_cast<const uint8_t*>(buf.ptr);
    uint8_t* dst = static_cast<uint8_t*>(res_buf.ptr);
    
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int src_idx = y * width * 3 + x * 3;
            int dst_idx = y * width * 4 + x * 4;
            
            // Convert RGB to BGRA
            dst[dst_idx + 0] = src[src_idx + 2];  // B
            dst[dst_idx + 1] = src[src_idx + 1];  // G
            dst[dst_idx + 2] = src[src_idx + 0];  // R
            dst[dst_idx + 3] = 255;               // A
        }
    }
    
    return result;
}

py::array_t<uint8_t> rgb_uint16_to_yuv10(py::array_t<uint16_t> rgb_array, int width, int height, DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709, bool input_narrow_range = false, bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // v210 format: 6 pixels packed into 4 32-bit words (16 bytes)
    int row_bytes = ((width + 5) / 6) * 16;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint32_t* dst = static_cast<uint32_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x += 6) {
            uint16_t y_values[6], u_values[3], v_values[3];
            double cb_temp[6], cr_temp[6];   // chroma in -1..+1

            // Convert RGB to YCbCr for up to 6 pixels
            for (int i = 0; i < 6; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const uint16_t* pixel = reinterpret_cast<const uint16_t*>(
                        src_base + y * stride_y + pixel_x * stride_x);
                    uint16_t r = pixel[0];
                    uint16_t g = pixel[1];
                    uint16_t b = pixel[2];

                    double rf, gf, bf;
                    if (input_narrow_range) {
                        rf = (r - (64 << 6)) / (double)(876 << 6);
                        gf = (g - (64 << 6)) / (double)(876 << 6);
                        bf = (b - (64 << 6)) / (double)(876 << 6);
                    } else {
                        rf = r / 65535.0;
                        gf = g / 65535.0;
                        bf = b / 65535.0;
                    }

                    // RGB -> YCbCr ((1-Kr) form, chroma in -1..+1)
                    double yf  = Kr * rf + Kg * gf + Kb * bf;
                    double cbf = (bf - yf) / (1.0 - Kb);
                    double crf = (rf - yf) / (1.0 - Kr);

                    int y10;
                    if (output_narrow_range) {
                        y10 = (int)(yf * 876.0 + 64.0 + 0.5);
                    } else {
                        y10 = (int)(yf * 1023.0 + 0.5);
                    }
                    y_values[i] = (uint16_t)(y10 < 0 ? 0 : (y10 > 1023 ? 1023 : y10));
                    cb_temp[i] = cbf;
                    cr_temp[i] = crf;
                } else {
                    y_values[i] = output_narrow_range ? 64 : 0;
                    cb_temp[i] = 0.0;
                    cr_temp[i] = 0.0;
                }
            }

            // Average pairs of Cb/Cr samples for 4:2:2 chroma subsampling
            for (int i = 0; i < 3; i++) {
                double cb_avg = (cb_temp[i*2] + cb_temp[i*2+1]) * 0.5;
                double cr_avg = (cr_temp[i*2] + cr_temp[i*2+1]) * 0.5;
                int cb10, cr10;
                if (output_narrow_range) {
                    cb10 = (int)(cb_avg * 448.0 + 512.0 + 0.5);
                    cr10 = (int)(cr_avg * 448.0 + 512.0 + 0.5);
                } else {
                    cb10 = (int)(cb_avg * 1023.0 / 2.0 + 512.0 + 0.5);
                    cr10 = (int)(cr_avg * 1023.0 / 2.0 + 512.0 + 0.5);
                }
                u_values[i] = (uint16_t)(cb10 < 0 ? 0 : (cb10 > 1023 ? 1023 : cb10));
                v_values[i] = (uint16_t)(cr10 < 0 ? 0 : (cr10 > 1023 ? 1023 : cr10));
            }

            // Pack into v210 format
            // v210 is little-endian with component order: Cb Y Cr (U Y V)
            // Each DWORD: comp0[9:0] comp1[9:0] comp2[9:0] xx[1:0]
            // Written in little-endian byte order
            int dst_idx = (y * row_bytes / 4) + ((x / 6) * 4);
            dst[dst_idx + 0] = (u_values[0] << 0) | (y_values[0] << 10) | (v_values[0] << 20);
            dst[dst_idx + 1] = (y_values[1] << 0) | (u_values[1] << 10) | (y_values[2] << 20);
            dst[dst_idx + 2] = (v_values[1] << 0) | (y_values[3] << 10) | (u_values[2] << 20);
            dst[dst_idx + 3] = (y_values[4] << 0) | (v_values[2] << 10) | (y_values[5] << 20);
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_float_to_yuv10(py::array_t<float> rgb_array, int width, int height, DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709, bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // v210 format: 6 pixels packed into 4 32-bit words (16 bytes)
    int row_bytes = ((width + 5) / 6) * 16;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint32_t* dst = static_cast<uint32_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x += 6) {
            uint16_t y_values[6], u_values[3], v_values[3];
            double cb_temp[6], cr_temp[6];   // chroma in -1..+1

            // Convert RGB to YCbCr for up to 6 pixels
            for (int i = 0; i < 6; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const float* pixel = reinterpret_cast<const float*>(
                        src_base + y * stride_y + pixel_x * stride_x);
                    double rf = pixel[0];
                    double gf = pixel[1];
                    double bf = pixel[2];

                    // RGB -> YCbCr ((1-Kr) form, chroma in -1..+1)
                    double yf  = Kr * rf + Kg * gf + Kb * bf;
                    double cbf = (bf - yf) / (1.0 - Kb);
                    double crf = (rf - yf) / (1.0 - Kr);

                    int y10;
                    if (output_narrow_range) {
                        y10 = (int)(yf * 876.0 + 64.0 + 0.5);
                    } else {
                        y10 = (int)(yf * 1023.0 + 0.5);
                    }
                    y_values[i] = (uint16_t)(y10 < 0 ? 0 : (y10 > 1023 ? 1023 : y10));
                    cb_temp[i] = cbf;
                    cr_temp[i] = crf;
                } else {
                    y_values[i] = output_narrow_range ? 64 : 0;
                    cb_temp[i] = 0.0;
                    cr_temp[i] = 0.0;
                }
            }

            // Average pairs of Cb/Cr samples for 4:2:2 chroma subsampling
            for (int i = 0; i < 3; i++) {
                double cb_avg = (cb_temp[i*2] + cb_temp[i*2+1]) * 0.5;
                double cr_avg = (cr_temp[i*2] + cr_temp[i*2+1]) * 0.5;
                int cb10, cr10;
                if (output_narrow_range) {
                    cb10 = (int)(cb_avg * 448.0 + 512.0 + 0.5);
                    cr10 = (int)(cr_avg * 448.0 + 512.0 + 0.5);
                } else {
                    cb10 = (int)(cb_avg * 1023.0 / 2.0 + 512.0 + 0.5);
                    cr10 = (int)(cr_avg * 1023.0 / 2.0 + 512.0 + 0.5);
                }
                u_values[i] = (uint16_t)(cb10 < 0 ? 0 : (cb10 > 1023 ? 1023 : cb10));
                v_values[i] = (uint16_t)(cr10 < 0 ? 0 : (cr10 > 1023 ? 1023 : cr10));
            }

            // Pack into v210 format
            // v210 is little-endian with component order: Cb Y Cr (U Y V)
            // Each DWORD: comp0[9:0] comp1[9:0] comp2[9:0] xx[1:0]
            // Written in little-endian byte order
            int dst_idx = (y * row_bytes / 4) + ((x / 6) * 4);
            dst[dst_idx + 0] = (u_values[0] << 0) | (y_values[0] << 10) | (v_values[0] << 20);
            dst[dst_idx + 1] = (y_values[1] << 0) | (u_values[1] << 10) | (y_values[2] << 20);
            dst[dst_idx + 2] = (v_values[1] << 0) | (y_values[3] << 10) | (u_values[2] << 20);
            dst[dst_idx + 3] = (y_values[4] << 0) | (v_values[2] << 10) | (y_values[5] << 20);
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_uint16_to_rgb10(py::array_t<uint16_t> rgb_array, int width, int height, bool input_narrow_range = true, bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // bmdFormat10BitRGBXLE: 4 bytes per pixel (32-bit words)
    int row_bytes = width * 4;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint32_t* dst = static_cast<uint32_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Range constants (hoisted out of the per-pixel loop).
    // Input is 16-bit; output is 10-bit. Narrow 16-bit is the 10-bit narrow
    // range scaled up by 64, so 64<<6 .. 940<<6 = 4096 .. 60160.
    double in_min   = input_narrow_range  ? 64.0 * 64.0  : 0.0;        // 4096 or 0
    double in_range = input_narrow_range  ? 876.0 * 64.0 : 65535.0;    // 56064 or 65535
    double out_min   = output_narrow_range ? 64.0   : 0.0;             // 10-bit narrow black
    double out_range = output_narrow_range ? 876.0  : 1023.0;          // 10-bit narrow / full range

    bool use_bitshift = (input_narrow_range == output_narrow_range);

    for (int y = 0; y < height; y++) {
        uint32_t* row_dst = dst + (y * row_bytes / 4);
        for (int x = 0; x < width; x++) {
            const uint16_t* pixel = reinterpret_cast<const uint16_t*>(
                src_base + y * stride_y + x * stride_x);

            uint16_t r10, g10, b10;

            if (use_bitshift) {
                // Same range: 16-bit -> 10-bit by dropping bottom 6 bits
                r10 = pixel[0] >> 6;
                g10 = pixel[1] >> 6;
                b10 = pixel[2] >> 6;
            } else {
                // Different ranges: normalise input to 0..1, scale to output range
                double rf = (pixel[0] - in_min) / in_range;
                double gf = (pixel[1] - in_min) / in_range;
                double bf = (pixel[2] - in_min) / in_range;

                int r10_int = (int)(rf * out_range + out_min + 0.5);
                int g10_int = (int)(gf * out_range + out_min + 0.5);
                int b10_int = (int)(bf * out_range + out_min + 0.5);

                // Clamp to valid 10-bit code range before packing
                r10 = (uint16_t)(r10_int < 0 ? 0 : (r10_int > 1023 ? 1023 : r10_int));
                g10 = (uint16_t)(g10_int < 0 ? 0 : (g10_int > 1023 ? 1023 : g10_int));
                b10 = (uint16_t)(b10_int < 0 ? 0 : (b10_int > 1023 ? 1023 : b10_int));
            }

            // Pack as bmdFormat10BitRGBXLE (little-endian 10-bit RGB)
            // 32-bit word: R[9:0] at bits 31:22, G[9:0] at bits 21:12, B[9:0] at bits 11:2, padding at bits 1:0
            row_dst[x] = (r10 << 22) | (g10 << 12) | (b10 << 2);
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_float_to_rgb10(py::array_t<float> rgb_array, int width, int height, bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // bmdFormat10BitRGBXLE: 4 bytes per pixel (32-bit words)
    int row_bytes = width * 4;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint32_t* dst = static_cast<uint32_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Output range constants. Float input is always 0..1 full range.
    // Narrow output: 0..1 maps to 64..940 (10-bit narrow).
    // Full output:   0..1 maps to 0..1023 (10-bit full).
    double out_min   = output_narrow_range ? 64.0  : 0.0;
    double out_range = output_narrow_range ? 876.0 : 1023.0;

    for (int y = 0; y < height; y++) {
        uint32_t* row_dst = dst + (y * row_bytes / 4);
        for (int x = 0; x < width; x++) {
            const float* pixel = reinterpret_cast<const float*>(
                src_base + y * stride_y + x * stride_x);

            // Convert float (0..1) to 10-bit with rounding
            int r10 = (int)(pixel[0] * out_range + out_min + 0.5);
            int g10 = (int)(pixel[1] * out_range + out_min + 0.5);
            int b10 = (int)(pixel[2] * out_range + out_min + 0.5);

            // Clamp to valid 10-bit code range
            r10 = r10 < 0 ? 0 : (r10 > 1023 ? 1023 : r10);
            g10 = g10 < 0 ? 0 : (g10 > 1023 ? 1023 : g10);
            b10 = b10 < 0 ? 0 : (b10 > 1023 ? 1023 : b10);

            // Pack as bmdFormat10BitRGBXLE (little-endian 10-bit RGB)
            row_dst[x] = (r10 << 22) | (g10 << 12) | (b10 << 2);
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_uint16_to_rgb12(py::array_t<uint16_t> rgb_array, int width, int height,
                                         bool input_narrow_range = false, bool output_narrow_range = false) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // bmdFormat12BitRGBLE: 36 bits per pixel, 8 pixels in 36 bytes (9 DWORDs)
    int row_bytes = ((width + 7) / 8) * 36;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint32_t* dst = static_cast<uint32_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Range constants (hoisted out of the per-pixel loop).
    // Input is 16-bit; output is 12-bit. Narrow 16-bit is the 12-bit narrow
    // range scaled up by 16, so 256<<4 .. 3760<<4 = 4096 .. 60160.
    double in_min   = input_narrow_range  ? 256.0 * 16.0  : 0.0;       // 4096 or 0
    double in_range = input_narrow_range  ? 3504.0 * 16.0 : 65535.0;   // 56064 or 65535
    double out_min   = output_narrow_range ? 256.0  : 0.0;             // 12-bit narrow black
    double out_range = output_narrow_range ? 3504.0 : 4095.0;          // 12-bit narrow / full range

    bool use_bitshift = (input_narrow_range == output_narrow_range);

    for (int y = 0; y < height; y++) {
        uint32_t* nextWord = dst + (y * row_bytes / 4);

        for (int x = 0; x < width; x += 8) {
            // Process 8 pixels at a time (or fewer at end of row)
            uint16_t r[8], g[8], b[8];

            for (int i = 0; i < 8; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const uint16_t* pixel = reinterpret_cast<const uint16_t*>(
                        src_base + y * stride_y + pixel_x * stride_x);

                    if (use_bitshift) {
                        // Same range: 16-bit -> 12-bit by dropping bottom 4 bits
                        r[i] = pixel[0] >> 4;
                        g[i] = pixel[1] >> 4;
                        b[i] = pixel[2] >> 4;
                    } else {
                        // Different ranges: normalise input to 0..1, scale to output range
                        double rf = (pixel[0] - in_min) / in_range;
                        double gf = (pixel[1] - in_min) / in_range;
                        double bf = (pixel[2] - in_min) / in_range;

                        int r12 = (int)(rf * out_range + out_min + 0.5);
                        int g12 = (int)(gf * out_range + out_min + 0.5);
                        int b12 = (int)(bf * out_range + out_min + 0.5);

                        // Clamp to valid 12-bit code range before packing
                        r[i] = (uint16_t)(r12 < 0 ? 0 : (r12 > 4095 ? 4095 : r12));
                        g[i] = (uint16_t)(g12 < 0 ? 0 : (g12 > 4095 ? 4095 : g12));
                        b[i] = (uint16_t)(b12 < 0 ? 0 : (b12 > 4095 ? 4095 : b12));
                    }
                } else {
                    // Padding for incomplete groups
                    r[i] = 0;
                    g[i] = 0;
                    b[i] = 0;
                }
            }

            // Pack 8 pixels into 9 DWORDs using SDK sample formula
            *nextWord++ = ((b[0] & 0x0FF) << 24) | ((g[0] & 0xFFF) << 12) | (r[0] & 0xFFF);
            *nextWord++ = ((b[1] & 0x00F) << 28) | ((g[1] & 0xFFF) << 16) | ((r[1] & 0xFFF) << 4) | ((b[0] & 0xF00) >> 8);
            *nextWord++ = ((g[2] & 0xFFF) << 20) | ((r[2] & 0xFFF) << 8) | ((b[1] & 0xFF0) >> 4);
            *nextWord++ = ((g[3] & 0x0FF) << 24) | ((r[3] & 0xFFF) << 12) | (b[2] & 0xFFF);
            *nextWord++ = ((g[4] & 0x00F) << 28) | ((r[4] & 0xFFF) << 16) | ((b[3] & 0xFFF) << 4) | ((g[3] & 0xF00) >> 8);
            *nextWord++ = ((r[5] & 0xFFF) << 20) | ((b[4] & 0xFFF) << 8) | ((g[4] & 0xFF0) >> 4);
            *nextWord++ = ((r[6] & 0x0FF) << 24) | ((b[5] & 0xFFF) << 12) | (g[5] & 0xFFF);
            *nextWord++ = ((r[7] & 0x00F) << 28) | ((b[6] & 0xFFF) << 16) | ((g[6] & 0xFFF) << 4) | ((r[6] & 0xF00) >> 8);
            *nextWord++ = ((b[7] & 0xFFF) << 20) | ((g[7] & 0xFFF) << 8) | ((r[7] & 0xFF0) >> 4);
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_float_to_rgb12(py::array_t<float> rgb_array, int width, int height, bool output_narrow_range = false) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // bmdFormat12BitRGBLE: 36 bits per pixel, 8 pixels in 36 bytes (9 DWORDs)
    int row_bytes = ((width + 7) / 8) * 36;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint32_t* dst = static_cast<uint32_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Output range constants. Float input is always 0..1 full range.
    // Narrow output: 0..1 maps to 256..3760 (12-bit narrow).
    // Full output:   0..1 maps to 0..4095 (12-bit full).
    double out_min   = output_narrow_range ? 256.0  : 0.0;
    double out_range = output_narrow_range ? 3504.0 : 4095.0;

    for (int y = 0; y < height; y++) {
        uint32_t* nextWord = dst + (y * row_bytes / 4);

        for (int x = 0; x < width; x += 8) {
            // Process 8 pixels at a time (or fewer at end of row)
            uint16_t r[8], g[8], b[8];

            for (int i = 0; i < 8; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const float* pixel = reinterpret_cast<const float*>(
                        src_base + y * stride_y + pixel_x * stride_x);

                    // Convert float (0..1) to 12-bit with rounding
                    int r12 = (int)(pixel[0] * out_range + out_min + 0.5);
                    int g12 = (int)(pixel[1] * out_range + out_min + 0.5);
                    int b12 = (int)(pixel[2] * out_range + out_min + 0.5);

                    // Clamp to valid 12-bit code range
                    r[i] = (uint16_t)(r12 < 0 ? 0 : (r12 > 4095 ? 4095 : r12));
                    g[i] = (uint16_t)(g12 < 0 ? 0 : (g12 > 4095 ? 4095 : g12));
                    b[i] = (uint16_t)(b12 < 0 ? 0 : (b12 > 4095 ? 4095 : b12));
                } else {
                    // Padding for incomplete groups
                    r[i] = 0;
                    g[i] = 0;
                    b[i] = 0;
                }
            }

            // Pack 8 pixels into 9 DWORDs using SDK sample formula
            *nextWord++ = ((b[0] & 0x0FF) << 24) | ((g[0] & 0xFFF) << 12) | (r[0] & 0xFFF);
            *nextWord++ = ((b[1] & 0x00F) << 28) | ((g[1] & 0xFFF) << 16) | ((r[1] & 0xFFF) << 4) | ((b[0] & 0xF00) >> 8);
            *nextWord++ = ((g[2] & 0xFFF) << 20) | ((r[2] & 0xFFF) << 8) | ((b[1] & 0xFF0) >> 4);
            *nextWord++ = ((g[3] & 0x0FF) << 24) | ((r[3] & 0xFFF) << 12) | (b[2] & 0xFFF);
            *nextWord++ = ((g[4] & 0x00F) << 28) | ((r[4] & 0xFFF) << 16) | ((b[3] & 0xFFF) << 4) | ((g[3] & 0xF00) >> 8);
            *nextWord++ = ((r[5] & 0xFFF) << 20) | ((b[4] & 0xFFF) << 8) | ((g[4] & 0xFF0) >> 4);
            *nextWord++ = ((r[6] & 0x0FF) << 24) | ((b[5] & 0xFFF) << 12) | (g[5] & 0xFFF);
            *nextWord++ = ((r[7] & 0x00F) << 28) | ((b[6] & 0xFFF) << 16) | ((g[6] & 0xFFF) << 4) | ((r[6] & 0xF00) >> 8);
            *nextWord++ = ((b[7] & 0xFFF) << 20) | ((g[7] & 0xFFF) << 8) | ((r[7] & 0xFF0) >> 4);
        }
    }

    return result;
}

py::array_t<uint16_t> yuv10_to_rgb_uint16(py::array_t<uint8_t> yuv_array, int width, int height, DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709, bool input_narrow_range = true, bool output_narrow_range = false, int row_bytes = -1) {
    auto buf = yuv_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D v210 format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = ((width + 47) / 48) * 128;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for v210 format");
    }

    auto result = py::array_t<uint16_t>({height, width, 3});
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* dst = static_cast<uint16_t*>(res_buf.ptr);

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        const uint32_t* src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);
        for (int x = 0; x < width; x += 6) {
            int groupIndex = (x / 6) * 4;
            const uint32_t* group = src + groupIndex;

            uint32_t d0 = group[0];
            uint32_t d1 = group[1];
            uint32_t d2 = group[2];
            uint32_t d3 = group[3];

            for (int i = 0; i < 6 && (x + i) < width; i++) {
                uint16_t y_val, cb_val, cr_val;

                switch (i) {
                    case 0:
                        y_val = (d0 >> 10) & 0x3FF;
                        cb_val = d0 & 0x3FF;
                        cr_val = (d0 >> 20) & 0x3FF;
                        break;
                    case 1:
                        y_val = d1 & 0x3FF;
                        cb_val = d0 & 0x3FF;
                        cr_val = (d0 >> 20) & 0x3FF;
                        break;
                    case 2:
                        y_val = (d1 >> 20) & 0x3FF;
                        cb_val = (d1 >> 10) & 0x3FF;
                        cr_val = d2 & 0x3FF;
                        break;
                    case 3:
                        y_val = (d2 >> 10) & 0x3FF;
                        cb_val = (d1 >> 10) & 0x3FF;
                        cr_val = d2 & 0x3FF;
                        break;
                    case 4:
                        y_val = d3 & 0x3FF;
                        cb_val = (d2 >> 20) & 0x3FF;
                        cr_val = (d3 >> 10) & 0x3FF;
                        break;
                    case 5:
                        y_val = (d3 >> 20) & 0x3FF;
                        cb_val = (d2 >> 20) & 0x3FF;
                        cr_val = (d3 >> 10) & 0x3FF;
                        break;
                }

                // Normalise Y to 0..1 and Cb/Cr to -1..+1
                double yf, cbf, crf;
                if (input_narrow_range) {
                    yf  = (y_val  -  64.0) / 876.0;
                    cbf = (cb_val - 512.0) / 448.0;
                    crf = (cr_val - 512.0) / 448.0;
                } else {
                    yf  =  y_val           / 1023.0;
                    cbf = (cb_val - 512.0) * 2.0 / 1023.0;
                    crf = (cr_val - 512.0) * 2.0 / 1023.0;
                }

                // YCbCr -> RGB ((1-Kr) form, chroma in -1..+1)
                double rf = yf + (1.0 - Kr) * crf;
                double bf = yf + (1.0 - Kb) * cbf;
                double gf = yf - (Kr * (1.0 - Kr) / Kg) * crf
                                - (Kb * (1.0 - Kb) / Kg) * cbf;

                // Allow super-whites (values > 1.0), but clamp after scaling to prevent uint16_t overflow
                uint16_t r16, g16, b16;

                if (output_narrow_range) {
                    r16 = (uint16_t)std::max(0.0, std::min(65535.0, rf * 876.0 * 64.0 + 64.0 * 64.0));
                    g16 = (uint16_t)std::max(0.0, std::min(65535.0, gf * 876.0 * 64.0 + 64.0 * 64.0));
                    b16 = (uint16_t)std::max(0.0, std::min(65535.0, bf * 876.0 * 64.0 + 64.0 * 64.0));
                } else {
                    r16 = (uint16_t)std::max(0.0, std::min(65535.0, rf * 65535.0));
                    g16 = (uint16_t)std::max(0.0, std::min(65535.0, gf * 65535.0));
                    b16 = (uint16_t)std::max(0.0, std::min(65535.0, bf * 65535.0));
                }

                int pixel_idx = (y * width + x + i) * 3;
                dst[pixel_idx + 0] = r16;
                dst[pixel_idx + 1] = g16;
                dst[pixel_idx + 2] = b16;
            }
        }
    }

    return result;
}

py::array_t<float> yuv10_to_rgb_float(py::array_t<uint8_t> yuv_array, int width, int height, DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709, bool input_narrow_range = true, int row_bytes = -1) {
    auto buf = yuv_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D v210 format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = ((width + 47) / 48) * 128;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for v210 format");
    }

    auto result = py::array_t<float>({height, width, 3});
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    float* dst = static_cast<float*>(res_buf.ptr);

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        const uint32_t* src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);
        for (int x = 0; x < width; x += 6) {
            int groupIndex = (x / 6) * 4;
            const uint32_t* group = src + groupIndex;

            uint32_t d0 = group[0];
            uint32_t d1 = group[1];
            uint32_t d2 = group[2];
            uint32_t d3 = group[3];

            for (int i = 0; i < 6 && (x + i) < width; i++) {
                uint16_t y_val, cb_val, cr_val;

                switch (i) {
                    case 0:
                        y_val = (d0 >> 10) & 0x3FF;
                        cb_val = d0 & 0x3FF;
                        cr_val = (d0 >> 20) & 0x3FF;
                        break;
                    case 1:
                        y_val = d1 & 0x3FF;
                        cb_val = d0 & 0x3FF;
                        cr_val = (d0 >> 20) & 0x3FF;
                        break;
                    case 2:
                        y_val = (d1 >> 20) & 0x3FF;
                        cb_val = (d1 >> 10) & 0x3FF;
                        cr_val = d2 & 0x3FF;
                        break;
                    case 3:
                        y_val = (d2 >> 10) & 0x3FF;
                        cb_val = (d1 >> 10) & 0x3FF;
                        cr_val = d2 & 0x3FF;
                        break;
                    case 4:
                        y_val = d3 & 0x3FF;
                        cb_val = (d2 >> 20) & 0x3FF;
                        cr_val = (d3 >> 10) & 0x3FF;
                        break;
                    case 5:
                        y_val = (d3 >> 20) & 0x3FF;
                        cb_val = (d2 >> 20) & 0x3FF;
                        cr_val = (d3 >> 10) & 0x3FF;
                        break;
                }

                // Normalise Y to 0..1 and Cb/Cr to -1..+1
                double yf, cbf, crf;
                if (input_narrow_range) {
                    yf  = (y_val  -  64.0) / 876.0;
                    cbf = (cb_val - 512.0) / 448.0;
                    crf = (cr_val - 512.0) / 448.0;
                } else {
                    yf  =  y_val           / 1023.0;
                    cbf = (cb_val - 512.0) * 2.0 / 1023.0;
                    crf = (cr_val - 512.0) * 2.0 / 1023.0;
                }

                // YCbCr -> RGB ((1-Kr) form, chroma in -1..+1)
                double rf = yf + (1.0 - Kr) * crf;
                double bf = yf + (1.0 - Kb) * cbf;
                double gf = yf - (Kr * (1.0 - Kr) / Kg) * crf
                                - (Kb * (1.0 - Kb) / Kg) * cbf;

                // Allow super-whites: values > 1.0 are valid for super-white content
                int pixel_idx = (y * width + x + i) * 3;
                dst[pixel_idx + 0] = static_cast<float>(rf);
                dst[pixel_idx + 1] = static_cast<float>(gf);
                dst[pixel_idx + 2] = static_cast<float>(bf);
            }
        }
    }

    return result;
}

py::dict unpack_v210(py::array_t<uint8_t> yuv_array, int width, int height, int row_bytes = -1) {
    auto buf = yuv_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D v210 format");
    }

    if (row_bytes < 0) {
        row_bytes = ((width + 47) / 48) * 128;
    }

    long expected_size = (long)row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for v210 format");
    }

    auto y_array = py::array_t<uint16_t>({height, width});
    auto cb_array = py::array_t<uint16_t>({height, width});
    auto cr_array = py::array_t<uint16_t>({height, width});

    auto y_buf = y_array.request();
    auto cb_buf = cb_array.request();
    auto cr_buf = cr_array.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* y_dst = static_cast<uint16_t*>(y_buf.ptr);
    uint16_t* cb_dst = static_cast<uint16_t*>(cb_buf.ptr);
    uint16_t* cr_dst = static_cast<uint16_t*>(cr_buf.ptr);

    for (int y = 0; y < height; y++) {
        const uint32_t* row_src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);
        for (int x = 0; x < width; x += 6) {
            int groupIndex = (x / 6) * 4;
            const uint32_t* group = row_src + groupIndex;

            uint32_t d0 = group[0];
            uint32_t d1 = group[1];
            uint32_t d2 = group[2];
            uint32_t d3 = group[3];

            for (int i = 0; i < 6 && (x + i) < width; i++) {
                uint16_t y_val, cb_val, cr_val;

                switch (i) {
                    case 0:
                        y_val = (d0 >> 10) & 0x3FF;
                        cb_val = d0 & 0x3FF;
                        cr_val = (d0 >> 20) & 0x3FF;
                        break;
                    case 1:
                        y_val = d1 & 0x3FF;
                        cb_val = d0 & 0x3FF;
                        cr_val = (d0 >> 20) & 0x3FF;
                        break;
                    case 2:
                        y_val = (d1 >> 20) & 0x3FF;
                        cb_val = (d1 >> 10) & 0x3FF;
                        cr_val = d2 & 0x3FF;
                        break;
                    case 3:
                        y_val = (d2 >> 10) & 0x3FF;
                        cb_val = (d1 >> 10) & 0x3FF;
                        cr_val = d2 & 0x3FF;
                        break;
                    case 4:
                        y_val = d3 & 0x3FF;
                        cb_val = (d2 >> 20) & 0x3FF;
                        cr_val = (d3 >> 10) & 0x3FF;
                        break;
                    case 5:
                        y_val = (d3 >> 20) & 0x3FF;
                        cb_val = (d2 >> 20) & 0x3FF;
                        cr_val = (d3 >> 10) & 0x3FF;
                        break;
                }

                int pixel_idx = y * width + x + i;
                y_dst[pixel_idx] = y_val;
                cb_dst[pixel_idx] = cb_val;
                cr_dst[pixel_idx] = cr_val;
            }
        }
    }

    py::dict result;
    result["y"] = y_array;
    result["cb"] = cb_array;
    result["cr"] = cr_array;
    return result;
}

// YUV8 (2vuy) to RGB conversion functions
py::array_t<uint16_t> yuv8_to_rgb_uint16(py::array_t<uint8_t> yuv_array, int width, int height,
                                          DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709,
                                          bool input_narrow_range = true, bool output_narrow_range = false, int row_bytes = -1) {
    auto buf = yuv_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D 2vuy format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = width * 2;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for 2vuy format");
    }

    auto rgb_array = py::array_t<uint16_t>({height, width, 3});
    auto rgb_buf = rgb_array.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* rgb_dst = static_cast<uint16_t*>(rgb_buf.ptr);

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    // Output 16-bit range (narrow = 64<<6 .. 940<<6, full = 0..65535)
    double out_min, out_range;
    if (output_narrow_range) {
        out_min = 64.0 * 64.0;       // 4096
        out_range = 876.0 * 64.0;    // 56064
    } else {
        out_min = 0.0;
        out_range = 65535.0;
    }

    for (int y = 0; y < height; y++) {
        const uint8_t* src = src_base + y * row_bytes;
        for (int x = 0; x < width; x += 2) {
            int row_idx = x * 2;

            uint8_t u_byte = src[row_idx];
            uint8_t y0_byte = src[row_idx + 1];
            uint8_t v_byte = src[row_idx + 2];
            uint8_t y1_byte = src[row_idx + 3];

            // Normalise Y to 0..1 and Cb/Cr to -1..+1
            double y0, y1, cbf, crf;
            if (input_narrow_range) {
                // Y: 16..235 (range 219); Cb/Cr: 16..240 (±112 from 128)
                y0  = (y0_byte - 16.0)  / 219.0;
                y1  = (y1_byte - 16.0)  / 219.0;
                cbf = (u_byte  - 128.0) / 112.0;
                crf = (v_byte  - 128.0) / 112.0;
            } else {
                y0  =  y0_byte           / 255.0;
                y1  =  y1_byte           / 255.0;
                cbf = (u_byte  - 128.0) * 2.0 / 255.0;
                crf = (v_byte  - 128.0) * 2.0 / 255.0;
            }

            // YCbCr -> RGB ((1-Kr) form, chroma in -1..+1)
            double r_off = (1.0 - Kr) * crf;
            double b_off = (1.0 - Kb) * cbf;
            double g_off = - (Kr * (1.0 - Kr) / Kg) * crf
                            - (Kb * (1.0 - Kb) / Kg) * cbf;

            int pixel0_idx = (y * width + x) * 3;
            rgb_dst[pixel0_idx]     = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, (y0 + r_off) * out_range + out_min)));
            rgb_dst[pixel0_idx + 1] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, (y0 + g_off) * out_range + out_min)));
            rgb_dst[pixel0_idx + 2] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, (y0 + b_off) * out_range + out_min)));

            if (x + 1 < width) {
                int pixel1_idx = (y * width + x + 1) * 3;
                rgb_dst[pixel1_idx]     = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, (y1 + r_off) * out_range + out_min)));
                rgb_dst[pixel1_idx + 1] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, (y1 + g_off) * out_range + out_min)));
                rgb_dst[pixel1_idx + 2] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, (y1 + b_off) * out_range + out_min)));
            }
        }
    }

    return rgb_array;
}

py::array_t<float> yuv8_to_rgb_float(py::array_t<uint8_t> yuv_array, int width, int height,
                                       DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709,
                                       bool input_narrow_range = true, int row_bytes = -1) {
    auto buf = yuv_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D 2vuy format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = width * 2;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for 2vuy format");
    }

    auto rgb_array = py::array_t<float>({height, width, 3});
    auto rgb_buf = rgb_array.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    float* rgb_dst = static_cast<float*>(rgb_buf.ptr);

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        const uint8_t* src = src_base + y * row_bytes;
        for (int x = 0; x < width; x += 2) {
            int row_idx = x * 2;

            uint8_t u_byte = src[row_idx];
            uint8_t y0_byte = src[row_idx + 1];
            uint8_t v_byte = src[row_idx + 2];
            uint8_t y1_byte = src[row_idx + 3];

            // Normalise Y to 0..1 and Cb/Cr to -1..+1
            double y0, y1, cbf, crf;
            if (input_narrow_range) {
                // Y: 16..235 (range 219); Cb/Cr: 16..240 (±112 from 128)
                y0  = (y0_byte - 16.0)  / 219.0;
                y1  = (y1_byte - 16.0)  / 219.0;
                cbf = (u_byte  - 128.0) / 112.0;
                crf = (v_byte  - 128.0) / 112.0;
            } else {
                y0  =  y0_byte           / 255.0;
                y1  =  y1_byte           / 255.0;
                cbf = (u_byte  - 128.0) * 2.0 / 255.0;
                crf = (v_byte  - 128.0) * 2.0 / 255.0;
            }

            // YCbCr -> RGB ((1-Kr) form, chroma in -1..+1)
            double r_off = (1.0 - Kr) * crf;
            double b_off = (1.0 - Kb) * cbf;
            double g_off = - (Kr * (1.0 - Kr) / Kg) * crf
                            - (Kb * (1.0 - Kb) / Kg) * cbf;

            // Allow super-whites: values > 1.0 are valid for super-white content
            int pixel0_idx = (y * width + x) * 3;
            rgb_dst[pixel0_idx]     = static_cast<float>(y0 + r_off);
            rgb_dst[pixel0_idx + 1] = static_cast<float>(y0 + g_off);
            rgb_dst[pixel0_idx + 2] = static_cast<float>(y0 + b_off);

            if (x + 1 < width) {
                int pixel1_idx = (y * width + x + 1) * 3;
                rgb_dst[pixel1_idx]     = static_cast<float>(y1 + r_off);
                rgb_dst[pixel1_idx + 1] = static_cast<float>(y1 + g_off);
                rgb_dst[pixel1_idx + 2] = static_cast<float>(y1 + b_off);
            }
        }
    }

    return rgb_array;
}

// RGB to YUV8 (2vuy) conversion functions
py::array_t<uint8_t> rgb_uint8_to_yuv8(py::array_t<uint8_t> rgb_array, int width, int height,
                                        DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709,
                                        bool input_narrow_range = false, bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // 2vuy format: 2 bytes per pixel (4:2:2 chroma subsampling)
    int row_bytes = width * 2;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint8_t* dst = static_cast<uint8_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x += 2) {
            double cb_temp[2], cr_temp[2];   // chroma in -1..+1
            uint8_t y_values[2];

            // Convert RGB to YCbCr for 2 pixels
            for (int i = 0; i < 2; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const uint8_t* pixel = src_base + y * stride_y + pixel_x * stride_x;
                    uint8_t r = pixel[0];
                    uint8_t g = pixel[1];
                    uint8_t b = pixel[2];

                    double rf, gf, bf;
                    if (input_narrow_range) {
                        rf = (r - 16) / 219.0;
                        gf = (g - 16) / 219.0;
                        bf = (b - 16) / 219.0;
                    } else {
                        rf = r / 255.0;
                        gf = g / 255.0;
                        bf = b / 255.0;
                    }

                    // RGB -> YCbCr ((1-Kr) form, chroma in -1..+1)
                    double yf  = Kr * rf + Kg * gf + Kb * bf;
                    double cbf = (bf - yf) / (1.0 - Kb);
                    double crf = (rf - yf) / (1.0 - Kr);

                    int y8;
                    if (output_narrow_range) {
                        y8 = (int)(yf * 219.0 + 16.0 + 0.5);
                    } else {
                        y8 = (int)(yf * 255.0 + 0.5);
                    }
                    // Clamp to byte range, allowing super-blacks/super-whites
                    y8 = (y8 < 0) ? 0 : ((y8 > 255) ? 255 : y8);
                    y_values[i] = (uint8_t)y8;
                    cb_temp[i] = cbf;
                    cr_temp[i] = crf;
                } else {
                    y_values[i] = output_narrow_range ? 16 : 0;
                    cb_temp[i] = 0.0;
                    cr_temp[i] = 0.0;
                }
            }

            // Average Cb/Cr samples for 4:2:2 chroma subsampling
            double cb_avg = (cb_temp[0] + cb_temp[1]) * 0.5;
            double cr_avg = (cr_temp[0] + cr_temp[1]) * 0.5;

            int cb8, cr8;
            if (output_narrow_range) {
                cb8 = (int)(cb_avg * 112.0 + 128.0 + 0.5);
                cr8 = (int)(cr_avg * 112.0 + 128.0 + 0.5);
            } else {
                cb8 = (int)(cb_avg * 255.0 / 2.0 + 128.0 + 0.5);
                cr8 = (int)(cr_avg * 255.0 / 2.0 + 128.0 + 0.5);
            }
            cb8 = (cb8 < 0) ? 0 : ((cb8 > 255) ? 255 : cb8);
            cr8 = (cr8 < 0) ? 0 : ((cr8 > 255) ? 255 : cr8);

            // Pack into 2vuy format: U Y0 V Y1
            int dst_idx = (y * width + x) * 2;
            dst[dst_idx + 0] = (uint8_t)cb8;
            dst[dst_idx + 1] = y_values[0];
            dst[dst_idx + 2] = (uint8_t)cr8;
            dst[dst_idx + 3] = y_values[1];
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_uint16_to_yuv8(py::array_t<uint16_t> rgb_array, int width, int height,
                                         DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709,
                                         bool input_narrow_range = false, bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // 2vuy format: 2 bytes per pixel (4:2:2 chroma subsampling)
    int row_bytes = width * 2;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint8_t* dst = static_cast<uint8_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x += 2) {
            double cb_temp[2], cr_temp[2];   // chroma in -1..+1
            uint8_t y_values[2];

            // Convert RGB to YCbCr for 2 pixels
            for (int i = 0; i < 2; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const uint16_t* pixel = reinterpret_cast<const uint16_t*>(
                        src_base + y * stride_y + pixel_x * stride_x);
                    uint16_t r = pixel[0];
                    uint16_t g = pixel[1];
                    uint16_t b = pixel[2];

                    double rf, gf, bf;
                    if (input_narrow_range) {
                        rf = (r - (64 << 6)) / (double)(876 << 6);
                        gf = (g - (64 << 6)) / (double)(876 << 6);
                        bf = (b - (64 << 6)) / (double)(876 << 6);
                    } else {
                        rf = r / 65535.0;
                        gf = g / 65535.0;
                        bf = b / 65535.0;
                    }

                    // RGB -> YCbCr ((1-Kr) form, chroma in -1..+1)
                    double yf  = Kr * rf + Kg * gf + Kb * bf;
                    double cbf = (bf - yf) / (1.0 - Kb);
                    double crf = (rf - yf) / (1.0 - Kr);

                    int y8;
                    if (output_narrow_range) {
                        y8 = (int)(yf * 219.0 + 16.0 + 0.5);
                    } else {
                        y8 = (int)(yf * 255.0 + 0.5);
                    }
                    // Clamp to byte range, allowing super-blacks/super-whites
                    y8 = (y8 < 0) ? 0 : ((y8 > 255) ? 255 : y8);
                    y_values[i] = (uint8_t)y8;
                    cb_temp[i] = cbf;
                    cr_temp[i] = crf;
                } else {
                    y_values[i] = output_narrow_range ? 16 : 0;
                    cb_temp[i] = 0.0;
                    cr_temp[i] = 0.0;
                }
            }

            // Average Cb/Cr samples for 4:2:2 chroma subsampling
            double cb_avg = (cb_temp[0] + cb_temp[1]) * 0.5;
            double cr_avg = (cr_temp[0] + cr_temp[1]) * 0.5;

            int cb8, cr8;
            if (output_narrow_range) {
                cb8 = (int)(cb_avg * 112.0 + 128.0 + 0.5);
                cr8 = (int)(cr_avg * 112.0 + 128.0 + 0.5);
            } else {
                cb8 = (int)(cb_avg * 255.0 / 2.0 + 128.0 + 0.5);
                cr8 = (int)(cr_avg * 255.0 / 2.0 + 128.0 + 0.5);
            }
            cb8 = (cb8 < 0) ? 0 : ((cb8 > 255) ? 255 : cb8);
            cr8 = (cr8 < 0) ? 0 : ((cr8 > 255) ? 255 : cr8);

            // Pack into 2vuy format: U Y0 V Y1
            int dst_idx = (y * width + x) * 2;
            dst[dst_idx + 0] = (uint8_t)cb8;
            dst[dst_idx + 1] = y_values[0];
            dst[dst_idx + 2] = (uint8_t)cr8;
            dst[dst_idx + 3] = y_values[1];
        }
    }

    return result;
}

py::array_t<uint8_t> rgb_float_to_yuv8(py::array_t<float> rgb_array, int width, int height,
                                        DeckLinkOutput::Matrix matrix = DeckLinkOutput::Matrix::Rec709,
                                        bool output_narrow_range = true) {
    auto buf = rgb_array.request();

    if (buf.ndim != 3 || buf.shape[2] != 3) {
        throw std::runtime_error("Input array must be HxWx3 RGB format");
    }

    if (buf.shape[0] != height || buf.shape[1] != width) {
        throw std::runtime_error("Array dimensions don't match specified width/height");
    }

    // 2vuy format: 2 bytes per pixel (4:2:2 chroma subsampling)
    int row_bytes = width * 2;
    auto result = py::array_t<uint8_t>(height * row_bytes);
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint8_t* dst = static_cast<uint8_t*>(res_buf.ptr);

    // Get strides in bytes
    ssize_t stride_y = buf.strides[0];
    ssize_t stride_x = buf.strides[1];

    // Matrix coefficients: Y = Kr*R + Kg*G + Kb*B
    double Kr, Kb;
    switch (matrix) {
        case DeckLinkOutput::Matrix::Rec601:  Kr = 0.299;  Kb = 0.114;  break;
        case DeckLinkOutput::Matrix::Rec2020: Kr = 0.2627; Kb = 0.0593; break;
        case DeckLinkOutput::Matrix::Rec709:
        default:                             Kr = 0.2126; Kb = 0.0722; break;
    }
    double Kg = 1.0 - Kr - Kb;

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x += 2) {
            double cb_temp[2], cr_temp[2];   // chroma in -1..+1
            uint8_t y_values[2];

            // Convert RGB to YCbCr for 2 pixels
            for (int i = 0; i < 2; i++) {
                int pixel_x = x + i;
                if (pixel_x < width) {
                    const float* pixel = reinterpret_cast<const float*>(
                        src_base + y * stride_y + pixel_x * stride_x);
                    double rf = pixel[0];
                    double gf = pixel[1];
                    double bf = pixel[2];

                    // RGB -> YCbCr ((1-Kr) form, chroma in -1..+1)
                    double yf  = Kr * rf + Kg * gf + Kb * bf;
                    double cbf = (bf - yf) / (1.0 - Kb);
                    double crf = (rf - yf) / (1.0 - Kr);

                    int y8;
                    if (output_narrow_range) {
                        y8 = (int)(yf * 219.0 + 16.0 + 0.5);
                    } else {
                        y8 = (int)(yf * 255.0 + 0.5);
                    }
                    // Clamp to byte range, allowing super-blacks/super-whites
                    y8 = (y8 < 0) ? 0 : ((y8 > 255) ? 255 : y8);
                    y_values[i] = (uint8_t)y8;
                    cb_temp[i] = cbf;
                    cr_temp[i] = crf;
                } else {
                    y_values[i] = output_narrow_range ? 16 : 0;
                    cb_temp[i] = 0.0;
                    cr_temp[i] = 0.0;
                }
            }

            // Average Cb/Cr samples for 4:2:2 chroma subsampling
            double cb_avg = (cb_temp[0] + cb_temp[1]) * 0.5;
            double cr_avg = (cr_temp[0] + cr_temp[1]) * 0.5;

            int cb8, cr8;
            if (output_narrow_range) {
                cb8 = (int)(cb_avg * 112.0 + 128.0 + 0.5);
                cr8 = (int)(cr_avg * 112.0 + 128.0 + 0.5);
            } else {
                cb8 = (int)(cb_avg * 255.0 / 2.0 + 128.0 + 0.5);
                cr8 = (int)(cr_avg * 255.0 / 2.0 + 128.0 + 0.5);
            }
            cb8 = (cb8 < 0) ? 0 : ((cb8 > 255) ? 255 : cb8);
            cr8 = (cr8 < 0) ? 0 : ((cr8 > 255) ? 255 : cr8);

            // Pack into 2vuy format: U Y0 V Y1
            int dst_idx = (y * width + x) * 2;
            dst[dst_idx + 0] = (uint8_t)cb8;
            dst[dst_idx + 1] = y_values[0];
            dst[dst_idx + 2] = (uint8_t)cr8;
            dst[dst_idx + 3] = y_values[1];
        }
    }

    return result;
}

py::dict unpack_2vuy(py::array_t<uint8_t> yuv_array, int width, int height, int row_bytes = -1) {
    auto buf = yuv_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D 2vuy format");
    }

    if (row_bytes < 0) {
        row_bytes = width * 2;
    }

    long expected_size = (long)row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for 2vuy format");
    }

    auto y_array = py::array_t<uint8_t>({height, width});
    auto cb_array = py::array_t<uint8_t>({height, width});
    auto cr_array = py::array_t<uint8_t>({height, width});

    auto y_buf = y_array.request();
    auto cb_buf = cb_array.request();
    auto cr_buf = cr_array.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint8_t* y_dst = static_cast<uint8_t*>(y_buf.ptr);
    uint8_t* cb_dst = static_cast<uint8_t*>(cb_buf.ptr);
    uint8_t* cr_dst = static_cast<uint8_t*>(cr_buf.ptr);

    for (int y = 0; y < height; y++) {
        const uint8_t* src = src_base + y * row_bytes;
        for (int x = 0; x < width; x += 2) {
            int src_idx = x * 2;

            uint8_t u_val = src[src_idx];
            uint8_t y0_val = src[src_idx + 1];
            uint8_t v_val = src[src_idx + 2];
            uint8_t y1_val = src[src_idx + 3];

            int pixel0_idx = y * width + x;
            y_dst[pixel0_idx] = y0_val;
            cb_dst[pixel0_idx] = u_val;
            cr_dst[pixel0_idx] = v_val;

            if (x + 1 < width) {
                int pixel1_idx = y * width + x + 1;
                y_dst[pixel1_idx] = y1_val;
                cb_dst[pixel1_idx] = u_val;
                cr_dst[pixel1_idx] = v_val;
            }
        }
    }

    py::dict result;
    result["y"] = y_array;
    result["cb"] = cb_array;
    result["cr"] = cr_array;
    return result;
}

// RGB10 unpacking functions
py::array_t<uint16_t> rgb10_to_uint16(py::array_t<uint8_t> rgb_array, int width, int height,
                                       bool input_narrow_range = true, bool output_narrow_range = false, int row_bytes = -1) {
    auto buf = rgb_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D RGB10 format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = width * 4;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for RGB10 format");
    }

    auto result = py::array_t<uint16_t>({height, width, 3});
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* dst = static_cast<uint16_t*>(res_buf.ptr);

    // Range constants (hoisted out of the per-pixel loop).
    // Input is 10-bit; output is 16-bit. Narrow 16-bit is the 10-bit narrow
    // range scaled up by 64, so 64<<6 .. 940<<6 = 4096 .. 60160.
    double in_min   = input_narrow_range  ? 64.0   : 0.0;              // 10-bit narrow black
    double in_range = input_narrow_range  ? 876.0  : 1023.0;           // 10-bit narrow / full range
    double out_min   = output_narrow_range ? 64.0 * 64.0  : 0.0;       // 4096 or 0
    double out_range = output_narrow_range ? 876.0 * 64.0 : 65535.0;   // 56064 or 65535

    bool use_bitshift     = ( input_narrow_range &&  output_narrow_range);
    bool use_bitreplicate = (!input_narrow_range && !output_narrow_range);

    for (int y = 0; y < height; y++) {
        const uint32_t* src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);
        for (int x = 0; x < width; x++) {
            uint32_t word = src[x];

            // Unpack: R bits 22-31, G bits 12-21, B bits 2-11
            uint16_t r10 = (word >> 22) & 0x3FF;
            uint16_t g10 = (word >> 12) & 0x3FF;
            uint16_t b10 = (word >> 2) & 0x3FF;

            int pixel_idx = (y * width + x) * 3;

            if (use_bitshift) {
                // Both narrow: 10-bit narrow -> 16-bit narrow by shifting up 6 bits (exact inverse of packing)
                dst[pixel_idx]     = r10 << 6;
                dst[pixel_idx + 1] = g10 << 6;
                dst[pixel_idx + 2] = b10 << 6;
            } else if (use_bitreplicate) {
                // Both full: 10-bit full -> 16-bit full by bit-replication of
                // the top 6 bits into the bottom 6. Maps 1023 -> 65535 exactly,
                // bounded in [0, 65535] by construction so no clamp needed.
                dst[pixel_idx]     = (r10 << 6) | (r10 >> 4);
                dst[pixel_idx + 1] = (g10 << 6) | (g10 >> 4);
                dst[pixel_idx + 2] = (b10 << 6) | (b10 >> 4);
            } else {
                // Cross-range: normalise input to 0..1, scale to output range.
                // Allow super-whites, clamp after scaling to prevent uint16_t overflow.
                double rf = (r10 - in_min) / in_range;
                double gf = (g10 - in_min) / in_range;
                double bf = (b10 - in_min) / in_range;

                dst[pixel_idx]     = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, rf * out_range + out_min)));
                dst[pixel_idx + 1] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, gf * out_range + out_min)));
                dst[pixel_idx + 2] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, bf * out_range + out_min)));
            }
        }
    }

    return result;
}

py::array_t<float> rgb10_to_float(py::array_t<uint8_t> rgb_array, int width, int height,
                                    bool input_narrow_range = true, int row_bytes = -1) {
    auto buf = rgb_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D RGB10 format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = width * 4;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for RGB10 format");
    }

    auto result = py::array_t<float>({height, width, 3});
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    float* dst = static_cast<float*>(res_buf.ptr);

    // Input range constants. Output is always 0..1 full-range float.
    double in_min   = input_narrow_range ? 64.0  : 0.0;
    double in_range = input_narrow_range ? 876.0 : 1023.0;

    for (int y = 0; y < height; y++) {
        const uint32_t* src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);
        for (int x = 0; x < width; x++) {
            uint32_t word = src[x];

            // Unpack: R bits 22-31, G bits 12-21, B bits 2-11
            uint16_t r10 = (word >> 22) & 0x3FF;
            uint16_t g10 = (word >> 12) & 0x3FF;
            uint16_t b10 = (word >> 2) & 0x3FF;

            // Normalise 10-bit to 0..1 (allow super-whites > 1.0 to pass through)
            double rf = (r10 - in_min) / in_range;
            double gf = (g10 - in_min) / in_range;
            double bf = (b10 - in_min) / in_range;

            int pixel_idx = (y * width + x) * 3;
            dst[pixel_idx]     = static_cast<float>(rf);
            dst[pixel_idx + 1] = static_cast<float>(gf);
            dst[pixel_idx + 2] = static_cast<float>(bf);
        }
    }

    return result;
}

py::dict unpack_rgb10(py::array_t<uint8_t> rgb_array, int width, int height, int row_bytes = -1) {
    auto buf = rgb_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D RGB10 format");
    }

    if (row_bytes < 0) {
        row_bytes = width * 4;
    }

    long expected_size = (long)row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for RGB10 format");
    }

    auto r_array = py::array_t<uint16_t>({height, width});
    auto g_array = py::array_t<uint16_t>({height, width});
    auto b_array = py::array_t<uint16_t>({height, width});

    auto r_buf = r_array.request();
    auto g_buf = g_array.request();
    auto b_buf = b_array.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* r_dst = static_cast<uint16_t*>(r_buf.ptr);
    uint16_t* g_dst = static_cast<uint16_t*>(g_buf.ptr);
    uint16_t* b_dst = static_cast<uint16_t*>(b_buf.ptr);

    for (int y = 0; y < height; y++) {
        const uint32_t* src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);
        for (int x = 0; x < width; x++) {
            uint32_t word = src[x];
            int pixel_idx = y * width + x;

            // Unpack: R bits 22-31, G bits 12-21, B bits 2-11
            r_dst[pixel_idx] = (word >> 22) & 0x3FF;
            g_dst[pixel_idx] = (word >> 12) & 0x3FF;
            b_dst[pixel_idx] = (word >> 2) & 0x3FF;
        }
    }

    py::dict result;
    result["r"] = r_array;
    result["g"] = g_array;
    result["b"] = b_array;
    return result;
}

// RGB12 unpacking functions
py::array_t<uint16_t> rgb12_to_uint16(py::array_t<uint8_t> rgb_array, int width, int height,
                                       bool input_narrow_range = false, bool output_narrow_range = false, int row_bytes = -1) {
    auto buf = rgb_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D RGB12 format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = ((width + 7) / 8) * 36;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for RGB12 format");
    }

    auto result = py::array_t<uint16_t>({height, width, 3});
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* dst = static_cast<uint16_t*>(res_buf.ptr);

    // Range constants (hoisted out of the per-pixel loop).
    // Input is 12-bit; output is 16-bit. Narrow 16-bit is the 12-bit narrow
    // range scaled up by 16, so 256<<4 .. 3760<<4 = 4096 .. 60160.
    double in_min   = input_narrow_range  ? 256.0  : 0.0;              // 12-bit narrow black
    double in_range = input_narrow_range  ? 3504.0 : 4095.0;           // 12-bit narrow / full range
    double out_min   = output_narrow_range ? 256.0 * 16.0  : 0.0;      // 4096 or 0
    double out_range = output_narrow_range ? 3504.0 * 16.0 : 65535.0;  // 56064 or 65535

    bool use_bitshift     = ( input_narrow_range &&  output_narrow_range);
    bool use_bitreplicate = (!input_narrow_range && !output_narrow_range);

    for (int y = 0; y < height; y++) {
        const uint32_t* row_src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);

        for (int x = 0; x < width; x += 8) {
            int group_idx = x / 8;
            const uint32_t* group = row_src + (group_idx * 9);

            uint16_t r[8], g[8], b[8];

            // Unpack 8 pixels from 9 DWORDs (reverse of packing)
            r[0] = group[0] & 0xFFF;
            g[0] = (group[0] >> 12) & 0xFFF;
            b[0] = ((group[0] >> 24) & 0xFF) | ((group[1] & 0xF) << 8);

            r[1] = (group[1] >> 4) & 0xFFF;
            g[1] = (group[1] >> 16) & 0xFFF;
            b[1] = ((group[1] >> 28) & 0xF) | ((group[2] & 0xFF) << 4);

            r[2] = (group[2] >> 8) & 0xFFF;
            g[2] = (group[2] >> 20) & 0xFFF;
            b[2] = group[3] & 0xFFF;

            r[3] = (group[3] >> 12) & 0xFFF;
            g[3] = ((group[3] >> 24) & 0xFF) | ((group[4] & 0xF) << 8);
            b[3] = (group[4] >> 4) & 0xFFF;

            r[4] = (group[4] >> 16) & 0xFFF;
            g[4] = ((group[4] >> 28) & 0xF) | ((group[5] & 0xFF) << 4);
            b[4] = (group[5] >> 8) & 0xFFF;

            r[5] = (group[5] >> 20) & 0xFFF;
            g[5] = group[6] & 0xFFF;
            b[5] = (group[6] >> 12) & 0xFFF;

            r[6] = ((group[6] >> 24) & 0xFF) | ((group[7] & 0xF) << 8);
            g[6] = (group[7] >> 4) & 0xFFF;
            b[6] = (group[7] >> 16) & 0xFFF;

            r[7] = ((group[7] >> 28) & 0xF) | ((group[8] & 0xFF) << 4);
            g[7] = (group[8] >> 8) & 0xFFF;
            b[7] = (group[8] >> 20) & 0xFFF;

            for (int i = 0; i < 8 && (x + i) < width; i++) {
                int pixel_idx = (y * width + x + i) * 3;

                if (use_bitshift) {
                    // Both narrow: 12-bit narrow -> 16-bit narrow by shifting up 4 bits (exact inverse of packing)
                    dst[pixel_idx]     = r[i] << 4;
                    dst[pixel_idx + 1] = g[i] << 4;
                    dst[pixel_idx + 2] = b[i] << 4;
                } else if (use_bitreplicate) {
                    // Both full: 12-bit full -> 16-bit full by bit-replication of
                    // the top 4 bits into the bottom 4. Maps 4095 -> 65535 exactly,
                    // bounded in [0, 65535] by construction so no clamp needed.
                    dst[pixel_idx]     = (r[i] << 4) | (r[i] >> 8);
                    dst[pixel_idx + 1] = (g[i] << 4) | (g[i] >> 8);
                    dst[pixel_idx + 2] = (b[i] << 4) | (b[i] >> 8);
                } else {
                    // Cross-range: normalise input to 0..1, scale to output range.
                    // Allow super-whites, clamp after scaling to prevent uint16_t overflow.
                    double rf = (r[i] - in_min) / in_range;
                    double gf = (g[i] - in_min) / in_range;
                    double bf = (b[i] - in_min) / in_range;

                    dst[pixel_idx]     = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, rf * out_range + out_min)));
                    dst[pixel_idx + 1] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, gf * out_range + out_min)));
                    dst[pixel_idx + 2] = static_cast<uint16_t>(std::max(0.0, std::min(65535.0, bf * out_range + out_min)));
                }
            }
        }
    }

    return result;
}

py::array_t<float> rgb12_to_float(py::array_t<uint8_t> rgb_array, int width, int height,
                                    bool input_narrow_range = false, int row_bytes = -1) {
    auto buf = rgb_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D RGB12 format");
    }

    // Calculate row bytes if not provided (for backwards compatibility)
    if (row_bytes < 0) {
        row_bytes = ((width + 7) / 8) * 36;
    }

    long expected_size = row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for RGB12 format");
    }

    auto result = py::array_t<float>({height, width, 3});
    auto res_buf = result.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    float* dst = static_cast<float*>(res_buf.ptr);

    // Input range constants. Output is always 0..1 full-range float.
    double in_min   = input_narrow_range ? 256.0  : 0.0;
    double in_range = input_narrow_range ? 3504.0 : 4095.0;

    for (int y = 0; y < height; y++) {
        const uint32_t* row_src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);

        for (int x = 0; x < width; x += 8) {
            int group_idx = x / 8;
            const uint32_t* group = row_src + (group_idx * 9);

            uint16_t r[8], g[8], b[8];

            // Unpack 8 pixels from 9 DWORDs
            r[0] = group[0] & 0xFFF;
            g[0] = (group[0] >> 12) & 0xFFF;
            b[0] = ((group[0] >> 24) & 0xFF) | ((group[1] & 0xF) << 8);

            r[1] = (group[1] >> 4) & 0xFFF;
            g[1] = (group[1] >> 16) & 0xFFF;
            b[1] = ((group[1] >> 28) & 0xF) | ((group[2] & 0xFF) << 4);

            r[2] = (group[2] >> 8) & 0xFFF;
            g[2] = (group[2] >> 20) & 0xFFF;
            b[2] = group[3] & 0xFFF;

            r[3] = (group[3] >> 12) & 0xFFF;
            g[3] = ((group[3] >> 24) & 0xFF) | ((group[4] & 0xF) << 8);
            b[3] = (group[4] >> 4) & 0xFFF;

            r[4] = (group[4] >> 16) & 0xFFF;
            g[4] = ((group[4] >> 28) & 0xF) | ((group[5] & 0xFF) << 4);
            b[4] = (group[5] >> 8) & 0xFFF;

            r[5] = (group[5] >> 20) & 0xFFF;
            g[5] = group[6] & 0xFFF;
            b[5] = (group[6] >> 12) & 0xFFF;

            r[6] = ((group[6] >> 24) & 0xFF) | ((group[7] & 0xF) << 8);
            g[6] = (group[7] >> 4) & 0xFFF;
            b[6] = (group[7] >> 16) & 0xFFF;

            r[7] = ((group[7] >> 28) & 0xF) | ((group[8] & 0xFF) << 4);
            g[7] = (group[8] >> 8) & 0xFFF;
            b[7] = (group[8] >> 20) & 0xFFF;

            for (int i = 0; i < 8 && (x + i) < width; i++) {
                // Normalise 12-bit to 0..1 (allow super-whites > 1.0 to pass through)
                double rf = (r[i] - in_min) / in_range;
                double gf = (g[i] - in_min) / in_range;
                double bf = (b[i] - in_min) / in_range;

                int pixel_idx = (y * width + x + i) * 3;
                dst[pixel_idx]     = static_cast<float>(rf);
                dst[pixel_idx + 1] = static_cast<float>(gf);
                dst[pixel_idx + 2] = static_cast<float>(bf);
            }
        }
    }

    return result;
}

py::dict unpack_rgb12(py::array_t<uint8_t> rgb_array, int width, int height, int row_bytes = -1) {
    auto buf = rgb_array.request();

    if (buf.ndim != 1) {
        throw std::runtime_error("Input array must be 1D RGB12 format");
    }

    if (row_bytes < 0) {
        row_bytes = ((width + 7) / 8) * 36;
    }

    long expected_size = (long)row_bytes * height;
    if (buf.size < expected_size) {
        throw std::runtime_error("Input array size too small for RGB12 format");
    }

    auto r_array = py::array_t<uint16_t>({height, width});
    auto g_array = py::array_t<uint16_t>({height, width});
    auto b_array = py::array_t<uint16_t>({height, width});

    auto r_buf = r_array.request();
    auto g_buf = g_array.request();
    auto b_buf = b_array.request();

    const uint8_t* src_base = static_cast<const uint8_t*>(buf.ptr);
    uint16_t* r_dst = static_cast<uint16_t*>(r_buf.ptr);
    uint16_t* g_dst = static_cast<uint16_t*>(g_buf.ptr);
    uint16_t* b_dst = static_cast<uint16_t*>(b_buf.ptr);

    for (int y = 0; y < height; y++) {
        const uint32_t* row_src = reinterpret_cast<const uint32_t*>(src_base + y * row_bytes);

        for (int x = 0; x < width; x += 8) {
            int group_idx = x / 8;
            const uint32_t* group = row_src + (group_idx * 9);

            uint16_t r[8], g[8], b[8];

            // Unpack 8 pixels from 9 DWORDs
            r[0] = group[0] & 0xFFF;
            g[0] = (group[0] >> 12) & 0xFFF;
            b[0] = ((group[0] >> 24) & 0xFF) | ((group[1] & 0xF) << 8);

            r[1] = (group[1] >> 4) & 0xFFF;
            g[1] = (group[1] >> 16) & 0xFFF;
            b[1] = ((group[1] >> 28) & 0xF) | ((group[2] & 0xFF) << 4);

            r[2] = (group[2] >> 8) & 0xFFF;
            g[2] = (group[2] >> 20) & 0xFFF;
            b[2] = group[3] & 0xFFF;

            r[3] = (group[3] >> 12) & 0xFFF;
            g[3] = ((group[3] >> 24) & 0xFF) | ((group[4] & 0xF) << 8);
            b[3] = (group[4] >> 4) & 0xFFF;

            r[4] = (group[4] >> 16) & 0xFFF;
            g[4] = ((group[4] >> 28) & 0xF) | ((group[5] & 0xFF) << 4);
            b[4] = (group[5] >> 8) & 0xFFF;

            r[5] = (group[5] >> 20) & 0xFFF;
            g[5] = group[6] & 0xFFF;
            b[5] = (group[6] >> 12) & 0xFFF;

            r[6] = ((group[6] >> 24) & 0xFF) | ((group[7] & 0xF) << 8);
            g[6] = (group[7] >> 4) & 0xFFF;
            b[6] = (group[7] >> 16) & 0xFFF;

            r[7] = ((group[7] >> 28) & 0xF) | ((group[8] & 0xFF) << 4);
            g[7] = (group[8] >> 8) & 0xFFF;
            b[7] = (group[8] >> 20) & 0xFFF;

            for (int i = 0; i < 8 && (x + i) < width; i++) {
                int pixel_idx = y * width + x + i;
                r_dst[pixel_idx] = r[i];
                g_dst[pixel_idx] = g[i];
                b_dst[pixel_idx] = b[i];
            }
        }
    }

    py::dict result;
    result["r"] = r_array;
    result["g"] = g_array;
    result["b"] = b_array;
    return result;
}

PYBIND11_MODULE(decklink_io, m) {
    m.doc() = "Python bindings for Blackmagic DeckLink video I/O";

    // Enums
    py::enum_<DeckLinkOutput::PixelFormat>(m, "PixelFormat")
        .value("BGRA", DeckLinkOutput::PixelFormat::Format8BitBGRA)
        .value("YUV8", DeckLinkOutput::PixelFormat::Format8BitYUV)
        .value("YUV10", DeckLinkOutput::PixelFormat::Format10BitYUV)
        .value("RGB10", DeckLinkOutput::PixelFormat::Format10BitRGB)
        .value("RGB12", DeckLinkOutput::PixelFormat::Format12BitRGB);

    py::enum_<DeckLinkOutput::DisplayMode>(m, "DisplayMode")
        // SD Modes
        .value("NTSC", DeckLinkOutput::DisplayMode::NTSC)
        .value("NTSC2398", DeckLinkOutput::DisplayMode::NTSC2398)
        .value("PAL", DeckLinkOutput::DisplayMode::PAL)
        .value("NTSCp", DeckLinkOutput::DisplayMode::NTSCp)
        .value("PALp", DeckLinkOutput::DisplayMode::PALp)

        // HD 1080 Progressive
        .value("HD1080p2398", DeckLinkOutput::DisplayMode::HD1080p2398)
        .value("HD1080p24", DeckLinkOutput::DisplayMode::HD1080p24)
        .value("HD1080p25", DeckLinkOutput::DisplayMode::HD1080p25)
        .value("HD1080p2997", DeckLinkOutput::DisplayMode::HD1080p2997)
        .value("HD1080p30", DeckLinkOutput::DisplayMode::HD1080p30)
        .value("HD1080p4795", DeckLinkOutput::DisplayMode::HD1080p4795)
        .value("HD1080p48", DeckLinkOutput::DisplayMode::HD1080p48)
        .value("HD1080p50", DeckLinkOutput::DisplayMode::HD1080p50)
        .value("HD1080p5994", DeckLinkOutput::DisplayMode::HD1080p5994)
        .value("HD1080p60", DeckLinkOutput::DisplayMode::HD1080p60)
        .value("HD1080p9590", DeckLinkOutput::DisplayMode::HD1080p9590)
        .value("HD1080p96", DeckLinkOutput::DisplayMode::HD1080p96)
        .value("HD1080p100", DeckLinkOutput::DisplayMode::HD1080p100)
        .value("HD1080p11988", DeckLinkOutput::DisplayMode::HD1080p11988)
        .value("HD1080p120", DeckLinkOutput::DisplayMode::HD1080p120)

        // HD 1080 Interlaced
        .value("HD1080i50", DeckLinkOutput::DisplayMode::HD1080i50)
        .value("HD1080i5994", DeckLinkOutput::DisplayMode::HD1080i5994)
        .value("HD1080i60", DeckLinkOutput::DisplayMode::HD1080i60)

        // HD 720
        .value("HD720p50", DeckLinkOutput::DisplayMode::HD720p50)
        .value("HD720p5994", DeckLinkOutput::DisplayMode::HD720p5994)
        .value("HD720p60", DeckLinkOutput::DisplayMode::HD720p60)

        // 2K
        .value("Mode2k2398", DeckLinkOutput::DisplayMode::Mode2k2398)
        .value("Mode2k24", DeckLinkOutput::DisplayMode::Mode2k24)
        .value("Mode2k25", DeckLinkOutput::DisplayMode::Mode2k25)

        // 2K DCI
        .value("Mode2kDCI2398", DeckLinkOutput::DisplayMode::Mode2kDCI2398)
        .value("Mode2kDCI24", DeckLinkOutput::DisplayMode::Mode2kDCI24)
        .value("Mode2kDCI25", DeckLinkOutput::DisplayMode::Mode2kDCI25)
        .value("Mode2kDCI2997", DeckLinkOutput::DisplayMode::Mode2kDCI2997)
        .value("Mode2kDCI30", DeckLinkOutput::DisplayMode::Mode2kDCI30)
        .value("Mode2kDCI4795", DeckLinkOutput::DisplayMode::Mode2kDCI4795)
        .value("Mode2kDCI48", DeckLinkOutput::DisplayMode::Mode2kDCI48)
        .value("Mode2kDCI50", DeckLinkOutput::DisplayMode::Mode2kDCI50)
        .value("Mode2kDCI5994", DeckLinkOutput::DisplayMode::Mode2kDCI5994)
        .value("Mode2kDCI60", DeckLinkOutput::DisplayMode::Mode2kDCI60)
        .value("Mode2kDCI9590", DeckLinkOutput::DisplayMode::Mode2kDCI9590)
        .value("Mode2kDCI96", DeckLinkOutput::DisplayMode::Mode2kDCI96)
        .value("Mode2kDCI100", DeckLinkOutput::DisplayMode::Mode2kDCI100)
        .value("Mode2kDCI11988", DeckLinkOutput::DisplayMode::Mode2kDCI11988)
        .value("Mode2kDCI120", DeckLinkOutput::DisplayMode::Mode2kDCI120)

        // 4K UHD
        .value("Mode4K2160p2398", DeckLinkOutput::DisplayMode::Mode4K2160p2398)
        .value("Mode4K2160p24", DeckLinkOutput::DisplayMode::Mode4K2160p24)
        .value("Mode4K2160p25", DeckLinkOutput::DisplayMode::Mode4K2160p25)
        .value("Mode4K2160p2997", DeckLinkOutput::DisplayMode::Mode4K2160p2997)
        .value("Mode4K2160p30", DeckLinkOutput::DisplayMode::Mode4K2160p30)
        .value("Mode4K2160p4795", DeckLinkOutput::DisplayMode::Mode4K2160p4795)
        .value("Mode4K2160p48", DeckLinkOutput::DisplayMode::Mode4K2160p48)
        .value("Mode4K2160p50", DeckLinkOutput::DisplayMode::Mode4K2160p50)
        .value("Mode4K2160p5994", DeckLinkOutput::DisplayMode::Mode4K2160p5994)
        .value("Mode4K2160p60", DeckLinkOutput::DisplayMode::Mode4K2160p60)
        .value("Mode4K2160p9590", DeckLinkOutput::DisplayMode::Mode4K2160p9590)
        .value("Mode4K2160p96", DeckLinkOutput::DisplayMode::Mode4K2160p96)
        .value("Mode4K2160p100", DeckLinkOutput::DisplayMode::Mode4K2160p100)
        .value("Mode4K2160p11988", DeckLinkOutput::DisplayMode::Mode4K2160p11988)
        .value("Mode4K2160p120", DeckLinkOutput::DisplayMode::Mode4K2160p120)

        // 4K DCI
        .value("Mode4kDCI2398", DeckLinkOutput::DisplayMode::Mode4kDCI2398)
        .value("Mode4kDCI24", DeckLinkOutput::DisplayMode::Mode4kDCI24)
        .value("Mode4kDCI25", DeckLinkOutput::DisplayMode::Mode4kDCI25)
        .value("Mode4kDCI2997", DeckLinkOutput::DisplayMode::Mode4kDCI2997)
        .value("Mode4kDCI30", DeckLinkOutput::DisplayMode::Mode4kDCI30)
        .value("Mode4kDCI4795", DeckLinkOutput::DisplayMode::Mode4kDCI4795)
        .value("Mode4kDCI48", DeckLinkOutput::DisplayMode::Mode4kDCI48)
        .value("Mode4kDCI50", DeckLinkOutput::DisplayMode::Mode4kDCI50)
        .value("Mode4kDCI5994", DeckLinkOutput::DisplayMode::Mode4kDCI5994)
        .value("Mode4kDCI60", DeckLinkOutput::DisplayMode::Mode4kDCI60)
        .value("Mode4kDCI9590", DeckLinkOutput::DisplayMode::Mode4kDCI9590)
        .value("Mode4kDCI96", DeckLinkOutput::DisplayMode::Mode4kDCI96)
        .value("Mode4kDCI100", DeckLinkOutput::DisplayMode::Mode4kDCI100)
        .value("Mode4kDCI11988", DeckLinkOutput::DisplayMode::Mode4kDCI11988)
        .value("Mode4kDCI120", DeckLinkOutput::DisplayMode::Mode4kDCI120)

        // 8K UHD
        .value("Mode8K4320p2398", DeckLinkOutput::DisplayMode::Mode8K4320p2398)
        .value("Mode8K4320p24", DeckLinkOutput::DisplayMode::Mode8K4320p24)
        .value("Mode8K4320p25", DeckLinkOutput::DisplayMode::Mode8K4320p25)
        .value("Mode8K4320p2997", DeckLinkOutput::DisplayMode::Mode8K4320p2997)
        .value("Mode8K4320p30", DeckLinkOutput::DisplayMode::Mode8K4320p30)
        .value("Mode8K4320p4795", DeckLinkOutput::DisplayMode::Mode8K4320p4795)
        .value("Mode8K4320p48", DeckLinkOutput::DisplayMode::Mode8K4320p48)
        .value("Mode8K4320p50", DeckLinkOutput::DisplayMode::Mode8K4320p50)
        .value("Mode8K4320p5994", DeckLinkOutput::DisplayMode::Mode8K4320p5994)
        .value("Mode8K4320p60", DeckLinkOutput::DisplayMode::Mode8K4320p60)

        // 8K DCI
        .value("Mode8kDCI2398", DeckLinkOutput::DisplayMode::Mode8kDCI2398)
        .value("Mode8kDCI24", DeckLinkOutput::DisplayMode::Mode8kDCI24)
        .value("Mode8kDCI25", DeckLinkOutput::DisplayMode::Mode8kDCI25)
        .value("Mode8kDCI2997", DeckLinkOutput::DisplayMode::Mode8kDCI2997)
        .value("Mode8kDCI30", DeckLinkOutput::DisplayMode::Mode8kDCI30)
        .value("Mode8kDCI4795", DeckLinkOutput::DisplayMode::Mode8kDCI4795)
        .value("Mode8kDCI48", DeckLinkOutput::DisplayMode::Mode8kDCI48)
        .value("Mode8kDCI50", DeckLinkOutput::DisplayMode::Mode8kDCI50)
        .value("Mode8kDCI5994", DeckLinkOutput::DisplayMode::Mode8kDCI5994)
        .value("Mode8kDCI60", DeckLinkOutput::DisplayMode::Mode8kDCI60)

        // PC Modes
        .value("Mode640x480p60", DeckLinkOutput::DisplayMode::Mode640x480p60)
        .value("Mode800x600p60", DeckLinkOutput::DisplayMode::Mode800x600p60)
        .value("Mode1440x900p50", DeckLinkOutput::DisplayMode::Mode1440x900p50)
        .value("Mode1440x900p60", DeckLinkOutput::DisplayMode::Mode1440x900p60)
        .value("Mode1440x1080p50", DeckLinkOutput::DisplayMode::Mode1440x1080p50)
        .value("Mode1440x1080p60", DeckLinkOutput::DisplayMode::Mode1440x1080p60)
        .value("Mode1600x1200p50", DeckLinkOutput::DisplayMode::Mode1600x1200p50)
        .value("Mode1600x1200p60", DeckLinkOutput::DisplayMode::Mode1600x1200p60)
        .value("Mode1920x1200p50", DeckLinkOutput::DisplayMode::Mode1920x1200p50)
        .value("Mode1920x1200p60", DeckLinkOutput::DisplayMode::Mode1920x1200p60)
        .value("Mode1920x1440p50", DeckLinkOutput::DisplayMode::Mode1920x1440p50)
        .value("Mode1920x1440p60", DeckLinkOutput::DisplayMode::Mode1920x1440p60)
        .value("Mode2560x1440p50", DeckLinkOutput::DisplayMode::Mode2560x1440p50)
        .value("Mode2560x1440p60", DeckLinkOutput::DisplayMode::Mode2560x1440p60)
        .value("Mode2560x1600p50", DeckLinkOutput::DisplayMode::Mode2560x1600p50)
        .value("Mode2560x1600p60", DeckLinkOutput::DisplayMode::Mode2560x1600p60);

    py::enum_<DeckLinkOutput::Matrix>(m, "Matrix")
        .value("Rec601", DeckLinkOutput::Matrix::Rec601)
        .value("Rec709", DeckLinkOutput::Matrix::Rec709)
        .value("Rec2020", DeckLinkOutput::Matrix::Rec2020);

    py::enum_<DeckLinkOutput::Gamut>(m, "Gamut")
        .value("Rec601", DeckLinkOutput::Gamut::Rec601)
        .value("Rec709", DeckLinkOutput::Gamut::Rec709)
        .value("Rec2020", DeckLinkOutput::Gamut::Rec2020);

    py::enum_<DeckLinkOutput::Eotf>(m, "Eotf")
        .value("SDR", DeckLinkOutput::Eotf::SDR)
        .value("HDR_Traditional", DeckLinkOutput::Eotf::HDR_Traditional)
        .value("PQ", DeckLinkOutput::Eotf::PQ)
        .value("HLG", DeckLinkOutput::Eotf::HLG);

    py::enum_<DeckLinkInput::InputConnection>(m, "InputConnection")
        .value("SDI", DeckLinkInput::InputConnection::SDI)
        .value("HDMI", DeckLinkInput::InputConnection::HDMI)
        .value("OpticalSDI", DeckLinkInput::InputConnection::OpticalSDI)
        .value("Component", DeckLinkInput::InputConnection::Component)
        .value("Composite", DeckLinkInput::InputConnection::Composite)
        .value("SVideo", DeckLinkInput::InputConnection::SVideo);

    // HdrStaticMetadata struct
    py::class_<DeckLinkOutput::HdrStaticMetadata>(m, "HdrStaticMetadata")
        .def(py::init<>())
        .def_readwrite("display_primaries_red_x", &DeckLinkOutput::HdrStaticMetadata::displayPrimariesRedX)
        .def_readwrite("display_primaries_red_y", &DeckLinkOutput::HdrStaticMetadata::displayPrimariesRedY)
        .def_readwrite("display_primaries_green_x", &DeckLinkOutput::HdrStaticMetadata::displayPrimariesGreenX)
        .def_readwrite("display_primaries_green_y", &DeckLinkOutput::HdrStaticMetadata::displayPrimariesGreenY)
        .def_readwrite("display_primaries_blue_x", &DeckLinkOutput::HdrStaticMetadata::displayPrimariesBlueX)
        .def_readwrite("display_primaries_blue_y", &DeckLinkOutput::HdrStaticMetadata::displayPrimariesBlueY)
        .def_readwrite("white_point_x", &DeckLinkOutput::HdrStaticMetadata::whitePointX)
        .def_readwrite("white_point_y", &DeckLinkOutput::HdrStaticMetadata::whitePointY)
        .def_readwrite("max_display_mastering_luminance", &DeckLinkOutput::HdrStaticMetadata::maxMasteringLuminance)
        .def_readwrite("min_display_mastering_luminance", &DeckLinkOutput::HdrStaticMetadata::minMasteringLuminance)
        .def_readwrite("max_content_light_level", &DeckLinkOutput::HdrStaticMetadata::maxContentLightLevel)
        .def_readwrite("max_frame_average_light_level", &DeckLinkOutput::HdrStaticMetadata::maxFrameAverageLightLevel);

    // VideoSettings struct
    py::class_<DeckLinkOutput::VideoSettings>(m, "VideoSettings")
        .def(py::init<>())
        .def_readwrite("mode", &DeckLinkOutput::VideoSettings::mode)
        .def_readwrite("format", &DeckLinkOutput::VideoSettings::format)
        .def_readwrite("width", &DeckLinkOutput::VideoSettings::width)
        .def_readwrite("height", &DeckLinkOutput::VideoSettings::height)
        .def_readwrite("framerate", &DeckLinkOutput::VideoSettings::framerate)
        .def_readwrite("matrix", &DeckLinkOutput::VideoSettings::matrix)
        .def_readwrite("eotf", &DeckLinkOutput::VideoSettings::eotf);

    // OutputInfo struct
    py::class_<DeckLinkOutput::OutputInfo>(m, "OutputInfo")
        .def(py::init<>())
        .def_readwrite("display_mode", &DeckLinkOutput::OutputInfo::displayMode)
        .def_readwrite("pixel_format", &DeckLinkOutput::OutputInfo::pixelFormat)
        .def_readwrite("width", &DeckLinkOutput::OutputInfo::width)
        .def_readwrite("height", &DeckLinkOutput::OutputInfo::height)
        .def_readwrite("framerate", &DeckLinkOutput::OutputInfo::framerate)
        .def_readwrite("rgb444_mode_enabled", &DeckLinkOutput::OutputInfo::rgb444ModeEnabled)
        .def_readwrite("display_mode_name", &DeckLinkOutput::OutputInfo::displayModeName)
        .def_readwrite("pixel_format_name", &DeckLinkOutput::OutputInfo::pixelFormatName);

    // DisplayModeInfo struct
    py::class_<DeckLinkOutput::DisplayModeInfo>(m, "DisplayModeInfo")
        .def(py::init<>())
        .def_readwrite("display_mode", &DeckLinkOutput::DisplayModeInfo::displayMode)
        .def_readwrite("name", &DeckLinkOutput::DisplayModeInfo::name)
        .def_readwrite("width", &DeckLinkOutput::DisplayModeInfo::width)
        .def_readwrite("height", &DeckLinkOutput::DisplayModeInfo::height)
        .def_readwrite("framerate", &DeckLinkOutput::DisplayModeInfo::framerate);

    // DeviceCapabilities struct
    py::class_<DeckLink::DeviceCapabilities>(m, "DeviceCapabilities")
        .def(py::init<>())
        .def_readwrite("name", &DeckLink::DeviceCapabilities::name)
        .def_readwrite("supports_input", &DeckLink::DeviceCapabilities::supports_input)
        .def_readwrite("supports_output", &DeckLink::DeviceCapabilities::supports_output);

    // Main DeckLinkOutput class
    py::class_<DeckLinkOutput>(m, "DeckLinkOutput")
        .def(py::init<>())
        .def("initialize", &DeckLinkOutput::initialize,
             "Initialize DeckLink device", py::arg("device_index") = 0)
        .def("setup_output", &DeckLinkOutput::setupOutput,
             "Setup video output with specified settings")
        .def("set_frame_data", [](DeckLinkOutput& self, py::array_t<uint8_t> data) {
            auto [ptr, size] = numpy_to_raw(data);
            return self.setFrameData(ptr, size);
        }, "Set frame data from numpy array")
        .def("display_frame", &DeckLinkOutput::displayFrame, "Display the current frame synchronously")
        .def("stop_output", &DeckLinkOutput::stopOutput, "Stop video output")
        .def("cleanup", &DeckLinkOutput::cleanup, "Cleanup resources")
        .def("get_device_list", &DeckLinkOutput::getDeviceList, "Get list of available devices")
        .def("get_video_settings", &DeckLinkOutput::getVideoSettings, "Get video settings for display mode")
        .def("is_pixel_format_supported", &DeckLinkOutput::isPixelFormatSupported,
             "Check if pixel format is supported for given display mode",
             py::arg("mode"), py::arg("format"))
        .def("set_matrix", &DeckLinkOutput::setMatrix,
             "Set the Y'CbCr matrix (Rec.601/709/2020) used for YUV encoding and "
             "signalled on the wire (VPID for SDI, AVI InfoFrame for HDMI). Also "
             "default-fills HDR Static Metadata primaries / white point / mastering "
             "luminance from the matrix name; only meaningful for PQ output (the "
             "SDK zeroes the InfoFrame for HLG and SDR). Call set_static_metadata "
             "afterwards to override the defaults.",
             py::arg("matrix"))
        .def("set_eotf", &DeckLinkOutput::setEotf,
             "Set the EOTF. Setting to non-SDR triggers HDR Static Metadata "
             "InfoFrame transmission on the next emitted frame. HDMI note: "
             "BMD's HDMI driver caches the HDR Static Metadata InfoFrame, so a "
             "subsequent display_frame() call is required for HDMI consumers to "
             "see updated values mid-stream. SDI carries metadata per-frame and "
             "updates on the next frame without any extra step.",
             py::arg("eotf"))
        .def("set_static_metadata", &DeckLinkOutput::setStaticMetadata,
             "Set HDR Static Metadata (per SMPTE ST 2086 / CEA-861.3 Type 1) with "
             "explicit display primaries, white point, mastering display luminance, "
             "and content light level fields. Overrides the defaults set by "
             "set_matrix. Only meaningful for PQ output.",
             py::arg("static_metadata"))
        .def("get_current_output_info", &DeckLinkOutput::getCurrentOutputInfo, "Get current output configuration info")
        .def("get_supported_display_modes", &DeckLinkOutput::getSupportedDisplayModes, "Get list of supported display modes");

    // Utility functions
    m.def("get_device_capabilities", &DeckLink::getDeviceCapabilities,
          "Get device capabilities (name and supported input/output)",
          py::arg("device_index") = 0);

    m.def("rgb_to_bgra", &rgb_to_bgra,
          "Convert RGB numpy array to BGRA format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"));

    m.def("rgb_uint16_to_yuv10", &rgb_uint16_to_yuv10,
          "Convert R'G'B' uint16 numpy array to 10-bit Y'CbCr v210 format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = false,
          py::arg("output_narrow_range") = true);

    m.def("rgb_float_to_yuv10", &rgb_float_to_yuv10,
          "Convert R'G'B' float numpy array to 10-bit Y'CbCr v210 format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("output_narrow_range") = true);

    m.def("rgb_uint16_to_rgb10", &rgb_uint16_to_rgb10,
          "Convert R'G'B' uint16 numpy array to 10-bit R'G'B' r210 format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("input_narrow_range") = true,
          py::arg("output_narrow_range") = true);

    m.def("rgb_float_to_rgb10", &rgb_float_to_rgb10,
          "Convert R'G'B' float numpy array to 10-bit R'G'B' r210 format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("output_narrow_range") = true);

    m.def("rgb_uint16_to_rgb12", &rgb_uint16_to_rgb12,
          "Convert R'G'B' uint16 numpy array to 12-bit R'G'B' format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("input_narrow_range") = false, py::arg("output_narrow_range") = false);

    m.def("rgb_float_to_rgb12", &rgb_float_to_rgb12,
          "Convert R'G'B' float numpy array to 12-bit R'G'B' format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("output_narrow_range") = false);

    m.def("yuv10_to_rgb_uint16", &yuv10_to_rgb_uint16,
          "Convert 10-bit Y'CbCr v210 format to R'G'B' uint16 numpy array",
          py::arg("yuv_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = true,
          py::arg("output_narrow_range") = false,
          py::arg("row_bytes") = -1);

    m.def("yuv10_to_rgb_float", &yuv10_to_rgb_float,
          "Convert 10-bit Y'CbCr v210 format to R'G'B' float numpy array",
          py::arg("yuv_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = true,
          py::arg("row_bytes") = -1);

    m.def("unpack_v210", &unpack_v210,
          "Unpack 10-bit Y'CbCr v210 format to separate Y', Cb, Cr arrays (returns dict with 'y', 'cb', 'cr' keys)",
          py::arg("yuv_array"), py::arg("width"), py::arg("height"),
          py::arg("row_bytes") = -1);

    m.def("yuv8_to_rgb_uint16", &yuv8_to_rgb_uint16,
          "Convert 8-bit Y'CbCr 2vuy format to R'G'B' uint16 numpy array",
          py::arg("yuv_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = true,
          py::arg("output_narrow_range") = false,
          py::arg("row_bytes") = -1);

    m.def("yuv8_to_rgb_float", &yuv8_to_rgb_float,
          "Convert 8-bit Y'CbCr 2vuy format to R'G'B' float numpy array",
          py::arg("yuv_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = true,
          py::arg("row_bytes") = -1);

    m.def("rgb_uint8_to_yuv8", &rgb_uint8_to_yuv8,
          "Convert R'G'B' uint8 numpy array to 8-bit Y'CbCr 2vuy format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = false,
          py::arg("output_narrow_range") = true);

    m.def("rgb_uint16_to_yuv8", &rgb_uint16_to_yuv8,
          "Convert R'G'B' uint16 numpy array to 8-bit Y'CbCr 2vuy format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("input_narrow_range") = false,
          py::arg("output_narrow_range") = true);

    m.def("rgb_float_to_yuv8", &rgb_float_to_yuv8,
          "Convert R'G'B' float numpy array to 8-bit Y'CbCr 2vuy format",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("matrix") = DeckLinkOutput::Matrix::Rec709,
          py::arg("output_narrow_range") = true);

    m.def("unpack_2vuy", &unpack_2vuy,
          "Unpack 8-bit Y'CbCr 2vuy format to separate Y', Cb, Cr arrays (returns dict with 'y', 'cb', 'cr' keys)",
          py::arg("yuv_array"), py::arg("width"), py::arg("height"),
          py::arg("row_bytes") = -1);

    m.def("rgb10_to_uint16", &rgb10_to_uint16,
          "Convert 10-bit R'G'B' (R10l) format to R'G'B' uint16 numpy array",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("input_narrow_range") = true,
          py::arg("output_narrow_range") = false,
          py::arg("row_bytes") = -1);

    m.def("rgb10_to_float", &rgb10_to_float,
          "Convert 10-bit R'G'B' (R10l) format to R'G'B' float numpy array",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("input_narrow_range") = true,
          py::arg("row_bytes") = -1);

    m.def("unpack_rgb10", &unpack_rgb10,
          "Unpack 10-bit R'G'B' (R10l) format to separate R', G', B' arrays (returns dict with 'r', 'g', 'b' keys)",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("row_bytes") = -1);

    m.def("rgb12_to_uint16", &rgb12_to_uint16,
          "Convert 12-bit R'G'B' (R12L) format to R'G'B' uint16 numpy array",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("input_narrow_range") = false,
          py::arg("output_narrow_range") = false,
          py::arg("row_bytes") = -1);

    m.def("rgb12_to_float", &rgb12_to_float,
          "Convert 12-bit R'G'B' (R12L) format to R'G'B' float numpy array",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("input_narrow_range") = false,
          py::arg("row_bytes") = -1);

    m.def("unpack_rgb12", &unpack_rgb12,
          "Unpack 12-bit R'G'B' (R12L) format to separate R', G', B' arrays (returns dict with 'r', 'g', 'b' keys)",
          py::arg("rgb_array"), py::arg("width"), py::arg("height"),
          py::arg("row_bytes") = -1);

    // Input - CapturedFrame struct
    py::class_<DeckLinkInput::CapturedFrame>(m, "CapturedFrame")
        .def(py::init<>())
        .def_property_readonly("data", [](DeckLinkInput::CapturedFrame& frame) {
            return py::memoryview::from_memory(
                frame.data.data(),
                frame.data.size(),
                true  // read-only
            );
        })
        .def_readonly("width", &DeckLinkInput::CapturedFrame::width)
        .def_readonly("height", &DeckLinkInput::CapturedFrame::height)
        .def_readonly("row_bytes", &DeckLinkInput::CapturedFrame::rowBytes)
        .def_readonly("format", &DeckLinkInput::CapturedFrame::format)
        .def_readonly("mode", &DeckLinkInput::CapturedFrame::mode)
        .def_readonly("matrix", &DeckLinkInput::CapturedFrame::matrix)
        .def_readonly("eotf", &DeckLinkInput::CapturedFrame::eotf)
        .def_readonly("has_metadata", &DeckLinkInput::CapturedFrame::hasMetadata)
        .def_readonly("valid", &DeckLinkInput::CapturedFrame::valid)
        .def_readonly("display_primaries_red_x", &DeckLinkInput::CapturedFrame::displayPrimariesRedX)
        .def_readonly("display_primaries_red_y", &DeckLinkInput::CapturedFrame::displayPrimariesRedY)
        .def_readonly("display_primaries_green_x", &DeckLinkInput::CapturedFrame::displayPrimariesGreenX)
        .def_readonly("display_primaries_green_y", &DeckLinkInput::CapturedFrame::displayPrimariesGreenY)
        .def_readonly("display_primaries_blue_x", &DeckLinkInput::CapturedFrame::displayPrimariesBlueX)
        .def_readonly("display_primaries_blue_y", &DeckLinkInput::CapturedFrame::displayPrimariesBlueY)
        .def_readonly("has_display_primaries", &DeckLinkInput::CapturedFrame::hasDisplayPrimaries)
        .def_readonly("white_point_x", &DeckLinkInput::CapturedFrame::whitePointX)
        .def_readonly("white_point_y", &DeckLinkInput::CapturedFrame::whitePointY)
        .def_readonly("has_white_point", &DeckLinkInput::CapturedFrame::hasWhitePoint)
        .def_readonly("max_display_mastering_luminance", &DeckLinkInput::CapturedFrame::maxMasteringLuminance)
        .def_readonly("min_display_mastering_luminance", &DeckLinkInput::CapturedFrame::minMasteringLuminance)
        .def_readonly("has_mastering_luminance", &DeckLinkInput::CapturedFrame::hasMasteringLuminance)
        .def_readonly("max_content_light_level", &DeckLinkInput::CapturedFrame::maxContentLightLevel)
        .def_readonly("has_max_cll", &DeckLinkInput::CapturedFrame::hasMaxCLL)
        .def_readonly("max_frame_average_light_level", &DeckLinkInput::CapturedFrame::maxFrameAverageLightLevel)
        .def_readonly("has_max_fall", &DeckLinkInput::CapturedFrame::hasMaxFALL)
        .def_readonly("has_timecode", &DeckLinkInput::CapturedFrame::hasTimecode)
        .def_readonly("timecode_hours", &DeckLinkInput::CapturedFrame::timecodeHours)
        .def_readonly("timecode_minutes", &DeckLinkInput::CapturedFrame::timecodeMinutes)
        .def_readonly("timecode_seconds", &DeckLinkInput::CapturedFrame::timecodeSeconds)
        .def_readonly("timecode_frames", &DeckLinkInput::CapturedFrame::timecodeFrames)
        .def_readonly("timecode_is_drop_frame", &DeckLinkInput::CapturedFrame::timecodeIsDropFrame);

    // Input - DeckLinkInput class
    py::class_<DeckLinkInput>(m, "DeckLinkInput")
        .def(py::init<>())
        .def("initialize",
             [](DeckLinkInput& self, int device_index, py::object input_connection) {
                 if (input_connection.is_none()) {
                     return self.initialize(device_index, nullptr);
                 }
                 auto conn = input_connection.cast<DeckLinkInput::InputConnection>();
                 return self.initialize(device_index, &conn);
             },
             "Initialize DeckLink device for input",
             py::arg("device_index") = 0, py::arg("input_connection") = py::none())
        .def("start_capture", &DeckLinkInput::startCapture, "Start capturing with specified or auto-detected format",
             py::arg("format") = DeckLink::PixelFormat::Format10BitYUV)
        .def("capture_frame", &DeckLinkInput::captureFrame, "Capture a single frame",
             py::arg("frame"), py::arg("timeout_ms") = 5000)
        .def("stop_capture", &DeckLinkInput::stopCapture, "Stop video capture")
        .def("cleanup", &DeckLinkInput::cleanup, "Cleanup and release resources")
        .def("get_detected_format", &DeckLinkInput::getDetectedFormat, "Get the detected video format")
        .def("get_detected_pixel_format", &DeckLinkInput::getDetectedPixelFormat, "Get the detected pixel format")
        .def("get_device_list", &DeckLinkInput::getDeviceList, "Get list of DeckLink devices")
        .def("get_available_input_connections", &DeckLinkInput::getAvailableInputConnections,
             "Get available input connections for a device", py::arg("device_index") = 0)
        .def("get_video_settings", &DeckLinkInput::getVideoSettings, "Get video settings for display mode")
        .def("get_supported_display_modes", &DeckLinkInput::getSupportedDisplayModes, "Get list of supported display modes")
        .def("set_hdmi_input_dynamic_ranges", &DeckLinkInput::setHDMIInputDynamicRanges,
             "Set HDMI EDID advertised BMDDynamicRange bitmask. Default is "
             "SDR | HDR Static PQ | HDR Static HLG. Pass any combination of "
             "BMDDynamicRange bits as int64. May be called before or after "
             "initialize(); no effect on non-HDMI connections or hardware "
             "lacking IDeckLinkHDMIInputEDID.",
             py::arg("dynamic_range_mask"));

    // Version info
    m.attr("__version__") = "0.17.0b5";
}
