"""The lamp's renderers (lamp_renderers.py, www/lamp-renderers.js) against
what the lamp draws: every reference frame of the lamp's Fireworks
(tests/fixtures/lamp_fireworks_frames.json.gz) must come out the same,
records and all."""

import gzip
import json
import runpy
import shutil
import subprocess
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "yeelight_cube"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lamp_fireworks_frames.json.gz"
APPEARANCE = Path(__file__).resolve().parent / "fixtures" / "lamp_led_appearance.json"
MAGIC = Path(__file__).resolve().parent / "fixtures" / "lamp_magic_frames.json"
LAMP = runpy.run_path(str(ROOT / "lamp_renderers.py"))
PREVIEW = runpy.run_path(str(ROOT / "native_effect_preview.py"))


def _runs():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))["runs"]


def _draws(text):
    if text == "-":
        return []
    out = []
    for draw in text.split(";"):
        index, colour = draw.split(":")
        value = int(colour, 16)
        out.append((int(index, 16), (value >> 16) & 255, (value >> 8) & 255, value & 255))
    return out


class FireworksLampTests(unittest.TestCase):
    def test_every_recorded_lamp_frame(self):
        frames = 0
        for index, run in enumerate(_runs()):
            state = LAMP["FireworksState"](run["n"])
            state.state, state.launches, state.dying = run["state"], run["launches"], run["dying"]
            for number, frame in enumerate(run["frames"]):
                label = f'run {index} frame {number}'
                reads = iter(zip(frame["sites"], frame["reads"]))

                def read(site):
                    expected, value = next(reads)
                    self.assertEqual(expected, site, label)
                    return value

                draws = LAMP["fireworks_step"](
                    state, run["n"], run["rate"], run["intensity"],
                    run["selector"], run["word"], read,
                )
                self.assertIsNone(next(reads, None), f"every read taken: {label}")
                self.assertEqual(_draws(frame["draws"]), draws, label)
                self.assertEqual(frame["state"], state.state, label)
                self.assertEqual(frame["launches"], state.launches, label)
                self.assertEqual(frame["side"], state.side, label)
                self.assertEqual(frame["dying"], format(state.dying, "08x"), label)
                self.assertEqual(frame["crc"], format(zlib.crc32(bytes(state.records)), "08x"), label)
                frames += 1
        self.assertEqual(2656, frames)

    def test_the_mapper_places_the_strip_as_on_the_lamp(self):
        frame_of = lambda direction, pixel: LAMP["frame_index"](
            LAMP["panel_index"](pixel, 100, direction, 2)
        )
        # Profile 2, direction 0 (the box the app's pictures are drawn in):
        # column c, row r from the top is buffer index c * 5 + 4 - r.
        self.assertEqual(4, LAMP["panel_index"](0, 100, 0, 2))
        self.assertEqual(9, LAMP["panel_index"](1, 100, 0, 2))
        # The first pixel of the strip (the flare's start): Up top-left, Down
        # bottom-right (as the earlier calibration saw), Left bottom-left,
        # Right top-right; Left and Right then climb column by column.
        self.assertEqual({0: 80, 1: 19, 2: 0, 3: 99}, {d: frame_of(d, 0) for d in range(4)})
        self.assertEqual([0, 20, 40, 60, 80, 1], [frame_of(2, i) for i in range(6)])
        # Every pixel lands once, whatever the direction or profile.
        for profile in range(4):
            for direction in range(4):
                indexes = {LAMP["panel_index"](i, 100, direction, profile) for i in range(100)}
                self.assertEqual(set(range(100)), indexes)

    def test_a_shots_length_is_known_without_drawing_it(self):
        for rate in (0, 1, 50, 128, 200, 255):
            for shot in range(12):
                state, read, renders = LAMP["FireworksState"](), LAMP["_shot_source"](shot), 0
                while True:
                    LAMP["fireworks_step"](state, 100, rate, 128, 14, 0, read)
                    renders += 1
                    if state.state == 0:
                        break
                self.assertEqual(renders, LAMP["_fireworks_shot_length"](shot, rate), (rate, shot))
        # On the lamp, at rate 128, a shot with the shortest pause
        # is 133 renders (5.3 s).
        self.assertTrue(any(
            LAMP["_fireworks_shot_length"](shot, 128) in range(128, 140) for shot in range(20)
        ))

    def test_any_moment_is_the_continuous_run(self):
        for rate in (0, 100, 255):
            state, shot = LAMP["FireworksState"](), 0
            read = LAMP["_shot_source"](0)
            timeline = LAMP["_FireworksTimeline"](rate)
            for render in range(700):
                if render and state.state == 0:
                    shot += 1
                    read = LAMP["_shot_source"](shot)
                expected = LAMP["fireworks_step"](state, 100, rate, 128, 14, 0, read)
                self.assertEqual(expected, timeline.draws_at(render), (rate, render))
            self.assertGreater(shot, 3)
        # Back in time, or far ahead, gives the same frames again.
        early = LAMP["render_fireworks"](2.0, 50, 0)
        LAMP["render_fireworks"](3600.0, 50, 0)
        self.assertEqual(early, LAMP["render_fireworks"](2.0, 50, 0))

    def test_previews_on_their_own_clocks_do_not_replay_a_shot(self):
        reference = LAMP["_FireworksTimeline"](50)
        expected = [reference.draws_at(render) for render in range(700)]
        timeline = LAMP["_FireworksTimeline"](50)
        for render in range(30, 680):
            for offset in (19, 0, 7):  # a clock ahead reads first
                self.assertEqual(expected[render + offset], timeline.draws_at(render + offset))
            self.assertLessEqual(len(timeline.shots), 6)
        # A shot is computed once: reading it behind its end adds no render.
        record = next(reversed(timeline.shots.values()))
        renders = len(record.draws)
        for back in range(5):
            timeline.draws_at(680 - back)
        self.assertEqual(renders, len(record.draws))

    def test_the_preview_draws_the_lamp(self):
        # The previews' phase is seconds x (0.25 + speed / 55): the lamp's
        # renderer gets the seconds and the speed (its rate) back.
        for speed in (10, 50, 100):
            for name, direction in (("Up", 0), ("Down", 1), ("Left", 2), ("Right", 3)):
                seconds = 4.36
                phase = seconds * (0.25 + speed / 55.0)
                expected = LAMP["render_fireworks"](seconds, speed, direction)
                self.assertEqual(
                    expected,
                    PREVIEW["render_native_effect"]("Fireworks", phase, name, speed=speed),
                )
        # A flare, then coloured sparks, then black between shots.
        flare = PREVIEW["render_native_effect"]("Fireworks", 0.0, "Up")
        self.assertEqual([(255, 255, 255)], [p for p in flare if p != (0, 0, 0)])
        frames = [LAMP["render_fireworks"](r * 0.04, 50, 0) for r in range(140)]
        lit = [sum(p != (0, 0, 0) for p in frame) for frame in frames]
        self.assertGreater(max(lit), 20)
        self.assertGreater(len({p for frame in frames for p in frame if max(p) - min(p) > 60}), 20)
        self.assertIn(0, lit[60:])

    def test_magic_is_the_lamp_formula(self):
        for case in json.loads(MAGIC.read_text())["cases"]:
            text = case["cells"]
            expected = [tuple(bytes.fromhex(text[i:i + 6])) for i in range(0, 600, 6)]
            self.assertEqual(expected, LAMP["magic_cells"](case["render"], case["rate"]))
        # The preview gets the seconds and the speed back out of the phase, and
        # reads the slot's renderer: LED drive on direction 0's box.
        speed, seconds = 24, 5.48
        phase = seconds * (0.25 + speed / 55.0)
        drive = PREVIEW["render_native_effect"]("Magic", phase, "Up", speed=speed)
        settings = LAMP["lamp_settings"]("Magic", "Up", speed)
        self.assertEqual(LAMP["renderer_frame"](settings, 137), drive)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the JS port")
    def test_the_js_port_of_magic_is_the_same(self):
        module = (ROOT / "www" / "lamp-renderers.js").as_uri()
        script = (
            'import fs from "node:fs";'
            f"const m = await import({json.dumps(module)});"
            f"const data = JSON.parse(fs.readFileSync({json.dumps(str(MAGIC))}));"
            "const hex = (c) => c.map((v) => v.toString(16).padStart(2, '0')).join('');"
            "const bad = data.cases.filter((k) => m.magicCells(k.render, k.rate).map(hex).join('') !== k.cells);"
            "process.stdout.write(JSON.stringify({ bad: bad.length }));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            text=True, capture_output=True, check=True,
        )
        out = json.loads(result.stdout)
        self.assertEqual(0, out["bad"])

    @unittest.skipUnless(shutil.which("node"), "Node is required for the JS port")
    def test_the_js_tide_directions_are_the_same(self):
        preview_js = (ROOT / "www" / "native-effect-preview.js").as_uri()
        cases = [[3.7, d] for d in ("Up", "Down", "Left", "Right")]
        script = (
            f"const p = await import({json.dumps(preview_js)});"
            f"process.stdout.write(JSON.stringify({json.dumps(cases)}.map("
            "([phase, d]) => p.renderNativeEffect('Tide', phase, d))));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            text=True, capture_output=True, check=True,
        )
        expected = [
            [list(pixel) for pixel in PREVIEW["render_native_effect"]("Tide", phase, d)]
            for phase, d in cases
        ]
        self.assertEqual(expected, json.loads(result.stdout))

    def test_led_drive_is_shown_as_the_reference_page_shows_it(self):
        for drive, shown in json.loads(APPEARANCE.read_text())["cases"]:
            self.assertEqual(tuple(shown), LAMP["led_appearance"](drive), drive)
        # A dim LED value is far brighter than the same number on a screen.
        self.assertEqual((173, 0, 0), LAMP["led_appearance"]((64, 0, 0)))

    @unittest.skipUnless(shutil.which("node"), "Node is required for the JS port")
    def test_the_cards_show_the_leds_only_for_lamp_renderers(self):
        renderers = (ROOT / "www" / "lamp-renderers.js").as_uri()
        utils = (ROOT / "www" / "native-effect-card-utils.js").as_uri()
        preview = (ROOT / "www" / "native-effect-preview.js").as_uri()
        script = (
            'import fs from "node:fs";'
            f"const f = await import({json.dumps(renderers)});"
            f"const u = await import({json.dumps(utils)});"
            f"const p = await import({json.dumps(preview)});"
            f"const data = JSON.parse(fs.readFileSync({json.dumps(str(APPEARANCE))}));"
            "const bad = data.cases.filter(([drive, shown]) =>"
            " String(f.ledAppearance(drive)) !== String(shown));"
            "const frame = [[64, 0, 0], [0, 0, 0]];"
            "const attrs = { native_effect_speed: 50 };"
            "const raw = (name) => p.renderNativeEffect(name, 4.36 * (0.25 + 50 / 55), 'Up', null, 'normal', 50);"
            "process.stdout.write(JSON.stringify({ bad: bad.length,"
            " fireworks: f.effectDisplayFrame('Fireworks', frame),"
            " other: f.effectDisplayFrame('77', frame),"
            " card: u.nativeEffectFrame({ name: 'Fireworks' }, attrs, 4.36).flat(),"
            " wanted: raw('Fireworks').map(f.ledAppearance).flat(),"
            " cardStreamer: u.nativeEffectFrame({ name: 'Ribbon' }, attrs, 4.36).flat(),"
            " wantedStreamer: raw('Ribbon').map(f.ledAppearance).flat(),"
            " cardOther: u.nativeEffectFrame({ name: '77' }, attrs, 4.36).flat(),"
            " wantedOther: raw('77').flat(),"
            " }));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            text=True, capture_output=True, check=True,
        )
        out = json.loads(result.stdout)
        self.assertEqual(0, out["bad"])
        self.assertEqual([[173, 0, 0], [0, 0, 0]], out["fireworks"])
        self.assertEqual([[64, 0, 0], [0, 0, 0]], out["other"])
        self.assertEqual(sorted(out["wanted"]), sorted(out["card"]))  # turned for the viewer
        self.assertEqual(sorted(out["wantedStreamer"]), sorted(out["cardStreamer"]))
        self.assertEqual(sorted(out["wantedOther"]), sorted(out["cardOther"]))

    def test_the_lamp_preview_does_not_fade_a_lamp_renderer(self):
        styles = (ROOT / "www" / "lamp-preview-styles.js").read_text(encoding="utf8")
        self.assertRegex(styles, r"\.lamp-dots-instant \.lamp-dot \{\s*transition: none;")
        matrix = (ROOT / "www" / "lamp-preview-matrix.js").read_text(encoding="utf8")
        self.assertIn("this._setInstantDots(isLampRendered(effect))", matrix)
        self.assertIn("this._setInstantDots(clockUsesLampRenderer(st.attributes))", matrix)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the JS port")
    def test_the_cards_show_every_render(self):
        # createRafLoop's smoothWhen, on three displays, with the preview's
        # clock started anywhere within a render: every render is painted once
        # or more and none skipped, while the other previews keep their rate.
        module = (ROOT / "www" / "matrix-animator.js").as_uri()
        renderers = (ROOT / "www" / "lamp-renderers.js").as_uri()
        script = (
            f"const m = await import({json.dumps(module)});"
            f"const f = await import({json.dumps(renderers)});"
            "const out = [];"
            # One requestAnimationFrame for every loop of the page: each run
            # stops its loop, so the next starts the ticker again.
            "globalThis.cancelAnimationFrame = () => {};"
            "for (const hz of [60, 120, 144]) for (let start = 0; start < 40; start += 3) {"
            " let callback = null; globalThis.requestAnimationFrame = (c) => { callback = c; return 1; };"
            " const shown = []; let due = 0;"
            " const loop = m.createRafLoop((t, isDue) => {"
            "  shown.push(Math.floor((t - start) / (f.RENDER_SECONDS * 1000))); if (isDue) due += 1;"
            " }, { minIntervalMs: 100, smoothWhen: () => f.isLampRendered('Fireworks') });"
            " loop.start();"
            " for (let i = 1; i <= hz * 10; i += 1) callback(i * 1000 / hz);"
            " const jumps = shown.slice(1).map((v, i) => v - shown[i]);"
            " loop.stop();"
            " out.push({ hz, start, most: Math.max(...jumps), due });"
            "}"
            "let callback = null; globalThis.requestAnimationFrame = (c) => { callback = c; return 1; };"
            "let plain = 0; let smooth = 0;"
            "const other = m.createRafLoop(() => { plain += 1; },"
            " { minIntervalMs: 100, smoothWhen: () => f.isLampRendered('77') });"
            "other.start(); for (let i = 1; i <= 600; i += 1) callback(i * 1000 / 60);"
            "process.stdout.write(JSON.stringify({ out, plain }));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            text=True, capture_output=True, check=True,
        )
        data = json.loads(result.stdout)
        self.assertEqual(42, len(data["out"]))
        for run in data["out"]:
            self.assertLessEqual(run["most"], 1, run)
            self.assertIn(run["due"], range(85, 102), run)
        # An effect the lamp's renderers do not draw stays at 10 a second.
        self.assertIn(data["plain"], range(85, 102))

    @unittest.skipUnless(shutil.which("node"), "Node is required for the JS port")
    def test_the_js_port_is_the_same(self):
        module = (ROOT / "www" / "lamp-renderers.js").as_uri()
        # The times go back and forth: previews on different clocks.
        cases = [[rate, d, t] for rate in (1, 50, 128, 255) for d in range(4)
                 for t in (0.0, 0.5, 1.7, 2.4, 5.3, 61.25, 3600.04, 1.8, 0.6, 2.5, 1.9)]
        script = (
            'import zlib from "node:zlib"; import fs from "node:fs";'
            f"const m = await import({json.dumps(module)});"
            f"const data = JSON.parse(zlib.gunzipSync(fs.readFileSync({json.dumps(str(FIXTURE))})));"
            "let frames = 0; const bad = [];"
            "data.runs.forEach((run, index) => {"
            " const fw = m.fireworksState(run.n);"
            " fw.state = run.state; fw.launches = run.launches; fw.dying = run.dying;"
            " run.frames.forEach((f, number) => {"
            "  let used = 0;"
            "  const draws = m.fireworksStep(fw, run.n, run.rate, run.intensity, run.selector, run.word,"
            "   (site) => { if (f.sites[used] !== site) bad.push([index, number, 'site']); return f.reads[used++]; });"
            "  const crc = (zlib.crc32(new Uint8Array(fw.records.buffer)) >>> 0).toString(16).padStart(8, '0');"
            "  const text = draws.length ? draws.map(([i, r, g, b]) => i.toString(16) + ':' +"
            "   ((r << 16 | g << 8 | b) >>> 0).toString(16).padStart(6, '0')).join(';') : '-';"
            "  if (used !== f.reads.length || text !== f.draws || fw.state !== f.state || fw.launches !== f.launches"
            "   || fw.side !== f.side || (fw.dying >>> 0).toString(16).padStart(8, '0') !== f.dying || crc !== f.crc)"
            "   bad.push([index, number]);"
            "  frames += 1;"
            " });"
            "});"
            f"const frames2 = {json.dumps(cases)}.map(([rate, d, t]) => m.renderFireworks(t, rate, d));"
            "process.stdout.write(JSON.stringify({frames, bad: bad.slice(0, 5), previews: frames2}));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            text=True, capture_output=True, check=True,
        )
        out = json.loads(result.stdout)
        self.assertEqual(2656, out["frames"])
        self.assertEqual([], out["bad"])
        expected = [[list(p) for p in LAMP["render_fireworks"](t, rate, d)] for rate, d, t in cases]
        self.assertEqual(expected, out["previews"])


