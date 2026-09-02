from __future__ import annotations

import unittest

import numpy as np

import core


class TextGridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tiers = [
            {
                "name": '点"层',
                "kind": "point",
                "items": [
                    {"t": 0.5, "text": '旧"值'},
                    {"t": 0.5, "text": '新"值'},
                ],
            },
            {
                "name": "音节",
                "kind": "interval",
                "items": [
                    {"t0": 0.0, "t1": 0.0000004, "text": "短"},
                    {"t0": 0.0000004, "t1": 1.0, "text": "其余"},
                ],
            },
        ]

    def assert_round_trip(self, text: str) -> None:
        tiers, xmax = core.textgrid_parse(text)
        self.assertEqual(xmax, 1.0)
        self.assertEqual(tiers[0]["kind"], "point")
        self.assertEqual(tiers[0]["name"], '点"层')
        self.assertEqual(tiers[0]["items"], [{"t": 0.5, "text": '新"值'}])
        self.assertEqual(tiers[1]["items"][0]["t1"], 0.0000004)

    def test_long_export_is_standard_and_round_trips(self) -> None:
        text = core.textgrid_export_tiers(self.tiers, 1.0)
        self.assertTrue(text.startswith('File type = "ooTextFile"'))
        self.assertNotEqual(text[0], "\ufeff")
        self.assertIn('class = "TextTier"', text)
        self.assertNotIn('class = "PointTier"', text)
        self.assertIn('name = "点""层"', text)
        self.assertEqual(text.count("number = 0.5"), 1)
        self.assert_round_trip(text)

    def test_short_export_round_trips(self) -> None:
        self.assert_round_trip(core.textgrid_export_tiers_short(self.tiers, 1.0))

    def test_utf16_and_compact_short_are_supported(self) -> None:
        long_text = core.textgrid_export_tiers(self.tiers, 1.0)
        tiers, xmax = core.textgrid_parse(long_text.encode("utf-16"))
        self.assertEqual(xmax, 1.0)
        self.assertEqual(tiers[0]["kind"], "point")

        short = core.textgrid_export_tiers_short(self.tiers[:1], 1.0)
        lines = short.splitlines()
        compact = "\n".join(
            [lines[0], lines[1], f"{lines[3]} {lines[4]}", lines[5], lines[6], " ".join(lines[7:])]
        ) + " ! trailing comment\n"
        compact_tiers, compact_xmax = core.textgrid_parse(compact)
        self.assertEqual(compact_xmax, 1.0)
        self.assertEqual(compact_tiers[0]["kind"], "point")

    def test_legacy_pointtier_can_be_imported(self) -> None:
        legacy = core.textgrid_export_tiers(self.tiers[:1], 1.0).replace("TextTier", "PointTier")
        tiers, _ = core.textgrid_parse(legacy)
        self.assertEqual(tiers[0]["kind"], "point")

    def test_interval_healing_is_positive_and_adjacent(self) -> None:
        healed = core._heal_interval_tier(
            [
                {"t0": 0.2, "t1": 0.6, "text": "a"},
                {"t0": 0.5, "t1": 0.8, "text": "b"},
            ],
            1.0,
        )
        self.assertEqual(healed[0]["t0"], 0.0)
        self.assertEqual(healed[-1]["t1"], 1.0)
        for left, right in zip(healed, healed[1:]):
            self.assertGreater(left["t1"], left["t0"])
            self.assertEqual(left["t1"], right["t0"])

    def test_time_values_round_trip_at_double_precision(self) -> None:
        xmax = float(np.nextafter(1.0, 2.0))
        tiers = [{"name": "points", "kind": "point", "items": []}]
        _, parsed_xmax = core.textgrid_parse(core.textgrid_export_tiers(tiers, xmax))
        self.assertEqual(parsed_xmax, xmax)


