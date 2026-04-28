"""Shared helpers for hardware-dependent test scripts.

Provides common CLI flags and helpers so interactive tests can be run
non-interactively as smoke tests (catch API-shape regressions without
requiring a human to watch a monitor or close a matplotlib window).
"""

import argparse
import time


def add_test_args(parser=None):
    """Add common interactive-test CLI flags to an argparse parser.

    Returns the parser. If no parser is provided, creates a fresh one.
    """
    if parser is None:
        parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Skip interactive Ctrl+C waits between test phases. Each phase "
             "holds briefly then auto-advances. Use to smoke-test the API "
             "without visual confirmation.",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Skip matplotlib visual displays of test results. Print the "
             "pass/fail summary only.",
    )
    return parser


def parse_test_args():
    """Convenience: parse the common flags and return the Namespace."""
    return add_test_args().parse_args()


def wait_or_advance(message, no_wait, hold_seconds=1.5):
    """Print message; either wait for Ctrl+C (interactive) or sleep briefly.

    With no_wait=False (default): prints message and blocks until the user
    presses Ctrl+C, then prints "Advancing..." and returns.

    With no_wait=True: prints message, sleeps `hold_seconds` to allow the
    output to propagate to the cable / monitor, then returns.
    """
    print(message)
    if no_wait:
        time.sleep(hold_seconds)
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nAdvancing...")
