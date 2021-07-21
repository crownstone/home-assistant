"""Helper functions for the Crownstone integration."""
from __future__ import annotations

import os


def get_serial_by_id(dev_path: str) -> str:
    """Return a /dev/serial/by-id match for given device if available."""
    by_id = "/dev/serial/by-id"
    if not os.path.isdir(by_id):
        return dev_path

    for path in (entry.path for entry in os.scandir(by_id) if entry.is_symlink()):
        if os.path.realpath(path) == dev_path:
            return path
    return dev_path


def get_port(by_id: str) -> str | None:
    """Get the port that the by-id link points to."""
    try:
        return os.path.basename(os.readlink(by_id))
    except FileNotFoundError:
        return None
