"""A palette music mode's run follows its whole palette (timeline_for)."""

import unittest

from tests.test_native_features import LAMP_RENDERERS

lamp_settings = LAMP_RENDERERS["lamp_settings"]
timeline_for = LAMP_RENDERERS["timeline_for"]
RED, GREEN, BLUE, WHITE = [255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]


def gather(palette):
    return lamp_settings("Music Gather", "Right", 128, None, "palette", None, 128, palette)


class PaletteTimelineTests(unittest.TestCase):
    def test_a_later_palette_colour_starts_its_own_run(self):
        # The first colour words alone are sent as colours: a later palette
        # colour only reaches the music mode's palette.
        first = gather([RED, GREEN, BLUE, BLUE, BLUE])
        second = gather([RED, GREEN, BLUE, BLUE, WHITE])
        self.assertNotEqual(first["palette"], second["palette"])
        self.assertIsNot(timeline_for(first), timeline_for(second))
        self.assertIs(timeline_for(first), timeline_for(dict(first)))
        self.assertNotEqual(
            [timeline_for(first).frame_at(render) for render in range(0, 200, 10)],
            [timeline_for(second).frame_at(render) for render in range(0, 200, 10)],
        )


if __name__ == "__main__":
    unittest.main()
