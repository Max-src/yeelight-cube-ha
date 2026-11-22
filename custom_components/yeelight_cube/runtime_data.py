"""A lamp's runtime data (``entry.runtime_data``): what its platforms share
while its config entry is loaded. Home Assistant drops it when the entry
unloads. What all lamps share (the storage, the global sensors) stays in
``hass.data[DOMAIN]``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry  # type: ignore

if TYPE_CHECKING:
    from .light import YeelightCubeLight


@dataclass
class CubeRuntimeData:
    """Set by async_setup_entry (__init__.py)."""

    # The IP this setup connects to: an entry update reloads only when the
    # stored IP differs from it (_async_entry_updated).
    active_ip: str
    # The lamp's light entity, set by the light platform (set up before the
    # others, which use it: lamp_of).
    light: YeelightCubeLight | None = None
    # Why the light platform did not set up (light.async_setup_entry): Home
    # Assistant only logs a platform's error, async_setup_entry decides from
    # it whether the entry is retried.
    light_error: Exception | None = None
    # The entry gave up on its light platform (it failed or took too long):
    # a light setup still running then adds nothing.
    light_abandoned: bool = False


type CubeConfigEntry = ConfigEntry[CubeRuntimeData]


def lamp_of(entry: ConfigEntry) -> YeelightCubeLight | None:
    """The light entity of a loaded entry; None before the light platform set
    it up, or once the entry is unloaded."""
    data = getattr(entry, "runtime_data", None)
    return data.light if data is not None else None
