from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

import core

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class AppSmokeTests(unittest.TestCase):
    def test_full_playback_reloads_edited_audio_while_paused(self) -> None:
        js = (Path(__file__).parents[1] / "pitch_editor" / "frontend" / "component.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('playToken === token && audioLoadedUrl === url', js)
        self.assertIn('audioLoadedUrl = next;', js)
        self.assertIn('const wasPlaying = playing;', js)
        self.assertIn('audio.src = next;', js)

        app_source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('component_mount_id = (epoch, PITCH_EDITOR_BUILD)', app_source)
        self.assertIn('key=f"pitch_editor_main_{PITCH_EDITOR_BUILD}_', app_source)

    def test_empty_and_demo_views_render_without_exceptions(self) -> None:
        empty = AppTest.from_file(APP_PATH)
        empty.run(timeout=30)
        self.assertEqual(len(empty.exception), 0)

        demo = AppTest.from_file(APP_PATH)
        demo.query_params["demo"] = "1"
        demo.run(timeout=60)
        self.assertEqual(len(demo.exception), 0)
        self.assertEqual(len(demo.metric), 6)
        self.assertFalse(demo.session_state["pitch_dirty"])
        self.assertEqual(demo.session_state["component_epoch"], 1)

    def test_point_first_layers_receive_clean_primary_interval_layer(self) -> None:
        data = core.generate_sample_audio()
        app = AppTest.from_file(APP_PATH)
        app.session_state["audio_bytes"] = data
        app.session_state["audio_hash"] = core.bytes_hash(data)
        app.session_state["audio_name"] = "state-test.wav"
        app.session_state["layers"] = [
            {"name": "marks", "kind": "point", "items": [{"t": 0.5, "text": "x"}]}
        ]
        app.session_state["syllables"] = [{"t": 9.0, "text": "stale"}]
        app.run(timeout=60)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual([layer["kind"] for layer in app.session_state["layers"]], ["interval", "point"])
        self.assertEqual(app.session_state["syllables"], [])

    def test_duration_apply_rebuilds_audio_and_refreshes_component(self) -> None:
        app = AppTest.from_file(APP_PATH)
        app.query_params["demo"] = "1"
        app.run(timeout=60)

        auto_segment = next(button for button in app.button if button.label == "🧩 自动切分音节")
        auto_segment.click().run(timeout=60)
        self.assertGreater(len(app.session_state["syllables"]), 0)

        old_audio = app.session_state["audio_bytes"]
        old_length = len(core.load_audio_bytes(old_audio)[0])
        old_epoch = app.session_state["component_epoch"]
        app.session_state["dur_factors"] = [1.5] + [1.0] * (len(app.session_state["syllables"]) - 1)
        app.run(timeout=60)

        apply_duration = next(
            button for button in app.button if button.label == "🕐 应用时长（重合成）"
        )
        self.assertFalse(apply_duration.disabled)
        apply_duration.click().run(timeout=60)

        new_audio = app.session_state["audio_bytes"]
        new_length = len(core.load_audio_bytes(new_audio)[0])
        self.assertNotEqual(new_audio, old_audio)
        self.assertGreater(new_length, old_length)
        self.assertEqual(app.session_state["component_epoch"], old_epoch + 1)
        self.assertEqual(app.session_state["dur_factors"], [1.0] * len(app.session_state["syllables"]))
        self.assertTrue(app.session_state["dur_apply_msg"])
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
