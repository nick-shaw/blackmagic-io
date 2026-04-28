#!/usr/bin/env python3
"""Smoke-run every hardware-dependent test script in non-interactive mode.

Runs each test script with the appropriate flags (--no-wait, --no-display)
to catch API regressions without requiring a human to watch a monitor or
close a matplotlib window. Aggregates pass/fail at the end.

This complements the interactive scripts: it does NOT replace visual
confirmation (colour-bar rendering correctness, narrow vs full range visual
checks, format-detection hand-eye verification, etc.). Run scripts
interactively (without --no-wait) for those.

REQUIRED HARDWARE SETUP
=======================

Before running this script, confirm:

  * A DeckLink device is connected and Blackmagic Desktop Video is installed.
  * SDI BNC cable: looped from SDI OUT → SDI IN
      Used by test_loopback.py and test_sdi_metadata_loopback.py.
  * HDMI cable: looped from HDMI OUT → HDMI IN
      Used by test_hdmi_metadata_loopback.py.

The script will prompt to confirm cables are in place before running anything.

Usage
=====

    python tests/run_all_tests.py        # interactive cable-check, then run all
    python tests/run_all_tests.py --yes  # skip the cable-check prompt
"""

import argparse
import os
import subprocess
import sys


# (script_name, args, hardware_required_summary)
TESTS = [
    ("test_device_detection.py",       [],                      "DeckLink device"),
    ("test_support_query.py",          [],                      "DeckLink device"),
    ("test_conversion_ranges.py",      [],                      "no hardware (pure unit tests)"),
    ("test_resolutions.py",            [],                      "DeckLink device"),
    ("test_rgb10_colorbars.py",        ["--no-wait"],           "DeckLink device"),
    ("test_rgb12_colorbars.py",        ["--no-wait"],           "DeckLink device"),
    ("test_loopback.py",               ["--no-display"],        "SDI BNC loopback cable"),
    ("test_sdi_metadata_loopback.py",  [],                      "SDI BNC loopback cable"),
    ("test_hdmi_metadata_loopback.py", [],                      "HDMI loopback cable"),
]


def main():
    parser = argparse.ArgumentParser(description="Smoke-run all hardware-dependent test scripts.")
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip the interactive cable-check prompt.",
    )
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))

    print("=" * 70)
    print("Blackmagic IO — Hardware Smoke Test Suite")
    print("=" * 70)
    print()
    print("Required hardware:")
    print("  - A DeckLink device with Blackmagic Desktop Video installed")
    print("  - SDI BNC cable looped from SDI OUT → SDI IN")
    print("  - HDMI cable looped from HDMI OUT → HDMI IN")
    print()

    if not args.yes:
        response = input("Are both SDI and HDMI loopback cables connected? [y/N] ").strip().lower()
        if response != "y":
            print("Aborting. Connect both cables and rerun.")
            return 1

    results = []
    for script, script_args, _ in TESTS:
        path = os.path.join(here, script)
        if not os.path.exists(path):
            print(f"\n[skip] {script} not found at {path}")
            results.append((script, None))
            continue

        print(f"\n{'=' * 70}")
        cmd_display = " ".join([script] + script_args)
        print(f"Running: {cmd_display}")
        print("=" * 70)

        try:
            result = subprocess.run([sys.executable, path] + script_args, cwd=here)
            results.append((script, result.returncode == 0))
        except KeyboardInterrupt:
            print(f"\n[interrupted] {script}")
            results.append((script, False))
            break

    print("\n" + "=" * 70)
    print("SMOKE TEST SUMMARY")
    print("=" * 70)
    for script, ok in results:
        if ok is None:
            status = "—  SKIP"
        elif ok:
            status = "✓  PASS"
        else:
            status = "✗  FAIL"
        print(f"  {status}  {script}")
    print("=" * 70)

    failed = [s for s, ok in results if ok is False]
    if failed:
        print(f"\n{len(failed)} script(s) failed.")
        return 1
    print("\nAll scripts passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