if __name__ == "__main__":
    unittest.main()


class DimmedTrailTests(unittest.TestCase):
    """A Cube Lite below full brightness: its pixel writer stores each
    channel (c x B) >> 8 and the renderers that read their strip back dim
    their trails once more every frame (lamp_renderers.at_brightness)."""

    EFFECTS = ("Particle path", "Palette trails", "Aqua-lime trails", "Palette sparks",
               "Drop and bounce", "Dot with fading trail", "Music bars from both ends",
               "Music bass-mid-treble colour")

    def _frames(self, effect, brightness, count=40):
        settings = LAMP["at_brightness"](LAMP["lamp_settings"](effect, "Right", 66, intensity=161), brightness)
        return list(LAMP["exact_frames"](settings, 300, count))

    def test_the_writer_level(self):
        level = LAMP["writer_level"]
        self.assertEqual(255, level(None))
        self.assertEqual(255, level(255))
        self.assertEqual(83, level(51))  # 20 %: byte 51
        self.assertEqual(40 + 2 * 215 // 255 + 1, level(1))  # 1 %: byte 3

    def test_full_brightness_is_unchanged(self):
        settings = LAMP["lamp_settings"]("Particle path", "Right", 66, intensity=161)
        self.assertIs(settings, LAMP["at_brightness"](settings, 255))
        self.assertIs(settings, LAMP["at_brightness"](settings, None))
        self.assertEqual(LAMP["writer_level"](254), LAMP["at_brightness"](settings, 254).get("writer", 255))
        self.assertNotIn("writer", settings)

    def test_a_dimmed_lamp_has_shorter_trails(self):
        # Seen on camera at 20 %: Particle path is four lone dots, not trails.
        for effect in ("Particle path", "Palette trails", "Aqua-lime trails"):
            full = sum(sum(1 for value in frame if value) for frame in self._frames(effect, 255))
            dimmed = sum(sum(1 for value in frame if value) for frame in self._frames(effect, 51))
            self.assertLess(dimmed, full / 3, effect)

    def test_an_effect_that_redraws_everything_keeps_its_picture(self):
        # Rainbow reads nothing back: dimmed once, at display, by the preview.
        self.assertEqual(self._frames("Rainbow", 255, 10), self._frames("Rainbow", 51, 10))

    def test_the_preview_timeline_is_the_lamps_run(self):
        # The previews' timeline (cursors, ring) gives the exact replay's frames.
        for effect in ("Particle path", "Dot with fading trail"):
            settings = LAMP["at_brightness"](LAMP["lamp_settings"](effect, "Right", 66, intensity=161), 51)
            timeline = LAMP["timeline_for"](settings)
            self.assertEqual(
                [bytes(frame) for frame in LAMP["exact_frames"](settings, 500, 20)],
                [bytes(timeline.frame_at(render, True)) for render in range(500, 520)],
                effect,
            )

    @unittest.skipUnless(shutil.which("node"), "Node is required for the JS port")
    def test_the_js_port_dims_the_same(self):
        module = (ROOT / "www" / "lamp-renderers.js").as_uri()
        core = (ROOT / "www" / "lamp-core.js").as_uri()
        levels = [None, 1, 51, 128, 200, 254, 255]
        script = (
            f"const m = await import({json.dumps(module)});"
            f"const c = await import({json.dumps(core)});"
            f"const effects = {json.dumps(self.EFFECTS)};"
            "const out = {levels: " + json.dumps(levels) + ".map((b) => c.writerLevel(b)), frames: {}};"
            "for (const effect of effects) for (const b of [255, 51, 128]) {"
            " const s = m.atBrightness(m.lampSettings(effect, 'Right', 66, null, null, null, 161), b);"
            " out.frames[effect + ' ' + b] = [...m.exactFrames(s, 300, 40)].map((f) => Array.from(f));"
            " const t = m.lampEffectFrame(s, 7.3);"
            " out.frames[effect + ' ' + b + ' preview'] = t;"
            "}"
            "process.stdout.write(JSON.stringify(out));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            text=True, capture_output=True, check=True,
        )
        out = json.loads(result.stdout)
        self.assertEqual([LAMP["writer_level"](b) for b in levels], out["levels"])
        for effect in self.EFFECTS:
            for brightness in (255, 51, 128):
                settings = LAMP["at_brightness"](
                    LAMP["lamp_settings"](effect, "Right", 66, intensity=161), brightness,
                )
                self.assertEqual(
                    [list(frame) for frame in LAMP["exact_frames"](settings, 300, 40)],
                    out["frames"][f"{effect} {brightness}"], (effect, brightness),
                )
                self.assertEqual(
                    [list(p) for p in LAMP["lamp_effect_frame"](settings, 7.3)],
                    out["frames"][f"{effect} {brightness} preview"], (effect, brightness),
                )
