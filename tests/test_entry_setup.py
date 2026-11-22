"""A lamp's entry set up (__init__.async_setup_entry) when its light does
not: Home Assistant only logs a platform's error, so the entry checks that
its light was created before the platforms that use it, and is retried (a
network or lamp error, a light setup that took too long) or fails visibly (a
bug) instead of staying loaded without entities."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from tests.fakes import FakeEntry, FakeHass, module, run

INIT = module("__init__")
LIGHT = module("light")
# The classes the integration imported (one copy, however the tests are run).
BulbException, ConfigEntryNotReady = INIT.BulbException, INIT.ConfigEntryNotReady


class ConfigEntryError(Exception):
    """homeassistant.exceptions.ConfigEntryError."""


def setup_entry(light_setup):
    """async_setup_entry run with the light platform's setup replaced by
    ``light_setup(entry)`` (Home Assistant's: an error is logged, never
    raised). Returns (outcome, the platforms set up, the ones unloaded)."""
    hass = FakeHass({"yeelight_cube": {}})
    set_up, unloaded = [], []

    async def forward(entry, platforms):
        set_up.extend(platforms)
        if "light" in platforms:
            try:
                await light_setup(entry)
            except Exception:  # noqa: BLE001 -- as Home Assistant: logged only
                pass

    async def unload(entry, platforms):
        unloaded.extend(platforms)
        return True

    hass.config_entries.async_forward_entry_setups = forward
    hass.config_entries.async_unload_platforms = unload
    entry = FakeEntry("e1", data={INIT.CONF_IP: "192.0.2.10"})
    entry.async_on_unload = Mock()
    entry.add_update_listener = Mock()
    with patch.object(INIT, "async_load_storage", AsyncMock()), \
            patch.object(INIT, "_resync_entry_title"), \
            patch.object(INIT, "_async_require_reachable", AsyncMock()), \
            patch.object(INIT, "_async_store_device_id", AsyncMock()), \
            patch.object(INIT, "_async_migrate_entity_unique_ids", AsyncMock()), \
            patch.object(INIT, "_schedule_dismiss_yeelight_discoveries"), \
            patch.object(INIT, "ConfigEntryError", ConfigEntryError):
        try:
            outcome = run(INIT.async_setup_entry(hass, entry))
        except Exception as err:  # noqa: BLE001 -- the outcome under test
            outcome = err
    return outcome, set_up, unloaded, entry


def light_fails(error):
    """The light platform's own setup, its lamp read raising ``error``."""
    async def setup(entry):
        with patch.object(LIGHT, "_async_create_light", AsyncMock(side_effect=error)):
            await LIGHT.async_setup_entry(None, entry, Mock())
    return setup


class EntrySetupTests(unittest.TestCase):
    def test_a_light_set_up_lets_the_other_platforms_follow(self):
        async def light(entry):
            entry.runtime_data.light = object()

        outcome, set_up, unloaded, _ = setup_entry(light)
        self.assertIs(True, outcome)
        self.assertIn("switch", set_up)
        self.assertEqual([], unloaded)

    def test_a_network_or_lamp_error_retries_the_entry(self):
        for error in (OSError("timed out"), TimeoutError(), BulbException("refused")):
            outcome, set_up, unloaded, entry = setup_entry(light_fails(error))
            self.assertIsInstance(outcome, ConfigEntryNotReady, error)
            self.assertIs(error, outcome.__cause__)
            # Nothing else set up; the light's platform unloaded so the retry
            # can set it up again.
            self.assertEqual(["light"], set_up)
            self.assertEqual(["light"], unloaded)
            self.assertIs(error, entry.runtime_data.light_error)

    def test_a_bug_fails_the_entry_visibly(self):
        # Not retried forever as if the lamp were unreachable.
        error = KeyError("model")
        outcome, set_up, unloaded, _ = setup_entry(light_fails(error))
        self.assertIsInstance(outcome, ConfigEntryError)
        self.assertIs(error, outcome.__cause__)
        self.assertEqual((["light"], ["light"]), (set_up, unloaded))

    def test_a_light_setup_that_took_too_long_retries_and_adds_nothing_later(self):
        # Home Assistant stopped waiting (no error, no light): retried. The
        # setup ending afterwards closes its connection and adds nothing.
        late = []

        async def slow(entry):
            late.append(entry)

        outcome, set_up, unloaded, _ = setup_entry(slow)
        self.assertIsInstance(outcome, ConfigEntryNotReady)
        self.assertEqual((["light"], ["light"]), (set_up, unloaded))
        entry = late[0]
        light = SimpleNamespace(_ip="192.0.2.10", _lamp_client=Mock())
        add = Mock()
        with patch.object(LIGHT, "_async_create_light", AsyncMock(return_value=light)):
            self.assertFalse(run(LIGHT.async_setup_entry(None, entry, add)))
        add.assert_not_called()
        light._lamp_client.close.assert_called_once_with()
        self.assertIsNone(entry.runtime_data.light)
        self.assertNotIn(light, LIGHT._ENTITY_REGISTRY.values())

    def test_the_light_platform_registers_the_light_it_creates(self):
        entry = FakeEntry("e1")
        entry.runtime_data = INIT.CubeRuntimeData(active_ip="192.0.2.10")
        light = SimpleNamespace(_ip="192.0.2.77", _lamp_client=Mock())
        add = Mock()
        with patch.object(LIGHT, "_async_create_light", AsyncMock(return_value=light)), \
                patch.dict(LIGHT._ENTITY_REGISTRY):
            self.assertTrue(run(LIGHT.async_setup_entry(None, entry, add)))
            self.assertIs(light, LIGHT._ENTITY_REGISTRY["192.0.2.77"])
        add.assert_called_once_with([light], update_before_add=True)
        self.assertIs(light, entry.runtime_data.light)


if __name__ == "__main__":
    unittest.main()
