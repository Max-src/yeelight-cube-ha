"""Tests for the stored pixel-art format (grouping, expansion, detection)."""

from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).parents[1] / "custom_components" / "yeelight_cube"
STORAGE = runpy.run_path(ROOT / "pixel_art_storage.py")
group_pixels = STORAGE["group_pixels"]
expand_pixels = STORAGE["expand_pixels"]
is_grouped = STORAGE["is_grouped"]


class PixelArtStorageTests(unittest.TestCase):
    def test_flat_pixels_are_grouped_without_black_or_duplicates(self):
        flat = [
            {"position": 5, "color": [255, 0, 0]},
            {"position": 1, "color": [255, 0, 0]},
            {"position": 5, "color": [0, 255, 0]},  # duplicate: the last wins
            {"position": 7, "color": [0, 0, 0]},  # black: background
            {"position": 3, "color": [0, 255, 0]},
        ]
        self.assertEqual(
            group_pixels(flat),
            [
                {"color": [255, 0, 0], "position": [1]},
                {"color": [0, 255, 0], "position": [3, 5]},
            ],
        )

    def test_a_position_keeps_its_last_color_as_the_lamp_shows_it(self):
        # light_render draws the last definition of a position (a later black
        # clears it): saved and loaded again, the drawing reads the same.
        flat = [
            {"position": 2, "color": [9, 9, 9]},
            {"position": 2, "color": [0, 0, 0]},
            {"position": 4, "color": [1, 1, 1]},
            {"position": [4, 6], "color": [5, 5, 5]},
        ]
        self.assertEqual(group_pixels(flat), [{"color": [5, 5, 5], "position": [4, 6]}])

    def test_legacy_positions_key_is_grouped(self):
        legacy = [{"color": [1, 2, 3], "positions": [9, 4]}]
        self.assertEqual(group_pixels(legacy), [{"color": [1, 2, 3], "position": [4, 9]}])
        self.assertFalse(is_grouped(legacy))

    def test_expand_round_trips_grouped_pixels(self):
        grouped = [{"color": [1, 2, 3], "position": [4, 9]}]
        flat = expand_pixels(grouped)
        self.assertEqual(
            flat,
            [{"position": 4, "color": [1, 2, 3]}, {"position": 9, "color": [1, 2, 3]}],
        )
        self.assertEqual(group_pixels(flat), grouped)

    def test_grouped_detection(self):
        self.assertTrue(is_grouped([{"color": [1, 2, 3], "position": [1]}]))
        self.assertTrue(is_grouped([]))  # nothing to convert
        self.assertFalse(is_grouped([{"color": [1, 2, 3], "position": 1}]))


if __name__ == "__main__":
    unittest.main()
