"""The lamp actions' targets, through Home Assistant's own action calls: an
entity_id in the data (one id or a list, as the cards, scripts and
automations send it) works as before, and a target (a device, an area)
reaches this integration's lights only. A call that reaches no lamp gets
the integration's own error."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_get_all_descriptions
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yeelight_cube.const import DOMAIN
# Through light.py, as __init__.py imports it (light_services needs it loaded).
from custom_components.yeelight_cube.light import async_setup_light_services


def _lamp(entity_id):
    """A set-up light, as the actions use it."""
    return SimpleNamespace(
        entity_id=entity_id,
        lamp_client=SimpleNamespace(force_tcp=Mock(), transport="tcp"),
        async_write_ha_state=Mock(),
        stop_effect_rotation=Mock(),
    )


@pytest.fixture
async def lamps(hass):
    """Two lamps in the living room, each on its own device; there too, the
    first lamp's sensor and another integration's light. A third device
    of the integration, in the kitchen, has no light."""
    hass.data.setdefault(DOMAIN, {})
    async_setup_light_services(hass)
    areas = ar.async_get(hass)
    living, kitchen = areas.async_create("Living room"), areas.async_create("Kitchen")
    devices, entities = dr.async_get(hass), er.async_get(hass)
    found = {"living": living.id, "kitchen": kitchen.id}
    for name in ("a", "b"):
        entry = MockConfigEntry(domain=DOMAIN, data={"ip": f"192.0.2.{len(found)}"})
        entry.add_to_hass(hass)
        device = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, name)})
        devices.async_update_device(device.id, area_id=living.id)
        light = entities.async_get_or_create(
            "light", DOMAIN, name, suggested_object_id=f"cube_{name}",
            config_entry=entry, device_id=device.id,
        )
        entry.runtime_data = SimpleNamespace(light=_lamp(light.entity_id))
        found[name] = entry.runtime_data.light
        found[f"device_{name}"] = device.id
        if name == "a":
            entities.async_get_or_create(
                "sensor", DOMAIN, "a_power", suggested_object_id="cube_a_power",
                config_entry=entry, device_id=device.id,
            )
    other = entities.async_get_or_create("light", "hue", "x", suggested_object_id="ceiling")
    entities.async_update_entity(other.entity_id, area_id=living.id)
    empty = MockConfigEntry(domain=DOMAIN, data={"ip": "192.0.2.9"})
    empty.add_to_hass(hass)
    device = devices.async_get_or_create(config_entry_id=empty.entry_id, identifiers={(DOMAIN, "c")})
    devices.async_update_device(device.id, area_id=kitchen.id)
    found["device_c"] = device.id
    return found


async def _force_tcp(hass, data=None, target=None):
    return await hass.services.async_call(
        DOMAIN, "force_tcp", {"minutes": 1, **(data or {})}, target=target,
        blocking=True, return_response=True,
    )


async def test_an_entity_id_in_the_data_works_as_before(hass, lamps):
    a, b = lamps["a"], lamps["b"]
    assert await _force_tcp(hass, {"entity_id": a.entity_id}) == {a.entity_id: "tcp"}
    a.lamp_client.force_tcp.assert_called_once_with(60)
    b.lamp_client.force_tcp.assert_not_called()
    # A list, as the cards send it: every lamp, in its order.
    assert list(await _force_tcp(hass, {"entity_id": [b.entity_id, a.entity_id]})) == [b.entity_id, a.entity_id]
    # A lamp of the list that is not set up is skipped.
    assert await _force_tcp(hass, {"entity_id": ["light.gone", b.entity_id]}) == {b.entity_id: "tcp"}
    # An action without a response, a list in the data.
    await hass.services.async_call(
        DOMAIN, "stop_effect_rotation", {"entity_id": [a.entity_id, b.entity_id]}, blocking=True
    )
    a.stop_effect_rotation.assert_called_once_with()
    b.stop_effect_rotation.assert_called_once_with()


async def test_a_target_entity_works_like_the_data(hass, lamps):
    a = lamps["a"]
    assert await _force_tcp(hass, target={"entity_id": a.entity_id}) == {a.entity_id: "tcp"}


async def test_a_device_or_area_reaches_only_this_integrations_lights(hass, lamps):
    a, b = lamps["a"], lamps["b"]
    # Not the lamp's sensor, not the other integration's light.
    assert await _force_tcp(hass, target={"area_id": lamps["living"]}) == {a.entity_id: "tcp", b.entity_id: "tcp"}
    assert await _force_tcp(hass, target={"device_id": lamps["device_b"]}) == {b.entity_id: "tcp"}
    await hass.services.async_call(
        DOMAIN, "stop_effect_rotation", target={"device_id": [lamps["device_a"]]}, blocking=True
    )
    a.stop_effect_rotation.assert_called_once_with()
    b.stop_effect_rotation.assert_not_called()


async def test_a_target_reaching_no_lamp_gets_the_unknown_lamp_error(hass, lamps):
    errors = []
    for data, target in (
        ({"entity_id": "light.gone"}, None),  # as before
        ({"entity_id": "light.ceiling"}, None),  # another integration's light
        (None, {"area_id": lamps["kitchen"]}),  # a device without a light
        (None, {"device_id": lamps["device_c"]}),
    ):
        with pytest.raises(ServiceValidationError) as error:
            await _force_tcp(hass, data, target)
        errors.append(error.value.translation_key)
    assert errors == ["lamp_not_found"] * 4
    with pytest.raises(ServiceValidationError) as error:
        await _force_tcp(hass)
    assert error.value.translation_key == "no_target"
    # An entity id that is not one is refused by the schema, as before.
    with pytest.raises(vol.Invalid):
        await _force_tcp(hass, {"entity_id": "not an id"})
    for lamp in (lamps["a"], lamps["b"]):
        lamp.lamp_client.force_tcp.assert_not_called()


async def test_the_actions_describe_a_target_instead_of_an_entity_field(hass, lamps):
    descriptions = (await async_get_all_descriptions(hass))[DOMAIN]
    for name in ("force_tcp", "stop_effect_rotation", "set_custom_text", "load_palette"):
        assert descriptions[name]["target"] == {"entity": [{"integration": DOMAIN, "domain": ["light"]}]}, name
        assert "entity_id" not in descriptions[name].get("fields", {}), name
    # The actions that target no lamp are as they were.
    assert "target" not in descriptions["save_pixel_art"]


async def test_font_alignment_and_orientation_reach_every_lamp_of_an_area(hass, lamps):
    a, b = lamps["a"], lamps["b"]
    for lamp in (a, b):
        lamp.set_font, lamp.set_alignment, lamp.set_orientation = AsyncMock(), AsyncMock(), AsyncMock()
    area = {"area_id": lamps["living"]}
    await hass.services.async_call(DOMAIN, "set_font", {"font": "basic"}, target=area, blocking=True)
    await hass.services.async_call(DOMAIN, "set_alignment", {"alignment": "left"}, target=area, blocking=True)
    await hass.services.async_call(DOMAIN, "set_orientation", {"orientation": "flipped"}, target=area, blocking=True)
    for lamp in (a, b):
        lamp.set_font.assert_awaited_once_with("basic")
        lamp.set_alignment.assert_awaited_once_with("left")
        lamp.set_orientation.assert_awaited_once_with("flipped")


async def test_set_brightness_reaches_every_lamp_of_an_area(hass, lamps):
    a, b = lamps["a"], lamps["b"]
    calls = []

    async def turn_on(call):
        calls.append(call.data)

    hass.services.async_register("light", "turn_on", turn_on)
    await hass.services.async_call(
        DOMAIN, "set_brightness", {"brightness": 100}, target={"area_id": lamps["living"]}, blocking=True
    )
    assert calls == [{"entity_id": [a.entity_id, b.entity_id], "brightness": 255}]


@pytest.mark.parametrize("given", ["false", "off", "0", False])
async def test_a_false_written_as_text_is_false(hass, lamps, given):
    """YAML and Node-RED send "false" as text: it is not taken for True
    (a calibration lock set by it would refuse every display command)."""
    services = hass.services.async_services()[DOMAIN]
    entity_id = lamps["a"].entity_id
    for name in ("set_color_accuracy", "set_calibration_lock"):
        assert services[name].schema({"enabled": given, "entity_id": entity_id})["enabled"] is False, name


async def test_bypass_lock_is_for_administrators(hass, lamps, hass_admin_user, hass_read_only_user):
    """bypass_lock goes through a lamp held for its calibration: a user who
    is not an administrator is refused; "false" as text is false."""
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized

    a = lamps["a"]
    a.set_brightness = AsyncMock()
    a.show_pixel_art = AsyncMock()
    services = hass.services.async_services()[DOMAIN]
    assert services["set_brightness"].schema(
        {"brightness": 50, "bypass_lock": "false", "entity_id": a.entity_id})["bypass_lock"] is False
    calls = (
        ("set_brightness", {"brightness": 50}),
        ("apply_custom_pixels", {"pixels": [{"position": 0, "color": [255, 0, 0]}]}),
    )
    for name, data in calls:
        data = {**data, "bypass_lock": True, "entity_id": a.entity_id}
        with pytest.raises(Unauthorized):
            await hass.services.async_call(
                DOMAIN, name, data, blocking=True, context=Context(user_id=hass_read_only_user.id))
        await hass.services.async_call(
            DOMAIN, name, data, blocking=True, context=Context(user_id=hass_admin_user.id))
    await hass.async_block_till_done()  # pixel arts are drawn in the background
    a.set_brightness.assert_awaited_once()
    a.show_pixel_art.assert_awaited_once()


async def test_set_solid_color_explains_a_color_it_cannot_read(hass, lamps):
    a = lamps["a"]
    a.async_set_solid_color = AsyncMock()
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN, "set_solid_color", {"rgb_color": "red", "entity_id": a.entity_id}, blocking=True)
    assert raised.value.translation_key == "hex_color_invalid"
    await hass.services.async_call(
        DOMAIN, "set_solid_color", {"rgb_color": " #00ff00", "entity_id": a.entity_id}, blocking=True)
    await hass.async_block_till_done()
    a.async_set_solid_color.assert_awaited_once_with((0, 255, 0))


async def test_a_pixel_art_that_cannot_be_read_is_answered(hass, lamps, hass_ws_client):
    """The Draw card waits for each request: an unreadable stored pixel art
    gets an error, never silence."""
    client = await hass_ws_client(hass)
    hass.data[DOMAIN]["pixel_arts"] = {"broken": True}  # not a list
    await client.send_json({"id": 1, "type": "yeelight_cube/ws_get_pixel_art_v2", "idx": 0})
    answer = await client.receive_json()
    assert (answer["success"], answer["error"]["code"]) == (False, "invalid_pixel_art")
    hass.data[DOMAIN]["pixel_arts"] = [{"name": "Heart", "pixels": [{"position": 0, "color": [255, 0, 0]}]}]
    await client.send_json({"id": 2, "type": "yeelight_cube/ws_get_pixel_art_v2", "idx": 0})
    answer = await client.receive_json()
    assert answer["success"] and answer["result"]["name"] == "Heart"


async def test_indexes_given_as_text_are_read_alike(hass, lamps):
    """YAML and Node-RED may send an index as "3": every action takes it."""
    services = hass.services.async_services()[DOMAIN]
    checks = {
        "remove_pixel_art": ("idx",), "rename_pixel_art": ("idx",), "apply_pixel_art": ("idx",),
        "move_pixel_art": ("from_idx", "to_idx"), "move_palette": ("from_idx", "to_idx"),
        "remove_palette": ("idx",),
    }
    for name, fields in checks.items():
        data = {field: "3" for field in fields}
        if name == "rename_pixel_art":
            data["name"] = "Heart"
        validated = services[name].schema(data)
        assert all(validated[field] == 3 for field in fields), name
        with pytest.raises(vol.Invalid):
            services[name].schema({**data, fields[0]: -1})
