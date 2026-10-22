"""Helpers for reliable command-line output across console encodings."""

import sys
from typing import Any


def _configure_output_stream(stream: Any) -> None:
    """Flush status lines promptly and replace unrepresentable characters."""
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return

    try:
        reconfigure(errors="replace", line_buffering=True)
    except (AttributeError, OSError, TypeError, ValueError):
        # Redirected or custom streams may not support reconfiguration.
        pass


def configure_console_output() -> None:
    """Prevent CLI status output from failing on legacy console code pages."""
    _configure_output_stream(sys.stdout)
    _configure_output_stream(sys.stderr)
