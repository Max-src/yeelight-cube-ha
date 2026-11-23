"""Shared helpers, limits and schemas for the entity-facing actions.

Used by the ``light_services_<area>`` modules, which register the actions
(see :func:`light_services.async_setup_light_services`).
"""
import asyncio
import functools
import logging
import time

import voluptuous as vol  # type: ignore
from homeassistant.core import HomeAssistant  # type: ignore
from homeassistant.exceptions import Unauthorized, UnknownUser  # type: ignore
from homeassistant.helpers import config_validation as cv  # type: ignore

from .command_errors import note_command_result
from .pixel_art_storage import PIXEL_ART_ORIENTATIONS
from .errors import invalid
from .lamp_protocol import is_connection_error
from .name_utils import normalize_display_name
from .light import _entity_id_or_list
from .const import DOMAIN
from .runtime_data import lamp_of
from .light_rotation import MAX_FAVOURITE_NAME, MAX_FAVOURITES
from .device_profile import MAX_COLS

_LOGGER = logging.getLogger(__name__)

# Limits for user-supplied collections. Every client (cards, automations,
# imported files) goes through these schemas, so bad or oversized data is
# rejected up front instead of being stored and breaking a later render.
MAX_COLORS = 100
MAX_PALETTES = 500
MAX_PIXEL_ARTS = 500
MAX_PIXEL_ENTRIES = 1000
MAX_NAME_LENGTH = 100

RGB_SCHEMA = vol.All(
    vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
)
COLOR_LIST_SCHEMA = vol.All([RGB_SCHEMA], vol.Length(min=1, max=MAX_COLORS))
NAME_SCHEMA = vol.All(cv.string, vol.Length(max=MAX_NAME_LENGTH))
# Stored/exported names may be missing or null; they fall back to "Palette N"
# / "Pixel Art N".
OPTIONAL_NAME_SCHEMA = vol.Any(None, NAME_SCHEMA)
_POSITION_LIST = vol.All([cv.positive_int], vol.Length(max=MAX_PIXEL_ENTRIES))
PIXEL_ENTRY_SCHEMA = vol.Any(
    vol.Schema(
        {
            vol.Required("position"): vol.Any(cv.positive_int, _POSITION_LIST),
            vol.Required("color"): RGB_SCHEMA,
        },
        extra=vol.REMOVE_EXTRA,
    ),
    # Legacy stored/exported format used "positions" (plural).
    vol.Schema(
        {
            vol.Required("positions"): _POSITION_LIST,
            vol.Required("color"): RGB_SCHEMA,
        },
        extra=vol.REMOVE_EXTRA,
    ),
)
PIXEL_LIST_SCHEMA = vol.All([PIXEL_ENTRY_SCHEMA], vol.Length(max=MAX_PIXEL_ENTRIES))
PALETTE_SCHEMA = vol.Schema(
    {
        vol.Optional("name"): OPTIONAL_NAME_SCHEMA,
        vol.Required("colors"): COLOR_LIST_SCHEMA,
    },
    extra=vol.REMOVE_EXTRA,
)
PALETTE_LIST_SCHEMA = vol.All([PALETTE_SCHEMA], vol.Length(max=MAX_PALETTES))
FAVOURITE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): vol.All(
            cv.string, vol.Length(min=1, max=MAX_FAVOURITE_NAME)
        ),
        vol.Optional("color_mode", default="normal"): vol.All(
            cv.string, vol.Length(max=40)
        ),
        vol.Optional("color"): vol.Any(None, RGB_SCHEMA),
    },
    extra=vol.REMOVE_EXTRA,
)
FAVOURITE_LIST_SCHEMA = vol.All(
    [FAVOURITE_SCHEMA], vol.Length(max=MAX_FAVOURITES)
)
PIXEL_ART_ORIENTATION_SCHEMA = vol.In(PIXEL_ART_ORIENTATIONS)
# A pixel art's (or drawing's) width in columns: its positions are
# row * width + column (pixel_art_storage). 20 when not given; up to a Cube
# Matrix of TOPOLOGY_SLOTS modules' 40.
PIXEL_ART_WIDTH_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_COLS))
PIXEL_ART_SCHEMA = vol.Schema(
    {
        vol.Optional("name"): OPTIONAL_NAME_SCHEMA,
        vol.Required("pixels"): PIXEL_LIST_SCHEMA,
        vol.Optional("orientation"): PIXEL_ART_ORIENTATION_SCHEMA,
        vol.Optional("width"): PIXEL_ART_WIDTH_SCHEMA,
    },
    extra=vol.REMOVE_EXTRA,
)
PIXEL_ART_LIST_SCHEMA = vol.All([PIXEL_ART_SCHEMA], vol.Length(max=MAX_PIXEL_ARTS))


