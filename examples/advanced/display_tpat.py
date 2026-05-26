#!/usr/bin/env python3
"""
A python utility for rendering a Test Pattern Descriptor file to Blackmagic Decklink output.

Usage: python display_tpat.py <tpat_file> <display_mode> [-p {yuv10,rgb10,rgb12,bgra}] [-r <range>] [-m <matrix>] [-e <eotf>]

The `bgra` pixel format is intended for fast preview-quality work: the
16-bit promoted image is downshifted to uint8 before output. The `-r`
flag has no effect on the BGRA wire output (the SDK's hardware
conversion produces narrow Y'CbCr 4:2:2 on SDI and full R'G'B' 4:4:4 on
HDMI regardless). For controlled output range, use yuv10 / rgb10 / rgb12.
"""

import argparse
import json
import sys
import numpy as np

import blackmagic_io as bmio
from blackmagic_io import BlackmagicOutput, DisplayMode, PixelFormat
from tpat.tpat import render_tpat

# Supported display modes. Edit this list to add others, or aliases.
DISPLAY_MODES = {
    '1080p25': DisplayMode.HD1080p25,
    '1080p2997': DisplayMode.HD1080p2997,
    '1080p30': DisplayMode.HD1080p30,
    '1080p50': DisplayMode.HD1080p50,
    '1080p5994': DisplayMode.HD1080p5994,
    '1080p60': DisplayMode.HD1080p60,
    '1080i50': DisplayMode.HD1080i50,
    '1080i5994': DisplayMode.HD1080i5994,
    '1080i60': DisplayMode.HD1080i60,
    '2160p25': DisplayMode.Mode4K2160p25,
    '2160p2997': DisplayMode.Mode4K2160p2997,
    '2160p30': DisplayMode.Mode4K2160p30,
    '2160p50': DisplayMode.Mode4K2160p50,
    '2160p5994': DisplayMode.Mode4K2160p5994,
    '2160p60': DisplayMode.Mode4K2160p60,
}

PIXEL_FORMATS = {
    'yuv10': PixelFormat.YUV10,
    'rgb10': PixelFormat.RGB10,
    'rgb12': PixelFormat.RGB12,
    'bgra': PixelFormat.BGRA,
}

MATRICES = {
    'rec709': bmio.Matrix.Rec709,
    'rec2020': bmio.Matrix.Rec2020,
}

EOTFS = {
    'sdr': bmio.Eotf.SDR,
    'hlg': bmio.Eotf.HLG,
    'pq': bmio.Eotf.PQ,
}


def main():
    """Main function for the tpat_bmd utility."""
    displaymode_options = list(DISPLAY_MODES.keys())
    pixelformat_options = ['yuv10', 'rgb10', 'rgb12', 'bgra']
    range_options = ['full', 'narrow']
    matrix_options = ['rec709', 'rec2020']
    eotf_options = ['sdr', 'hlg', 'pq']

    parser = argparse.ArgumentParser()
    parser.add_argument('tpat_in', help="input T-PAT file")
    parser.add_argument('display_mode',
                        choices=displaymode_options,
                        type=str.lower,
                        help="display mode"
                        )
    parser.add_argument('-p',
                        choices=pixelformat_options,
                        type=str.lower,
                        default='YUV10',
                        help="pixel format (optional) Default: YUV10"
    )
    parser.add_argument('-r',
                        choices=range_options,
                        type=str.lower,
                        default=None,
                        help="range (optional) Overrides TPAT file range tag if specified"
    )
    parser.add_argument('-m',
                        choices=matrix_options,
                        type=str.lower,
                        default=None,
                        help="matrix (optional) Overrides TPAT file matrix tag if specified"
    )
    parser.add_argument('-e',
                        choices=eotf_options,
                        type=str.lower,
                        default=None,
                        help="eotf (optional) Overrides TPAT file eotf tag if specified"
    )
    args = parser.parse_args()

    try:
        with open(args.tpat_in) as f:
            tpat_data = json.load(f)

        (image, bits, name) = render_tpat(args.tpat_in)

        # The TPAT's range tag declares what its encoded code values mean
        # (interpretation/input range). `-r` declares the desired output range.
        # When the TPAT has a range tag, `-r` overrides only the output; the
        # interpretation stays as the TPAT says. When the TPAT has no tag,
        # `-r` (or the default) provides both.
        tpat_narrow = (
            str(tpat_data['range']).lower() == 'narrow'
            if 'range' in tpat_data else None
        )
        if args.r is not None:
            output_narrow_range = str(args.r).lower() == 'narrow'
            input_narrow_range = (
                tpat_narrow if tpat_narrow is not None else output_narrow_range
            )
        else:
            input_narrow_range = tpat_narrow if tpat_narrow is not None else True
            output_narrow_range = input_narrow_range

        pixel_format = PIXEL_FORMATS.get(
            str(args.p).lower(),
            PixelFormat.YUV10
        )

        # Promote N-bit integer codes to uint16 in the canonical representation
        # for the declared input range. Narrow uses `<< (16 - bits)` (narrow at
        # N-bit IS narrow at 16-bit scaled by 2^(16-bits), exact). Full uses
        # bit-replication, which maps the per-bit-depth maximum to 65535 exactly
        # and produces correct values through RGB10 `>> 6`, RGB12 `>> 4`, and
        # YUV float `* / 65535` consumers. Unconditional `<< (16 - bits)` would
        # be wrong for full input via YUV and RGB12.
        if bits < 16:
            image = image.astype(np.uint16)
            shift = 16 - bits
            if input_narrow_range:
                image = image << shift
            else:
                image = (image << shift) | (image >> (2 * bits - 16))
        elif bits < 32:
            image = image.astype(np.uint16)

        if pixel_format == PixelFormat.BGRA:
            # BGRA wants uint8. The preceding promotion bit-replicates (full) or
            # left-shifts (narrow) 8→16, so `>> 8` recovers the original 8-bit
            # values precisely for 8-bit TPAT sources. For 10/12/16-bit sources
            # `>> 8` produces the canonical reduction (v >> 2, v >> 4, v >> 8
            # respectively) — no precision loss beyond the bit-depth downsample.
            image = (image >> 8).astype(np.uint8)

        with BlackmagicOutput() as output:

            display_mode = DISPLAY_MODES[args.display_mode]

            if args.m is not None:
                matrix_str = str(args.m).lower()
            elif 'matrix' in tpat_data:
                matrix_str = str(tpat_data['matrix']).lower()
            else:
                matrix_str = 'rec709'

            matrix = MATRICES.get(matrix_str, bmio.Matrix.Rec709)

            if args.e is not None:
                eotf_str = str(args.e).lower()
            elif 'eotf' in tpat_data:
                eotf_str = str(tpat_data['eotf']).lower()
            else:
                eotf_str = 'sdr'

            eotf_value = EOTFS.get(eotf_str, bmio.Eotf.SDR)
            eotf = {'eotf': eotf_value}

            output_narrow_range_arg = (
                None if pixel_format == PixelFormat.BGRA else output_narrow_range
            )
            output.display_static_frame(
                image,
                display_mode,
                pixel_format,
                matrix=matrix,
                hdr_metadata=eotf,
                input_narrow_range=input_narrow_range,
                output_narrow_range=output_narrow_range_arg,
            )

            print("Displaying:", name)
            input("Press Enter to stop...")

            output.display_solid_color((0.0, 0.0, 0.0), display_mode)

    except Exception as error:
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()
