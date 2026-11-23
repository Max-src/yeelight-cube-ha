"""A long text's scroll timer ends when the lamp shows something that does
not scroll (a drawing, the full panel, the background), and a card preview
never starts one (light_render._end_scroll, text_offset)."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fakes import make_light, run  # noqa: E402

LONG_TEXT = "HELLO WORLD 1234"


class _Timer:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _Loop:
    def call_later(self, delay, callback, *args):
        return _Timer()


def scrolling_light(**state):
    async def apply(*args, **kwargs):
        pass

    light = make_light(
        hass=types.SimpleNamespace(loop=_Loop()), apply=apply,
        _remember_drawing=lambda: None,
        _custom_text=LONG_TEXT, _mode="Solid Color", _scroll_enabled=True,
        _text_colors=[(255, 0, 0)], **state,
    )
    run(light._apply_display_mode_internal())
    return light


def no_scroll_left(test, light):
    test.assertIsNone(light._scroll_timer)
    test.assertFalse(light._is_scrolling)
    test.assertEqual(0, light._max_scroll_offset)
    test.assertFalse(light._lamp_client.streams_running)


class ScrollTeardownTests(unittest.TestCase):
    def test_a_long_text_scrolls(self):
        light = scrolling_light()
        self.assertIsNotNone(light._scroll_timer)
        self.assertTrue(light._is_scrolling)
        self.assertTrue(light._lamp_client.streams_running)

    def test_a_drawing_ends_the_scroll(self):
        light = scrolling_light()
        timer = light._scroll_timer
        light._custom_pixels = [{"position": 0, "color": [0, 255, 0]}]
        light._enter_mode("Custom Draw", matrix_mode="Custom Draw", custom_draw=True)
        run(light._apply_display_mode_internal())
        no_scroll_left(self, light)
        self.assertTrue(timer.cancelled)

    def test_the_full_panel_ends_the_scroll(self):
        light = scrolling_light()
        light._full_panel = True
        run(light._apply_display_mode_internal())
        no_scroll_left(self, light)

    def test_the_background_ends_the_scroll(self):
        light = scrolling_light()
        light._custom_text = ""
        run(light._apply_display_mode_internal())
        no_scroll_left(self, light)

    def test_the_scroll_switch_does_not_start_a_timer_over_a_drawing(self):
        light = scrolling_light()
        light._custom_pixels = [{"position": 0, "color": [0, 255, 0]}]
        light._enter_mode("Custom Draw", matrix_mode="Custom Draw", custom_draw=True)
        run(light._apply_display_mode_internal())
        # A card preview of the text modes reads the text, changes nothing.
        light.gradient_preview("Solid Color")
        self.assertEqual(0, light._max_scroll_offset)
        light.set_scroll_enabled(True)
        no_scroll_left(self, light)

    def test_a_preview_keeps_the_scroll_position(self):
        light = scrolling_light(_scroll_offset=3)
        before = (light._scroll_offset, light._max_scroll_offset)
        light.gradient_preview("Solid Color")
        self.assertEqual(before, (light._scroll_offset, light._max_scroll_offset))


if __name__ == "__main__":
    unittest.main()
