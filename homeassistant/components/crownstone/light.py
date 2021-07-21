"""Support for Crownstone devices."""
from __future__ import annotations

from functools import partial
import logging
from typing import TYPE_CHECKING, Any

from crownstone_cloud.cloud_models.crownstones import Crownstone
from crownstone_cloud.const import (
    DIMMING_ABILITY,
    SWITCHCRAFT_ABILITY,
    TAP_TO_TOGGLE_ABILITY,
)
from crownstone_cloud.exceptions import CrownstoneAbilityError
from crownstone_uart import CrownstoneUart
import numpy

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    SUPPORT_BRIGHTNESS,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ABILITY_STATE,
    CROWNSTONE_INCLUDE_TYPES,
    CROWNSTONE_SUFFIX,
    CROWNSTONE_USB,
    DOMAIN,
    SIG_CROWNSTONE_STATE_UPDATE,
    SIG_UART_STATE_CHANGE,
)
from .devices import CrownstoneDevice

if TYPE_CHECKING:
    from .entry_manager import CrownstoneEntryManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up crownstones from a config entry."""
    manager: CrownstoneEntryManager = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
    crownstone_usb_sphere_id = None

    # Look for a Crownstone USB and what sphere it belongs to
    for sphere in manager.cloud.cloud_data:
        for crownstone in sphere.crownstones:
            if crownstone.type == CROWNSTONE_USB:
                crownstone_usb_sphere_id = sphere.cloud_id

    # Add Crownstone entities that support switching/dimming
    for sphere in manager.cloud.cloud_data:
        for crownstone in sphere.crownstones:
            if crownstone.type in CROWNSTONE_INCLUDE_TYPES:
                # Crownstone can communicate with Crownstone USB
                if sphere.cloud_id == crownstone_usb_sphere_id:
                    entities.append(CrownstoneEntity(crownstone, manager.uart))
                # Crownstone can't communicate with Crownstone USB
                else:
                    entities.append(CrownstoneEntity(crownstone))

    async_add_entities(entities)


def crownstone_state_to_hass(value: int) -> int:
    """Crownstone 0..100 to hass 0..255."""
    return int(numpy.interp(value, [0, 100], [0, 255]))


def hass_to_crownstone_state(value: int) -> int:
    """Hass 0..255 to Crownstone 0..100."""
    return int(numpy.interp(value, [0, 255], [0, 100]))


class CrownstoneEntity(CrownstoneDevice, LightEntity):
    """
    Representation of a crownstone.

    Light platform is used to support dimming.
    """

    def __init__(self, crownstone_data: Crownstone, usb: CrownstoneUart = None) -> None:
        """Initialize the crownstone."""
        super().__init__(crownstone_data)
        self.usb = usb

    @property
    def name(self) -> str:
        """Return the name of this presence holder."""
        return str(self.device.name)

    @property
    def unique_id(self) -> str:
        """Return the unique id of this entity."""
        return f"{self.cloud_id}-{CROWNSTONE_SUFFIX}"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:power-socket-de"

    @property
    def brightness(self) -> int:
        """Return the brightness if dimming enabled."""
        return crownstone_state_to_hass(self.device.state)

    @property
    def is_on(self) -> bool:
        """Return if the device is on."""
        return crownstone_state_to_hass(self.device.state) > 0

    @property
    def supported_features(self) -> int:
        """Return the supported features of this Crownstone."""
        if self.device.abilities.get(DIMMING_ABILITY).is_enabled:
            return SUPPORT_BRIGHTNESS
        return 0

    @property
    def should_poll(self) -> bool:
        """Return if polling is required after switching."""
        return False

    async def async_added_to_hass(self) -> None:
        """Set up a listener when this entity is added to HA."""
        # new state received
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIG_CROWNSTONE_STATE_UPDATE, self.async_write_ha_state
            )
        )
        # updates state attributes when usb connects/disconnects
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIG_UART_STATE_CHANGE, self.async_write_ha_state
            )
        )

    @property
    def device_state_attributes(self) -> dict[str, Any]:
        """State attributes for Crownstone devices."""
        attributes: dict[str, Any] = {}
        # switch method
        if self.usb is not None and self.usb.is_ready():
            attributes["Switch Method"] = "Crownstone USB Dongle"
        else:
            attributes["Switch Method"] = "Crownstone Cloud"

        # crownstone abilities
        attributes["Dimming"] = ABILITY_STATE.get(
            self.device.abilities.get(DIMMING_ABILITY).is_enabled
        )
        attributes["Tap To Toggle"] = ABILITY_STATE.get(
            self.device.abilities.get(TAP_TO_TOGGLE_ABILITY).is_enabled
        )
        attributes["Switchcraft"] = ABILITY_STATE.get(
            self.device.abilities.get(SWITCHCRAFT_ABILITY).is_enabled
        )

        return attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on this light via dongle or cloud."""
        if ATTR_BRIGHTNESS in kwargs:
            try:
                # UART instance is not None when a USB is set up and in the same sphere
                # UART instance is ready when USB is set up and plugged in
                if self.usb is not None and self.usb.is_ready():
                    await self.hass.async_add_executor_job(
                        partial(
                            self.usb.dim_crownstone,
                            self.device.unique_id,
                            hass_to_crownstone_state(kwargs[ATTR_BRIGHTNESS]),
                        )
                    )
                else:
                    await self.device.async_set_brightness(
                        hass_to_crownstone_state(kwargs[ATTR_BRIGHTNESS])
                    )
                # set brightness
                self.device.state = hass_to_crownstone_state(kwargs[ATTR_BRIGHTNESS])
                self.async_write_ha_state()
            except CrownstoneAbilityError as ability_error:
                _LOGGER.error(ability_error)

        elif self.usb is not None and self.usb.is_ready():
            await self.hass.async_add_executor_job(
                partial(self.usb.switch_crownstone, self.device.unique_id, on=True)
            )
            # set state (in case the updates never comes in)
            self.device.state = 100
            self.async_write_ha_state()

        else:
            await self.device.async_turn_on()
            # set state (in case the updates never comes in)
            self.device.state = 100
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off this device via dongle or cloud."""
        if self.usb is not None and self.usb.is_ready():
            await self.hass.async_add_executor_job(
                partial(self.usb.switch_crownstone, self.device.unique_id, on=False)
            )

        else:
            await self.device.async_turn_off()

        # set state (in case the updates never comes in)
        self.device.state = 0
        self.async_write_ha_state()