def _check_collection_size(current, added, limit, kind):
    """Refuse an append that would grow a shared collection (``kind``:
    "palette" or "pixel_art") past ``limit``."""
    if current + added > limit:
        raise invalid(f"{kind}s_full", limit=limit, current=current, added=added)


# The keys of a lamp action's target. The cards, scripts and automations
# name their lamps with entity_id (one id or a list, in the action's data);
# Home Assistant's target (the action editor's entity, device or area
# picker) adds the others to the data. Every lamp action's schema takes them
# all (**LAMP_TARGET_FIELDS); a call naming none of them is refused with
# no_target (_target_ids).
_INDIRECT_TARGET_KEYS = ("device_id", "area_id", "floor_id", "label_id")
_TARGET_ID_LIST = vol.Any("none", vol.All(cv.ensure_list, [cv.string]))
LAMP_TARGET_FIELDS = {
    vol.Optional("entity_id"): _entity_id_or_list,
    **{vol.Optional(key): _TARGET_ID_LIST for key in _INDIRECT_TARGET_KEYS},
}


# The Home Assistant the actions were registered with (light_services
# async_setup_light_services): what a call reaches its lamps through when the
# call does not carry it (ServiceCall.hass exists from Home Assistant 2025.1;
# the integration supports 2024.12).
_SERVICES_HASS: list = []


def remember_services_hass(hass) -> None:
    """The Home Assistant the actions run in (one per session)."""
    _SERVICES_HASS[:] = [hass]


def _call_hass(service_call):
    """The Home Assistant a service call runs in."""
    hass = getattr(service_call, "hass", None)
    if hass is None and _SERVICES_HASS:
        hass = _SERVICES_HASS[0]
    return hass


