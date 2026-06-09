"""Device selection for hardware loopback tests.

Input and output both default to device index 0 — the single duplex-device
loopback rig. For a two-device rig (e.g. an output-only Monitor and an
input-only Recorder on separate UltraStudios) override via environment
variables before running pytest:

    BMIO_OUTPUT_DEVICE=1 BMIO_INPUT_DEVICE=0 pytest tests/

Each variable is a DeckLink device index, exactly as passed to ``initialize()``.
Unset defaults to 0, so existing single-device rigs are unaffected.
"""
import os


def _device_index(env_name):
    raw = os.environ.get(env_name, "0")
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{env_name} must be an integer device index, got {raw!r}")


OUTPUT_DEVICE_INDEX = _device_index("BMIO_OUTPUT_DEVICE")
INPUT_DEVICE_INDEX = _device_index("BMIO_INPUT_DEVICE")
