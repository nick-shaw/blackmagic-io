"""Cable-check wrapper that runs the full hardware test suite via pytest.

Confirms loopback cables are connected before invoking pytest, so the suite
doesn't run halfway and only then discover that a cable was missing. After
the cable-check, delegates to `pytest tests/` — which now runs everything in
the suite, hardware and non-hardware tests alike, with native parametrise
reporting.

REQUIRED HARDWARE SETUP
=======================

Before running this script, confirm:

  * A DeckLink device is connected and Blackmagic Desktop Video is installed.
  * SDI BNC cable: looped from SDI OUT -> SDI IN
      Used by test_loopback.py and the SDI half of test_hdr_metadata_loopback.py.
  * HDMI cable: looped from HDMI OUT -> HDMI IN
      Used by test_hdmi_bgra_loopback.py, test_hdmi_bgra_ycbcr_source.py, and
      the HDMI half of test_hdr_metadata_loopback.py.

Usage
=====

    python tests/run_all_tests.py        # interactive cable-check, then pytest
    python tests/run_all_tests.py --yes  # skip the cable-check prompt

To run pytest directly without the cable-check (e.g. once you know both cables
are in place), just invoke `pytest tests/` from the repo root.
"""

import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Hardware test suite with cable-check prompt.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive cable-check prompt.",
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed through to pytest.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Blackmagic IO - Hardware Test Suite")
    print("=" * 70)
    print()
    print("Required hardware:")
    print("  - A DeckLink device with Blackmagic Desktop Video installed")
    print("  - SDI BNC cable looped from SDI OUT -> SDI IN")
    print("  - HDMI cable looped from HDMI OUT -> HDMI IN")
    print()

    if not args.yes:
        response = input("Are both SDI and HDMI loopback cables connected? [y/N] ").strip().lower()
        if response != "y":
            print("Aborting. Connect both cables and rerun.")
            return 1

    tests_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, "-m", "pytest", tests_dir] + args.extra
    print(f"\nRunning: {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