def _lamps(hass):
    """Every lamp set up: the light of each loaded entry (runtime_data)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        lamp = lamp_of(entry)
        if lamp is not None:
            yield lamp


def _lamp_for(hass, entity_id):
    """The lamp whose current entity_id is ``entity_id``, or None. Matched
    on the live id (never a stored one): a renamed lamp answers to its new
    id only."""
    for lamp in _lamps(hass):
        if getattr(lamp, "entity_id", None) == entity_id:
            return lamp
    return None


def _named(value) -> list:
    """The ids a target key names (one id or a list; "none" names none)."""
    if value is None or value == "none":
        return []
    return [item for item in (value if isinstance(value, list) else [value]) if item]


def _indirect_entity_ids(service_call) -> set:
    """The entity ids the call's devices, areas, floors and labels reach
    (Home Assistant's own expansion: hidden and config/diagnostic entities
    left out)."""
    hass = _call_hass(service_call)
    try:
        from homeassistant.helpers import target  # type: ignore
    except ImportError:  # Home Assistant before its target helpers
        target = None
    # The selection class (TargetSelection; TargetSelectorData in some releases).
    selection = getattr(target, "TargetSelection", None) or getattr(target, "TargetSelectorData", None)
    if selection is not None and hasattr(target, "async_extract_referenced_entity_ids"):
        selected = target.async_extract_referenced_entity_ids(
            hass, selection(service_call.data), expand_group=False
        )
    else:
        from homeassistant.helpers.service import (  # type: ignore
            async_extract_referenced_entity_ids,
        )

        selected = async_extract_referenced_entity_ids(hass, service_call, expand_group=False)
    return set(selected.indirectly_referenced)


def _target_ids(service_call) -> list:
    """The entity ids a service call targets, in order: its entity_id (one
    or a list, as given), then the lamps its devices, areas, floors or labels
    reach (in entity id order; only this integration's lights). Raises when
    it names none, or when its devices and areas reach no lamp and it names
    no entity either."""
    data = service_call.data
    ids = _named(data.get("entity_id"))
    indirect = {key: _named(data.get(key)) for key in _INDIRECT_TARGET_KEYS}
    if any(indirect.values()):
        lamps = {getattr(lamp, "entity_id", None) for lamp in _lamps(_call_hass(service_call))}
        reached = _indirect_entity_ids(service_call) & lamps
        ids += sorted(eid for eid in reached if eid not in ids)
        if not ids:
            named = ", ".join(
                f"{key} {', '.join(values)}" for key, values in indirect.items() if values
            )
            raise invalid("lamp_not_found", entity_id=named)
    if not ids:
        raise invalid("no_target")
    return ids


def _resolve_entity(service_call, service_name: str):
    """The lamp a service call targets (the first one of _target_ids).
    Raises a clear error when it names no lamp that is set up: the call is
    refused, never sent to another lamp."""
    entity_id = _target_ids(service_call)[0]
    target = _lamp_for(_call_hass(service_call), entity_id)
    if target is None:
        raise invalid("lamp_not_found", entity_id=entity_id)
    return target


def _resolve_entities(service_call, service_name: str):
    """Every lamp a service call targets (_target_ids), for the handlers
    that update them in parallel. One that is not set up (still starting,
    or removed) is skipped and logged; the call is refused when none is."""
    ids = _target_ids(service_call)
    results = []
    for eid in ids:
        target = _lamp_for(_call_hass(service_call), eid)
        if target is not None:
            results.append(target)
        else:
            _LOGGER.warning("[%s] Entity %s not found among the lamps", service_name, eid)
    if not results:
        raise invalid("lamp_not_found", entity_id=", ".join(map(str, ids)))
    return results


def _locate_item(items, idx, expected_name, kind):
    """Return ``items[idx]``, refusing an index that no longer matches.

    Collections are shared by every browser, so an index sent by a card may
    point at a different item once another client deleted or reordered
    entries. When ``expected_name`` is passed (the name it saw at
    that index), a mismatch is rejected instead of acting on the wrong item.
    ``kind``: "palette" or "pixel_art" (its messages).
    """
    if not (isinstance(idx, int) and 0 <= idx < len(items)):
        raise invalid(f"{kind}_gone", index=idx)
    item = items[idx]
    # Compare as stored: names are normalised on save (e.g. "<"/">" are
    # stripped), while a card may still hold the raw name it just sent.
    if expected_name is not None and (
        not isinstance(item, dict)
        or normalize_display_name(item.get("name"), "")
        != normalize_display_name(expected_name, "")
    ):
        raise invalid(f"{kind}_list_changed", name=expected_name, index=idx)
    return item


def _move_item(items, from_idx, to_idx, expected_name, kind):
    """Move ``items[from_idx]`` to ``to_idx`` in place; False when already there.

    The one reorder of the user collections (palettes, pixel arts): a card
    moves a single item, so items other clients added meanwhile are kept,
    and ``expected_name`` refuses a move whose index went stale.
    """
    _locate_item(items, from_idx, expected_name, kind)
    if not (isinstance(to_idx, int) and 0 <= to_idx < len(items)):
        raise invalid(f"{kind}_position", index=to_idx)
    if from_idx == to_idx:
        return False
    items.insert(to_idx, items.pop(from_idx))
    return True


async def require_admin(hass: HomeAssistant, service_call) -> None:
    """Refuse a call from a user who is not a Home Assistant administrator.
    Calls without a user (automations, scripts, the system) are allowed,
    matching Home Assistant's own admin services."""
    user_id = service_call.context.user_id
    if user_id:
        user = await hass.auth.async_get_user(user_id)
        if user is None:
            raise UnknownUser(context=service_call.context)
        if not user.is_admin:
            raise Unauthorized(context=service_call.context)


# bypass_lock: the action goes through while the lamp is held for its
# calibration (set_calibration_lock). Administrators only.
BYPASS_LOCK_FIELD = {vol.Optional("bypass_lock", default=False): cv.boolean}


def make_admin_only(hass: HomeAssistant):
    """Build the ``_admin_only`` handler decorator for ``hass``."""

    def _admin_only(handler):
        """Restrict a raw/diagnostic service to Home Assistant administrators.

        These services send arbitrary raw commands or take exclusive
        control of a lamp, so a non-admin user must not be able to call them.
        Calls without a user (automations, scripts, the system) are allowed,
        matching Home Assistant's own admin services.
        """

        @functools.wraps(handler)
        async def wrapper(service_call):
            await require_admin(hass, service_call)
            return await handler(service_call)

        return wrapper

    return _admin_only


def make_lamp_runner(hass: HomeAssistant):
    """Build ``run_on_lamps(label, lamps, apply)`` for ``hass``: the services'
    way to do their per-lamp work (lamp commands) in the
    background, so the service returns at once and every lamp is updated in
    parallel.

    A lamp's failure never stops the others and is logged with the service
    and the lamp: "not reached" as a warning for the first failure of an
    outage (then at debug level, like the connection layer), anything else
    as an error with its traceback, and published on the lamp for the
    cards (command_errors.note_command_result).
    """

    def run_on_lamps(label, lamps, apply):
        async def _one(lamp):
            started = time.time()
            try:
                await apply(lamp)
            except Exception as err:  # noqa: BLE001 -- one lamp never stops the others
                name = getattr(lamp, "entity_id", None) or getattr(lamp, "_ip", lamp)
                if is_connection_error(err):
                    cube = getattr(lamp, "_lamp_client", None)
                    level = (
                        cube.outage_log_level()
                        if hasattr(cube, "outage_log_level")
                        else logging.WARNING
                    )
                    _LOGGER.log(level, "[%s] [%s] Lamp not reached: %s", label, name, err)
                else:
                    _LOGGER.exception("[%s] [%s] Failed: %s", label, name, err)
                    note_command_result(lamp, label, err)
            else:
                # Not an error its own redraw recorded meanwhile (refused).
                note_command_result(lamp, label, since=started)

        async def _run():
            await asyncio.gather(*(_one(lamp) for lamp in lamps))

        hass.async_create_task(_run(), name=f"yeelight_cube {label}")

    return run_on_lamps
