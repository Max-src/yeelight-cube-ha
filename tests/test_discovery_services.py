"""The discovery actions (discovery_services.py) that start or end a
discovery flow: create_cube_discovery offers a lamp through the config
flow's own discovery step, ignore_specific_yeelight ignores the device in the
built-in Yeelight integration as its Ignore button does, and
ignore_yeelight_discovery dismisses that integration's discovery of it. The
first two say when they did nothing (their event, and an error for the
caller)."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.fakes import FakeHass, module, run

SERVICES = module("discovery_services")
# The class the integration imported (one copy, however the tests are run).
HomeAssistantError = SERVICES.HomeAssistantError
DOMAIN = "yeelight_cube"


def services(flows=(), init=None):
    """The actions registered on a hass whose flow manager has ``flows``
    in progress and answers async_init with ``init``."""
    hass = FakeHass()
    hass.config_entries.flow = SimpleNamespace(
        async_progress_by_handler=lambda handler: [flow for flow in flows if flow["handler"] == handler],
        async_init=init or AsyncMock(return_value={"type": "form", "step_id": "discovery_confirm"}),
        async_abort=lambda flow_id: None,
    )
    SERVICES.async_setup_services(hass)
    return hass


def call(hass, name, **data):
    return run(hass.registered[(DOMAIN, name)](SimpleNamespace(data=data)))


def yeelight_flow(flow_id, host, unique_id="0x0000000012345678", **context):
    return {
        "flow_id": flow_id, "handler": "yeelight",
        "context": {"source": "zeroconf", "unique_id": unique_id,
                    "title_placeholders": {"host": host, "model": "Cube"}, **context},
    }


class CreateCubeDiscoveryTests(unittest.TestCase):
    def test_the_lamp_is_offered_through_the_discovery_step(self):
        hass = services()
        call(hass, "create_cube_discovery", ip_address=" 192.168.4.139 ", device_name="")
        # The step that exists (async_step_discovery) and the key it reads.
        hass.config_entries.flow.async_init.assert_awaited_once_with(
            DOMAIN, context={"source": SERVICES.SOURCE_DISCOVERY},
            data={"ip": "192.168.4.139", "name": "Yeelight Cube (192.168.4.139)"},
        )
        self.assertEqual(
            [(f"{DOMAIN}_cube_discovery_created",
              {"ip_address": "192.168.4.139", "device_name": "Yeelight Cube (192.168.4.139)", "success": True})],
            hass.events,
        )

    def test_a_lamp_not_offered_is_a_failure(self):
        # Already set up (or being set up): the flow aborts, nothing offered.
        hass = services(init=AsyncMock(return_value={"type": "abort", "reason": "already_configured"}))
        with self.assertRaises(HomeAssistantError):
            call(hass, "create_cube_discovery", ip_address="192.168.4.139", device_name="Desk")
        [(event, data)] = hass.events
        self.assertEqual((f"{DOMAIN}_cube_discovery_created", False), (event, data["success"]))
        self.assertIn("already_configured", data["error"])
        # Not an address: no flow at all.
        hass = services()
        with self.assertRaises(HomeAssistantError):
            call(hass, "create_cube_discovery", ip_address="desk lamp", device_name="")
        hass.config_entries.flow.async_init.assert_not_awaited()
        self.assertFalse(hass.events[0][1]["success"])


class IgnoreSpecificYeelightTests(unittest.TestCase):
    def test_the_device_s_discovered_entry_becomes_an_ignored_one(self):
        flows = [
            yeelight_flow("f1", "192.168.4.139", discovery_key="key"),
            yeelight_flow("f2", "192.168.4.140", unique_id="0x0000000087654321"),  # another device: kept
            {"flow_id": "f3", "handler": "yeelight_cube",
             "context": {"unique_id": "x", "title_placeholders": {"host": "192.168.4.139"}}},
        ]
        init = AsyncMock(return_value={"type": "create_entry"})
        hass = services(flows, init)
        call(hass, "ignore_specific_yeelight", ip_address="192.168.4.139")
        # As Home Assistant's Ignore button: an ignore flow for its unique id.
        init.assert_awaited_once_with(
            "yeelight",
            context={"source": SERVICES.SOURCE_IGNORE, "discovery_key": "key"},
            data={"unique_id": "0x0000000012345678", "title": "Yeelight (192.168.4.139)"},
        )
        self.assertEqual(
            [(f"{DOMAIN}_yeelight_device_ignored", {"ip_address": "192.168.4.139", "success": True})],
            hass.events,
        )

    def test_nothing_to_ignore_is_a_failure(self):
        # Not discovered by the Yeelight integration (or not confirmable yet:
        # no unique id): it says so instead of claiming success.
        flows = [yeelight_flow("f1", "192.168.4.139", unique_id=None)]
        hass = services(flows)
        with self.assertRaises(HomeAssistantError):
            call(hass, "ignore_specific_yeelight", ip_address="192.168.4.139")
        hass.config_entries.flow.async_init.assert_not_awaited()
        [(event, data)] = hass.events
        self.assertEqual((f"{DOMAIN}_yeelight_device_ignored", False), (event, data["success"]))
        self.assertIn("192.168.4.139", data["error"])
        # No such action is called any more.
        self.assertEqual([], hass.calls)


class IgnoreYeelightDiscoveryTests(unittest.TestCase):
    def test_the_discovery_at_the_address_is_dismissed(self):
        # The flow is told by the address it shows: its unique id is the
        # device's id, which has no address in it.
        aborted = []
        flows = [
            yeelight_flow("f1", "192.168.4.139"),
            yeelight_flow("f2", "192.168.4.139", source="ssdp"),
            yeelight_flow("f3", "192.168.4.140"),  # another device: kept
            yeelight_flow("f4", "192.168.4.139", source="user"),  # started by the user: kept
            {"flow_id": "f5", "handler": "yeelight_cube",
             "context": {"source": "zeroconf", "title_placeholders": {"host": "192.168.4.139"}}},
        ]
        hass = services(flows)
        hass.config_entries.flow.async_abort = aborted.append
        call(hass, "ignore_yeelight_discovery", ip_address=" 192.168.4.139")
        self.assertEqual(["f1", "f2"], aborted)
        self.assertEqual(
            [(f"{DOMAIN}_yeelight_discovery_ignored", {"ip_address": " 192.168.4.139", "success": True})],
            hass.events,
        )

    def test_the_managed_device_actions_are_gone(self):
        hass = services()
        for name in ("add_managed_device", "remove_managed_device", "is_device_managed", "list_managed_devices"):
            self.assertNotIn((DOMAIN, name), hass.registered)
        for name in ("create_cube_discovery", "ignore_specific_yeelight", "ignore_yeelight_discovery",
                     "test_device_detection"):
            self.assertIn((DOMAIN, name), hass.registered)


if __name__ == "__main__":
    unittest.main()
