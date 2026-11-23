"""Entity ids that change (renamed by the user; in place from Home Assistant
2026.11, GitHub issue #4): the services always reach the lamp under its
current id and never under an old one, and every entity class opts in to
in-place renames. The rules: docs/ENTITY_IDS.md."""
import ast
import types
import unittest
from unittest.mock import Mock

from tests.test_native_features import ROOT, _load_standalone_functions

COMMON_SOURCE = (ROOT / "light_services_common.py").read_text(encoding="utf-8")
LIFECYCLE_HOOKS = {
    "async_added_to_hass",
    "async_will_remove_from_hass",
    "async_prepare_to_add_to_hass",
}


class LampLookupTests(unittest.TestCase):
    """light_services_common: a lamp is found by its live entity_id, among
    the lamps set up (each loaded entry's runtime_data.light)."""

    def setUp(self):
        self.entries = []
        self.reached = set()  # what a call's devices and areas reach
        self.hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(
            async_entries=lambda domain=None: list(self.entries)))
        self.functions = _load_standalone_functions(
            COMMON_SOURCE,
            {"_lamps", "_lamp_for", "_named", "_target_ids", "_resolve_entity", "_resolve_entities",
             "_call_hass", "remember_services_hass"},
            {
                "DOMAIN": "yeelight_cube",
                "lamp_of": lambda entry: getattr(getattr(entry, "runtime_data", None), "light", None),
                "_INDIRECT_TARGET_KEYS": ("device_id", "area_id", "floor_id", "label_id"),
                "_indirect_entity_ids": lambda call: set(self.reached),
                "_LOGGER": Mock(),
                "_SERVICES_HASS": [],
            },
        )

    def lamp(self, ip, entity_id):
        lamp = types.SimpleNamespace(_ip=ip, entity_id=entity_id)
        # as light.async_setup_entry leaves it
        self.entries.append(types.SimpleNamespace(runtime_data=types.SimpleNamespace(light=lamp)))
        return lamp

    def call(self, entity_id=None, **target):
        data = dict(target)
        if entity_id is not None:
            data["entity_id"] = entity_id
        return types.SimpleNamespace(data=data, hass=self.hass)

    def test_a_renamed_lamp_answers_to_its_new_id_only(self):
        lamp = self.lamp("10.0.0.1", "light.cube")
        lamp.entity_id = "light.desk"  # renamed in place
        self.assertIs(self.functions["_resolve_entity"](self.call("light.desk"), "T"), lamp)
        # The old id is refused, never sent to the renamed lamp.
        with self.assertRaisesRegex(ValueError, "No matching .*light.cube"):
            self.functions["_resolve_entity"](self.call("light.cube"), "T")

    def test_a_call_without_its_hass_finds_the_lamp_through_the_registered_one(self):
        # ServiceCall.hass exists from Home Assistant 2025.1 only; the
        # integration supports 2024.12: the actions' own Home Assistant then.
        lamp = self.lamp("10.0.0.1", "light.cube")
        self.functions["remember_services_hass"](self.hass)
        call = types.SimpleNamespace(data={"entity_id": "light.cube"})
        self.assertIs(self.functions["_resolve_entity"](call, "T"), lamp)
        self.assertEqual([lamp], self.functions["_resolve_entities"](call, "T"))

    def test_two_lamps_swapping_names_never_reach_the_wrong_lamp(self):
        top = self.lamp("10.0.0.1", "light.top")
        bottom = self.lamp("10.0.0.2", "light.bottom")
        # top -> light.tmp, bottom -> light.top, top -> light.bottom
        top.entity_id = "light.tmp"
        bottom.entity_id = "light.top"
        top.entity_id = "light.bottom"
        resolve = self.functions["_resolve_entities"]
        self.assertEqual(resolve(self.call(["light.top"]), "T"), [bottom])
        self.assertEqual(resolve(self.call(["light.bottom", "light.top"]), "T"), [top, bottom])
        with self.assertRaisesRegex(ValueError, "No matching .*light.tmp"):
            resolve(self.call("light.tmp"), "T")

    def test_two_lamps_at_the_same_ip_are_both_found(self):
        # Two entries of one IP once overwrote each other (a dict by IP).
        first = self.lamp("10.0.0.1", "light.first")
        second = self.lamp("10.0.0.1", "light.second")
        resolve = self.functions["_resolve_entities"]
        self.assertEqual(resolve(self.call(["light.first", "light.second"]), "T"), [first, second])

    def test_an_unloaded_lamp_is_not_found(self):
        lamp = self.lamp("10.0.0.1", "light.cube")
        self.entries[0].runtime_data = None  # its entry unloaded
        with self.assertRaisesRegex(ValueError, "No matching .*light.cube"):
            self.functions["_resolve_entity"](self.call("light.cube"), "T")
        self.assertIsNotNone(lamp)

    def test_entity_ids_keep_their_order_and_an_unknown_one_is_skipped(self):
        a = self.lamp("10.0.0.1", "light.a")
        b = self.lamp("10.0.0.2", "light.b")
        resolve = self.functions["_resolve_entities"]
        self.assertEqual(resolve(self.call(["light.b", "light.gone", "light.a"]), "T"), [b, a])
        # The first one for a one-lamp action, as before.
        self.assertIs(self.functions["_resolve_entity"](self.call(["light.b", "light.a"]), "T"), b)
        with self.assertRaisesRegex(ValueError, "No matching .*light.gone, light.other"):
            resolve(self.call(["light.gone", "light.other"]), "T")

    def test_a_device_or_area_reaches_only_this_integrations_lamps(self):
        a = self.lamp("10.0.0.1", "light.a")
        b = self.lamp("10.0.0.2", "light.b")
        # The area also holds another integration's light and the lamp's
        # own sensor: neither is a lamp.
        self.reached = {"light.b", "light.a", "light.other_brand", "sensor.a_power"}
        resolve = self.functions["_resolve_entities"]
        self.assertEqual(resolve(self.call(area_id="living_room"), "T"), [a, b])
        self.assertEqual(resolve(self.call(device_id=["dev-a"]), "T"), [a, b])
        # Named lamps first, as given, then the others reached.
        self.assertEqual(resolve(self.call("light.b", area_id="living_room"), "T"), [b, a])

    def test_a_target_that_reaches_no_lamp_is_refused_as_an_unknown_lamp(self):
        self.lamp("10.0.0.1", "light.a")
        self.reached = {"light.other_brand"}
        for resolve in (self.functions["_resolve_entity"], self.functions["_resolve_entities"]):
            with self.assertRaisesRegex(ValueError, "No matching .*area_id kitchen"):
                resolve(self.call(area_id="kitchen"), "T")

    def test_a_call_naming_no_lamp_is_refused(self):
        self.lamp("10.0.0.1", "light.a")
        for call in (self.call(), self.call([]), self.call(area_id="none"), self.call(device_id=[])):
            with self.assertRaisesRegex(ValueError, "needs an entity_id"):
                self.functions["_resolve_entities"](call, "T")

    def test_the_lamps_are_found_through_their_entries_only(self):
        light = (ROOT / "light.py").read_text(encoding="utf-8")
        self.assertNotIn("_ENTITY_REGISTRY", light)
        self.assertIn("runtime.light = light_entity", light)
        self.assertNotIn("_ENTITY_REGISTRY", COMMON_SOURCE)


