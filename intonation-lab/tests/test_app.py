from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

import core

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class AppSmokeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
