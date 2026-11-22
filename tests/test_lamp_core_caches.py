"""lamp_core's tables and maps are kept within a limit, as _COLOURS is, and
read the same once started again."""

import runpy
import unittest

from tests.test_native_features import ROOT


class BoundedCacheTests(unittest.TestCase):
    def setUp(self):
        self.core = runpy.run_path(str(ROOT / "lamp_core.py"))

    def test_blend_and_towards_tables_stay_within_the_limit(self):
        core = self.core
        limit = core["_TABLES_LIMIT"]
        for name, cache in (("_blend_table", "_BLENDS"), ("_towards_table", "_TOWARDS")):
            table = core[name]
            first = table(7, 200)
            for amount in range(256):
                for target in range(0, 256, 8):
                    table(amount, target)
            self.assertLessEqual(len(core[cache]), limit, name)
            self.assertEqual(first, table(7, 200), name)

    def test_pixel_maps_and_row_blur_walks_stay_within_the_limit(self):
        core = self.core
        limit = core["_MAPS_LIMIT"]
        first = core["pixel_map"](1)
        for length in range(1, limit + 40):
            core["pixel_map"](0, length=length)
        self.assertLessEqual(len(core["_READ_BACKS"]), limit)
        self.assertEqual(first, core["pixel_map"](1))
        visits = core["_row_blur_visits"]
        first = visits(4, 2, None)
        for width in range(1, limit + 40):
            visits(width, 1, None)
        self.assertLessEqual(len(core["_ROW_BLUR_VISITS"]), limit)
        self.assertEqual(first, visits(4, 2, None))


if __name__ == "__main__":
    unittest.main()
