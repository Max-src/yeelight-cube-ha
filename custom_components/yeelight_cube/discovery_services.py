"""Device discovery actions of the Yeelight Cube integration."""
import ipaddress
import logging
import voluptuous as vol # type: ignore
from homeassistant.core import HomeAssistant, ServiceCall, callback # type: ignore
from homeassistant.exceptions import HomeAssistantError  # type: ignore
from homeassistant.helpers import config_validation as cv # type: ignore
from homeassistant.config_entries import SOURCE_DISCOVERY, SOURCE_IGNORE # type: ignore
from .const import DOMAIN
from .discovery import is_cube_device
from .errors import failed, invalid

_LOGGER = logging.getLogger(__name__)

# Service schemas
SERVICE_TEST_DEVICE_DETECTION = "test_device_detection"
SERVICE_IGNORE_YEELIGHT_DISCOVERY = "ignore_yeelight_discovery"
SERVICE_CREATE_CUBE_DISCOVERY = "create_cube_discovery"
SERVICE_IGNORE_SPECIFIC_YEELIGHT = "ignore_specific_yeelight"

ATTR_IP_ADDRESS = "ip_address"
ATTR_DEVICE_MODEL = "device_model"
ATTR_DEVICE_NAME = "device_name"
ATTR_DEVICE_ID = "device_id"

SERVICE_TEST_DEVICE_DETECTION_SCHEMA = vol.Schema({
    vol.Optional(ATTR_DEVICE_MODEL, default=""): cv.string,
    vol.Optional(ATTR_DEVICE_NAME, default=""): cv.string,
    vol.Optional(ATTR_DEVICE_ID, default=""): cv.string,
})

SERVICE_IGNORE_YEELIGHT_DISCOVERY_SCHEMA = vol.Schema({
    vol.Required(ATTR_IP_ADDRESS): cv.string,
})

SERVICE_CREATE_CUBE_DISCOVERY_SCHEMA = vol.Schema({
    vol.Required(ATTR_IP_ADDRESS): cv.string,
    vol.Optional(ATTR_DEVICE_NAME, default=""): cv.string,
})

SERVICE_IGNORE_SPECIFIC_YEELIGHT_SCHEMA = vol.Schema({
    vol.Required(ATTR_IP_ADDRESS): cv.string,
})

# The sources of the built-in Yeelight integration's discovery flows (not a
# flow the user started).
YEELIGHT_DISCOVERY_SOURCES = (
    "discovery", "integration_discovery", "ssdp", "dhcp", "zeroconf", "homekit",
)


def yeelight_flows_at(hass: HomeAssistant, ip_address: str) -> list[dict]:
    """The built-in Yeelight integration's flows in progress for the device
    at this address: told by the address the flow shows (its ``host``), as
    their unique id is the device's id, not its address."""
    return [
        flow for flow in hass.config_entries.flow.async_progress_by_handler("yeelight")
        if (flow.get("context", {}).get("title_placeholders") or {}).get("host") == ip_address
    ]