class PitchTests(unittest.TestCase):
    def test_audio_decode_does_not_normalize_amplitude(self) -> None:
        source = np.array([-0.25, 0.0, 0.25], dtype=np.float32)
        decoded, sr, _ = core.load_audio_bytes(core.wav_bytes(source, 8000))
        self.assertEqual(sr, 8000)
        self.assertAlmostEqual(float(np.max(np.abs(decoded))), 0.25, places=3)

    def test_tier_is_clipped_and_interpolated_in_semitones(self) -> None:
        times = np.array([0.0, 0.5, 1.0])
        voiced = np.array([100.0, 100.0, 100.0])
        clipped = core.build_f0_tier([[0.0, 10.0], [1.0, 1000.0]], times, voiced, 75, 500)
        self.assertGreaterEqual(float(clipped.min()), 75.0)
        self.assertLessEqual(float(clipped.max()), 500.0)

        interpolated = core.build_f0_tier([[0.0, 100.0], [1.0, 400.0]], times, voiced, 75, 500)
        self.assertAlmostEqual(float(interpolated[1]), 200.0, places=9)

    def test_chunked_analysis_is_chunk_size_independent(self) -> None:
        sr = 16000
        t = np.arange(sr, dtype=np.float64) / sr
        samples = np.sin(2 * np.pi * 180.0 * t).astype(np.float32)
        times_a, f0_a = core.analyze_pitch(samples, sr, chunk_frames=17)
        times_b, f0_b = core.analyze_pitch(samples, sr, chunk_frames=1024)
        np.testing.assert_array_equal(times_a, times_b)
        np.testing.assert_allclose(f0_a, f0_b, rtol=0, atol=1e-10)
        self.assertAlmostEqual(float(np.median(f0_a[f0_a > 0])), 180.0, delta=2.0)

    def test_resynthesis_is_finite_and_keeps_length_at_limits(self) -> None:
        sr = 16000
        t = np.arange(sr, dtype=np.float64) / sr
        samples = (0.2 * np.sin(2 * np.pi * 180.0 * t)).astype(np.float32)
        times, f0 = core.analyze_pitch(samples, sr)
        points = core.make_edit_points(times, f0)
        shifted = core.shift_semitones(points, 48)
        tier = core.build_f0_tier(shifted, times, f0, 75, 500)
        output = core.synthesize_with_f0(samples, sr, tier, f0, times)
        self.assertEqual(len(output), len(samples))
        self.assertTrue(np.isfinite(output).all())
        self.assertLessEqual(float(tier.max()), 500.0)

    def test_resynthesis_does_not_rescale_unvoiced_samples(self) -> None:
        sr = 16000
        t = np.arange(sr * 2, dtype=np.float64) / sr
        voiced = (
            0.4 * np.sin(2 * np.pi * 180.0 * t[:sr])
            + 0.3 * np.sin(2 * np.pi * 360.0 * t[:sr] + 0.7)
        )
        tail = np.linspace(-0.123, 0.123, sr)
        samples = np.concatenate([voiced, tail]).astype(np.float32)
        times = np.arange(0.02, 1.99, 0.01)
        f0_orig = np.where(times < 1.0, 180.0, 0.0)
        f0_new = np.where(times < 1.0, 400.0, 0.0)
        output = core.synthesize_with_f0(samples, sr, f0_new, f0_orig, times)
        np.testing.assert_array_equal(output[int(1.25 * sr):], samples[int(1.25 * sr):])

    def test_smoothing_uses_semitone_domain(self) -> None:
        points = [[0.0, 100.0], [0.1, 400.0], [0.2, 100.0], [0.3, 100.0]]
        result = core.smooth_points(points, window=3)
        expected_middle = 100.0 * (4.0 ** (1.0 / 3.0))
        self.assertAlmostEqual(result[1][1], expected_middle, places=3)

    def test_tone_features_keep_points_outside_annotations(self) -> None:
        points = [[0.0, 100.0], [0.1, 110.0], [1.0, 120.0]]
        result = core.extract_tone_feature_points(
            points, [{"t0": 0.0, "t1": 0.2, "text": "ma1"}], pad=0
        )
        self.assertIn([1.0, 120.0], result)

    def test_stylize_minimum_interval_cleanup_runs(self) -> None:
        points = [
            [time, 100.0 * 2 ** (semitones / 12.0)]
            for time, semitones in [(0, 0), (0.01, 1), (0.02, 1.1), (0.1, 2), (0.2, 3)]
        ]
        result = core.stylize_points(points, max_change_semitones=0.05, min_interval=0.04)
        self.assertNotIn(0.01, [point[0] for point in result])
        self.assertNotIn(0.02, [point[0] for point in result])


if __name__ == "__main__":
    unittest.main()