class InPlaceRenameOptInTests(unittest.TestCase):
    """Home Assistant keeps removing and re-adding an entity on a rename
    (until 2027.11) when one of the integration's classes in its hierarchy
    defines a lifecycle hook and neither it nor a subclass defines
    async_entity_id_changed. A class added later must opt in too."""

    def test_every_class_with_lifecycle_hooks_opts_in(self):
        checked = []
        for path in sorted(ROOT.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                methods = {
                    item.name: item
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if not LIFECYCLE_HOOKS & methods.keys():
                    continue
                name = f"{path.name}:{node.name}"
                checked.append(name)
                hook = methods.get("async_entity_id_changed")
                with self.subTest(cls=name):
                    self.assertIsNotNone(hook, f"{name}: no async_entity_id_changed")
                    # A plain @callback (not async) that calls the base hook.
                    self.assertIsInstance(hook, ast.FunctionDef)
                    self.assertIn("callback", [ast.unparse(d) for d in hook.decorator_list])
                    self.assertIn(
                        "super().async_entity_id_changed(old_entity_id)",
                        ast.unparse(hook),
                    )
        # The light, the shared control base (the selects, sliders and
        # switches that only listen to a topic inherit its hooks) and every
        # helper with hooks of its own (the palette and pixel art sensors share
        # sensor._CollectionSensor, their selects select._CollectionSelect).
        self.assertGreaterEqual(len(checked), 14, checked)


if __name__ == "__main__":
    unittest.main()
