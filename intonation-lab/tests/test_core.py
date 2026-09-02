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
    @staticmethod
    def dominant_frequency(samples: np.ndarray, sr: int) -> float:
        windowed = samples.astype(np.float64) * np.hanning(len(samples))
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(windowed), 1.0 / sr)
        usable = np.where((freqs >= 50.0) & (freqs <= 700.0))[0]
        return float(freqs[usable[int(np.argmax(spectrum[usable]))]])

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

    def test_fallback_points_exist_when_no_pitch_was_detected(self) -> None:
        times = np.arange(0.02, 0.5, 0.01)
        points = core.fallback_edit_points(times, 75, 500)
        self.assertGreaterEqual(len(points), 2)
        self.assertEqual(points[0][1], 150.0)
        self.assertAlmostEqual(points[-1][0], float(times[-1]), places=4)

    def test_resynthesis_changes_pitch_when_original_pulses_are_missing(self) -> None:
        sr = 16000
        t = np.arange(sr, dtype=np.float64) / sr
        samples = (0.3 * np.sin(2 * np.pi * 180.0 * t)).astype(np.float32)
        times = np.arange(0.02, 0.99, 0.01)
        f0_orig = np.zeros(len(times), dtype=np.float64)
        f0_new = np.full(len(times), 90.0, dtype=np.float64)
        output = core.synthesize_with_f0(samples, sr, f0_new, f0_orig, times)
        middle = output[int(0.15 * sr):int(0.85 * sr)]
        self.assertAlmostEqual(self.dominant_frequency(middle, sr), 90.0, delta=4.0)

    def test_chunked_analysis_is_chunk_size_independent(self) -> None:
        sr = 16000
        t = np.arange(sr, dtype=np.float64) / sr
        samples = np.sin(2 * np.pi * 180.0 * t).astype(np.float32)
        times_a, f0_a = core.analyze_pitch(samples, sr, chunk_frames=17)
        times_b, f0_b = core.analyze_pitch(samples, sr, chunk_frames=1024)
        np.testing.assert_array_equal(times_a, times_b)
        np.testing.assert_allclose(f0_a, f0_b, rtol=0, atol=1e-10)
        self.assertAlmostEqual(float(np.median(f0_a[f0_a > 0])), 180.0, delta=2.0)

    def test_resynthesis_keeps_energy_in_first_syllable(self) -> None:
        sr = 16000
        n = int(0.8 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        y = np.zeros(n, dtype=np.float64)
        y[t < 0.25] = 0.3 * np.sin(2 * np.pi * 180.0 * t[t < 0.25])
        mid = (t >= 0.4) & (t < 0.7)
        y[mid] = 0.3 * np.sin(2 * np.pi * 180.0 * t[mid])
        samples = y.astype(np.float32)
        times, f0 = core.analyze_pitch(samples, sr)
        points = core.shift_semitones(core.make_edit_points(times, f0), 4, 75, 500)
        tier = core.build_f0_tier(points, times, f0, 75, 500)
        output = core.synthesize_with_f0(samples, sr, tier, f0, times)
        first = slice(0, int(0.18 * sr))
        orig_rms = float(np.sqrt(np.mean(samples[first] ** 2)))
        out_rms = float(np.sqrt(np.mean(output[first] ** 2)))
        self.assertGreater(orig_rms, 0.02)
        self.assertGreater(out_rms, 0.35 * orig_rms)

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

    def test_tier_follows_edit_points_into_unvoiced_tail(self) -> None:
        times = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        orig = np.array([150.0, 140.0, 0.0, 0.0, 0.0])
        points = [[0.0, 150.0], [0.4, 90.0]]
        tier = core.build_f0_tier(points, times, orig, 75, 500)
        self.assertGreater(float(tier[0]), 0.0)
        self.assertGreater(float(tier[2]), 0.0)
        self.assertGreater(float(tier[-1]), 0.0)
        self.assertLess(float(tier[-1]), float(tier[0]))

    def test_resynthesis_applies_pitch_in_originally_unvoiced_tail(self) -> None:
        sr = 16000
        n = int(0.4 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        env = np.linspace(0.35, 0.05, n)
        samples = (env * np.sin(2 * np.pi * 180.0 * t)).astype(np.float32)
        times = np.arange(0.02, 0.38, 0.01)
        f0_orig = np.where(times < 0.18, 180.0, 0.0)
        points = [[0.02, 180.0], [0.35, 90.0]]
        tier = core.build_f0_tier(points, times, f0_orig, 75, 500)
        self.assertTrue(bool((tier[times >= 0.22] > 0).any()))
        output = core.synthesize_with_f0(samples, sr, tier, f0_orig, times)
        self.assertEqual(len(output), len(samples))
        self.assertTrue(np.isfinite(output).all())
        tail = slice(int(0.22 * sr), int(0.34 * sr))
        self.assertFalse(np.allclose(output[tail], samples[tail], atol=1e-3))

    def test_resynthesis_generates_sound_for_points_in_silence(self) -> None:
        sr = 16000
        n = int(0.5 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        y = np.zeros(n, dtype=np.float64)
        y[: int(0.2 * sr)] = 0.3 * np.sin(2 * np.pi * 180.0 * t[: int(0.2 * sr)])
        samples = y.astype(np.float32)
        times = np.arange(0.02, 0.48, 0.01)
        f0_orig = np.where(times < 0.2, 180.0, 0.0)
        points = [[0.05, 180.0], [0.18, 160.0], [0.40, 100.0]]
        tier = core.build_f0_tier(points, times, f0_orig, 75, 500)
        self.assertTrue(bool((tier[times > 0.3] > 0).any()))
        output = core.synthesize_with_f0(samples, sr, tier, f0_orig, times)
        tail = output[int(0.26 * sr) : int(0.40 * sr)]
        self.assertGreater(float(np.max(np.abs(tail))), 0.02)
        lag = int(round(sr / 100.0))
        corr = float(np.dot(tail[:-lag], tail[lag:]))
        self.assertGreater(corr, 0.0)

    def test_painted_tail_does_not_keep_original_residue(self) -> None:
        sr = 16000
        n = int(0.5 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        y = np.zeros(n, dtype=np.float64)
        y[t < 0.2] = 0.3 * np.sin(2 * np.pi * 180.0 * t[t < 0.2])
        y[t >= 0.2] = 0.25 * np.sin(2 * np.pi * 330.0 * t[t >= 0.2])
        samples = y.astype(np.float32)
        times = np.arange(0.02, 0.48, 0.01)
        f0_orig = np.where(times < 0.2, 180.0, 0.0)
        points = [[0.05, 180.0], [0.18, 160.0], [0.40, 100.0]]
        tier = core.build_f0_tier(points, times, f0_orig, 75, 500)
        output = core.synthesize_with_f0(samples, sr, tier, f0_orig, times)
        tail = slice(int(0.26 * sr), int(0.40 * sr))
        orig_tail = samples[tail].astype(np.float64)
        out_tail = output[tail].astype(np.float64)
        denom = float(np.sqrt(np.sum(orig_tail ** 2) * np.sum(out_tail ** 2)))
        corr = float(np.dot(orig_tail, out_tail) / denom) if denom > 1e-12 else 0.0
        self.assertLess(corr, 0.7)

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

    def test_split_syllable_text_pinyin_and_hanzi(self) -> None:
        syls, fmt = core.split_syllable_text("wo3men0shi4yi1shi4ba0")
        self.assertEqual(fmt, "拼音")
        self.assertEqual(syls, ["wo3", "men0", "shi4", "yi1", "shi4", "ba0"])
        syls, fmt = core.split_syllable_text("好3你0在吗")
        self.assertEqual(fmt, "汉字")
        self.assertEqual(syls, ["好3", "你0", "在", "吗"])

    def test_tone_feature_rules_keep_canonical_points(self) -> None:
        rising = [
            [0.0, 100.0], [0.1, 90.0], [0.2, 110.0],
            [0.3, 150.0], [0.4, 180.0], [0.5, 170.0],
        ]
        tone2 = core.extract_tone_feature_points(
            rising, [{"t0": 0.0, "t1": 0.6, "text": "ma2"}], pad=0
        )
        self.assertEqual(tone2, [[0.1, 90.0], [0.4, 180.0]])

        falling = [
            [0.0, 180.0], [0.1, 200.0], [0.2, 150.0],
            [0.3, 120.0], [0.4, 90.0], [0.5, 100.0],
        ]
        tone4 = core.extract_tone_feature_points(
            falling, [{"t0": 0.0, "t1": 0.6, "text": "ma4"}], pad=0
        )
        self.assertEqual(tone4, [[0.1, 200.0], [0.4, 90.0]])

        dip = [
            [0.0, 160.0], [0.1, 140.0], [0.2, 90.0],
            [0.3, 100.0], [0.4, 150.0],
        ]
        tone3 = core.extract_tone_feature_points(
            dip, [{"t0": 0.0, "t1": 0.5, "text": "ma3"}], pad=0
        )
        self.assertEqual([p[0] for p in tone3], [0.0, 0.2, 0.4])

        level = [[i * 0.1, 200.0] for i in range(5)]
        tone1 = core.extract_tone_feature_points(
            level, [{"t0": 0.0, "t1": 0.5, "text": "ma1"}], pad=0
        )
        self.assertEqual(tone1, [[0.0, 200.0], [0.4, 200.0]])

    def test_contiguous_tone_pad_does_not_steal_next_syllable(self) -> None:
        points = [
            [0.10, 150.0],
            [0.19, 150.0],
            [0.21, 80.0],
            [0.25, 100.0],
            [0.35, 200.0],
        ]
        syllables = [
            {"t0": 0.0, "t1": 0.2, "text": "a1"},
            {"t0": 0.2, "t1": 0.4, "text": "b2"},
        ]
        result = core.extract_tone_feature_points(points, syllables, pad=0.02)
        times = [p[0] for p in result]
        self.assertIn(0.19, times)
        self.assertIn(0.21, times)
        self.assertNotIn(0.25, times)

    def test_auto_segment_sample_covers_duration_contiguously(self) -> None:
        data = core.generate_sample_audio()
        samples, sr, _ = core.load_audio_bytes(data)
        times, f0 = core.analyze_pitch(samples, sr)
        boxes = core.auto_segment_syllables(samples, sr, times, f0)
        self.assertEqual(len(boxes), 3)
        duration = len(samples) / sr
        self.assertEqual(boxes[0]["t0"], 0.0)
        self.assertAlmostEqual(boxes[-1]["t1"], duration, places=3)
        for left, right in zip(boxes, boxes[1:]):
            self.assertEqual(left["t1"], right["t0"])
            self.assertGreater(left["t1"], left["t0"])

    def test_component_audio_payload_skips_resend_and_large_files(self) -> None:
        small = core.wav_bytes(np.zeros(1000, dtype=np.float32), 8000)
        first = core.component_audio_payload(small, small, remount=True)
        self.assertTrue(first["embedded"])
        self.assertTrue(first["url_orig"].startswith("data:"))
        self.assertEqual(first["url_edit"], "same")
        again = core.component_audio_payload(
            small,
            small,
            prev_orig_hash=first["orig_hash"],
            prev_edit_hash=first["edit_hash"],
            remount=False,
        )
        self.assertIsNone(again["url_orig"])
        self.assertIsNone(again["url_edit"])
        edited = core.wav_bytes(np.full(1000, 0.1, dtype=np.float32), 8000)
        changed = core.component_audio_payload(
            small,
            edited,
            prev_orig_hash=first["orig_hash"],
            prev_edit_hash=first["edit_hash"],
            remount=False,
        )
        self.assertIsNone(changed["url_orig"])
        self.assertTrue(changed["url_edit"].startswith("data:"))
        huge = core.component_audio_payload(small, small, remount=True, max_bytes=10)
        self.assertFalse(huge["embedded"])
        self.assertEqual(huge["url_orig"], "")
        self.assertEqual(huge["url_edit"], "")


if __name__ == "__main__":
    unittest.main()
