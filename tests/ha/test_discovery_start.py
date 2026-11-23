"""The integration's setup and removal (__init__.py): the first network
scan for lamps starts at once when the integration is added while Home
Assistant runs (it waited 10 minutes for the periodic scan), and a removed
lamp's stored data goes even when no lamp loaded the storage."""
from unittest.mock import AsyncMock, patch

from homeassistant.const import EVENT_HOMEASSISTANT_STOP

import custom_components.yeelight_cube as integration


async def test_added_while_running_scans_at_once(hass):
    scan = AsyncMock()
    with patch.object(integration, "_async_ssdp_discover_cubelite", scan):
        integration._schedule_device_discovery(hass)
        await hass.async_block_till_done()
        scan.assert_awaited_once_with(hass)
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)  # its timers stop
        await hass.async_block_till_done()


async def test_removing_a_lamp_that_never_loaded_forgets_its_data(hass, hass_storage):
    """Its favourites and drawing are removed from the storage file although
    no lamp loaded it this time."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=integration.DOMAIN, data={})
    hass_storage["yeelight_cube.storage"] = {
        "version": 1, "minor_version": 1, "key": "yeelight_cube.storage",
        "data": {
            "favourites": {entry.entry_id: {"clock": []}, "other": {"clock": []}},
            "drawing": {entry.entry_id: [1, 2]},
            "names_version": 2,
        },
    }
    hass.data.pop(integration.DOMAIN, None)
    await integration.async_remove_entry(hass, entry)
    saved = hass_storage["yeelight_cube.storage"]["data"]
    assert saved["favourites"] == {"other": {"clock": []}}
    assert saved["drawing"] == {}
