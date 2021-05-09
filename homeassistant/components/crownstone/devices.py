"""Base classes for Crownstone devices."""
from __future__ import annotations

from crownstone_cloud.cloud_models.crownstones import Crownstone

from homeassistant.helpers.entity import DeviceInfo

from .const import CROWNSTONE_INCLUDE_TYPES, DOMAIN


class CrownstoneDevice:
    """Representation of a Crownstone device."""

    def __init__(self, device: Crownstone) -> None:
        """Initialize the device."""
        self.device = device

    @property
    def cloud_id(self) -> str:
        """
        Return the unique identifier for this device.

        Used as device ID and to generate unique entity ID's.
        """
        return str(self.device.cloud_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.cloud_id)},
            "name": self.device.name,
            "manufacturer": "Crownstone",
            "model": str(CROWNSTONE_INCLUDE_TYPES.get(self.device.type)),
            "sw_version": self.device.sw_version,
        }