@callback
def async_setup_services(hass: HomeAssistant):
    """Register the discovery and device-management actions."""
    async def test_device_detection(call: ServiceCall):
        """Test device detection logic with provided parameters."""
        device_model = call.data.get(ATTR_DEVICE_MODEL, "")
        device_name = call.data.get(ATTR_DEVICE_NAME, "")
        device_id = call.data.get(ATTR_DEVICE_ID, "")
        
        # Test the detection logic
        would_be_detected = is_cube_device(device_model, device_name, device_id)
        
        # Return result via event
        hass.bus.async_fire(f"{DOMAIN}_detection_test_result", {
            "device_model": device_model,
            "device_name": device_name,
            "device_id": device_id,
            "would_be_detected": would_be_detected
        })
    
    async def ignore_yeelight_discovery(call: ServiceCall):
        """Dismiss the built-in Yeelight integration's discovery of the
        device at this address (its discovery flows are aborted)."""
        ip_address = call.data[ATTR_IP_ADDRESS]

        try:
            for flow in yeelight_flows_at(hass, ip_address.strip()):
                if flow.get("context", {}).get("source") in YEELIGHT_DISCOVERY_SOURCES:
                    hass.config_entries.flow.async_abort(flow["flow_id"])
                    _LOGGER.debug("Aborted Yeelight discovery flow for %s", ip_address)
            
            # Fire success event
            hass.bus.async_fire(f"{DOMAIN}_yeelight_discovery_ignored", {
                "ip_address": ip_address,
                "success": True
            })
            
        except HomeAssistantError as e:
            _LOGGER.error("Failed to ignore Yeelight discovery for %s: %s", ip_address, e)
            hass.bus.async_fire(f"{DOMAIN}_yeelight_discovery_ignored", {
                "ip_address": ip_address,
                "success": False,
                "error": str(e)
            })
    
    async def create_cube_discovery(call: ServiceCall):
        """Offer the lamp at this address as discovered (Settings → Devices &
        services), through the config flow's discovery step, as the network
        scan does (__init__._async_ssdp_discover_cubelite)."""
        raw = call.data[ATTR_IP_ADDRESS]
        try:
            ip_address = str(ipaddress.ip_address(raw.strip()))
        except ValueError:
            ip_address = None
        error = None
        if ip_address is None:
            error = "not an IP address"
        else:
            device_name = call.data.get(ATTR_DEVICE_NAME) or f"Yeelight Cube ({ip_address})"
            try:
                # No model or hardware id: the lamp is identified by its IP
                # until it is discovered, and asked its model when it is added.
                result = await hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_DISCOVERY},
                    data={"ip": ip_address, "name": device_name},
                )
            except HomeAssistantError as e:
                error = str(e) or type(e).__name__
            else:
                if result.get("type") == "abort":
                    # already_configured, already_in_progress...
                    error = str(result.get("reason"))
        if error is not None:
            _LOGGER.error("Could not offer the lamp at %s as discovered: %s", raw, error)
            hass.bus.async_fire(f"{DOMAIN}_cube_discovery_created", {
                "ip_address": raw,
                "success": False,
                "error": error,
            })
            if ip_address is None:
                raise invalid("discovery_invalid_ip", ip=raw)
            raise failed("discovery_not_offered", ip=raw, error=error)
        _LOGGER.debug("Offered the lamp at %s as discovered", ip_address)
        hass.bus.async_fire(f"{DOMAIN}_cube_discovery_created", {
            "ip_address": ip_address,
            "device_name": device_name,
            "success": True,
        })

    async def ignore_specific_yeelight(call: ServiceCall):
        """Ignore the device at this address in the built-in Yeelight
        integration, as its Ignore button does: its discovered entry becomes
        an ignored one (Settings → Devices & services → Ignored), the other
        devices it found stay."""
        ip_address = call.data[ATTR_IP_ADDRESS].strip()
        ignored = 0
        error = None
        for flow in yeelight_flows_at(hass, ip_address):
            context = flow.get("context", {})
            if not context.get("unique_id"):
                continue
            ignore_context = {"source": SOURCE_IGNORE}
            if "discovery_key" in context:
                ignore_context["discovery_key"] = context["discovery_key"]
            try:
                await hass.config_entries.flow.async_init(
                    "yeelight",
                    context=ignore_context,
                    data={"unique_id": context["unique_id"], "title": f"Yeelight ({ip_address})"},
                )
            except HomeAssistantError as e:
                error = str(e) or type(e).__name__
                continue
            ignored += 1
        if not ignored:
            error = error or f"the Yeelight integration has no discovered device at {ip_address}"
            _LOGGER.error("Failed to ignore Yeelight device %s: %s", ip_address, error)
            hass.bus.async_fire(f"{DOMAIN}_yeelight_device_ignored", {
                "ip_address": ip_address,
                "success": False,
                "error": error,
            })
            raise failed("yeelight_not_ignored", ip=ip_address, error=error)

        _LOGGER.debug("Ignored %s in Yeelight integration", ip_address)
        hass.bus.async_fire(f"{DOMAIN}_yeelight_device_ignored", {
            "ip_address": ip_address,
            "success": True,
        })

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_TEST_DEVICE_DETECTION,
        test_device_detection,
        schema=SERVICE_TEST_DEVICE_DETECTION_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_IGNORE_YEELIGHT_DISCOVERY,
        ignore_yeelight_discovery,
        schema=SERVICE_IGNORE_YEELIGHT_DISCOVERY_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_CUBE_DISCOVERY,
        create_cube_discovery,
        schema=SERVICE_CREATE_CUBE_DISCOVERY_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_IGNORE_SPECIFIC_YEELIGHT,
        ignore_specific_yeelight,
        schema=SERVICE_IGNORE_SPECIFIC_YEELIGHT_SCHEMA,
    )
