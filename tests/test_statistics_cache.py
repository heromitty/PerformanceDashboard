import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from data_loader import (
    FRAME_BUDGET_60FPS_MS,
    Measurement,
    calculate_statistics_cache,
    calculate_over_budget_statistics,
    calculate_statistics,
    load_frame_data,
    load_statistics_cache,
    save_statistics_cache,
    validate_statistics_cache,
)
import app
import generate_statistics


class StatisticsCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_root = self.root / "SanitizedData"
        self.cache_root = self.root / "StatisticsCache"
        self.csv_path = self.input_root / "Rev1000_hoge" / "L_Stage01-test.csv"
        self._write_csv(self.csv_path, [10.0, 16.67, 20.0, None])

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _write_csv(path, frame_times):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(
                [
                    "EVENTS",
                    "FrameTime",
                    "GameThreadTime",
                    "RenderThreadTime",
                    "GPUTime",
                    "GPU/Translucency",
                ]
            )
            for index, value in enumerate(frame_times):
                writer.writerow(
                    [
                        "Frame",
                        value,
                        value,
                        0 if value is not None else None,
                        value,
                        value,
                    ]
                )
            writer.writerow(["Cmd:SomeEvent", 99, 99, 99, 99, 99])

    def _run_generator(self):
        with patch.object(
            sys,
            "argv",
            [
                "generate_statistics.py",
                "--input-data",
                str(self.input_root),
                "--statistics-cache",
                str(self.cache_root),
            ],
        ):
            return generate_statistics.main()

    def test_first_run_generates_all_and_second_run_skips_without_csv_read(self):
        self.assertEqual(self._run_generator(), 0)
        cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        self.assertTrue(cache_path.exists())
        with patch("generate_statistics.load_frame_data", side_effect=AssertionError):
            self.assertEqual(self._run_generator(), 0)

    def test_statistics_preserve_missing_zero_and_strict_threshold(self):
        frame_df = load_frame_data(self.csv_path)
        payload = calculate_statistics_cache(frame_df, "Rev1000_hoge", 1000, "L_Stage01")
        metrics = payload["metrics"]
        self.assertNotIn("OverBudgetFrameCount", metrics["FrameTime"])
        self.assertEqual(metrics["GameThread"]["OverBudgetFrameCount"], 1)
        self.assertEqual(metrics["GameThread"]["ValidFrameCount"], 3)
        self.assertEqual(metrics["RenderThread"]["Mean"], 0.0)
        missing = frame_df.copy()
        missing["GPU/Translucency"] = pd.NA
        missing_payload = calculate_statistics_cache(
            missing, "Rev1000_hoge", 1000, "L_Stage01"
        )
        self.assertIsNone(missing_payload["metrics"]["Translucency"]["P95"])
        self.assertEqual(payload["over_budget_threshold_ms"], FRAME_BUDGET_60FPS_MS)

    def test_cache_statistics_match_existing_statistics_and_known_values(self):
        frame_df = load_frame_data(self.csv_path)
        expected = calculate_statistics(frame_df)
        expected_over_budget = calculate_over_budget_statistics(frame_df)
        payload = calculate_statistics_cache(frame_df, "Rev1000_hoge", 1000, "L_Stage01")
        cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        save_statistics_cache(cache_path, payload)
        loaded = load_statistics_cache(cache_path, "Rev1000_hoge", 1000, "L_Stage01")
        self.assertIsNotNone(loaded)

        for metric_name, expected_stats in expected.items():
            actual = loaded["metrics"][metric_name]
            for statistic in ("Mean", "Median", "Max", "P95"):
                if expected_stats[statistic] is None:
                    self.assertIsNone(actual[statistic])
                else:
                    self.assertAlmostEqual(actual[statistic], expected_stats[statistic])
            self.assertEqual(actual["ValidFrameCount"], int(
                frame_df[{
                    "FrameTime": "FrameTime",
                    "GameThread": "GameThreadTime",
                    "RenderThread": "RenderThreadTime",
                    "GPU": "GPUTime",
                    "Translucency": "GPU/Translucency",
                }[metric_name]].notna().sum()
            ))
            if metric_name in expected_over_budget:
                self.assertEqual(
                    actual["OverBudgetFrameCount"],
                    expected_over_budget[metric_name]["OverBudgetFrameCount"],
                )
                self.assertAlmostEqual(
                    actual["OverBudgetRate"],
                    expected_over_budget[metric_name]["OverBudgetRate"],
                )

        self.assertAlmostEqual(payload["metrics"]["FrameTime"]["Mean"], (10 + 16.67 + 20) / 3)
        self.assertEqual(payload["metrics"]["GameThread"]["OverBudgetFrameCount"], 1)
        self.assertEqual(payload["metrics"]["RenderThread"]["OverBudgetFrameCount"], 0)

        no_translucency = frame_df.copy()
        no_translucency["GPU/Translucency"] = pd.NA
        missing_payload = calculate_statistics_cache(
            no_translucency, "Rev1000_hoge", 1000, "L_Stage01"
        )
        self.assertIsNone(missing_payload["metrics"]["Translucency"]["Mean"])
        self.assertEqual(missing_payload["metrics"]["Translucency"]["ValidFrameCount"], 0)

    def test_invalid_identity_schema_and_corrupt_json_are_rejected(self):
        self._run_generator()
        cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["level"] = "WrongLevel"
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        valid, reason = validate_statistics_cache(cache_path, "Rev1000_hoge", 1000, "L_Stage01")
        self.assertFalse(valid)
        self.assertIn("level", reason)
        cache_path.write_text("{broken", encoding="utf-8")
        self.assertIsNone(load_statistics_cache(cache_path, "Rev1000_hoge", 1000, "L_Stage01"))
        with patch("generate_statistics.load_frame_data", wraps=load_frame_data) as loader:
            self.assertEqual(self._run_generator(), 0)
            self.assertEqual(loader.call_count, 1)
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["schema_version"] = 99
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch("generate_statistics.load_frame_data", wraps=load_frame_data) as loader:
            self.assertEqual(self._run_generator(), 0)
            self.assertEqual(loader.call_count, 1)

    def test_new_revision_and_level_only_generate_missing_entries(self):
        self.assertEqual(self._run_generator(), 0)
        self._write_csv(self.input_root / "Rev1001_hoge" / "L_Stage01-test.csv", [1.0])
        self._write_csv(self.input_root / "Rev1000_hoge" / "L_Stage02-test.csv", [2.0])
        with patch("generate_statistics.load_frame_data", wraps=load_frame_data) as loader:
            self.assertEqual(self._run_generator(), 0)
            self.assertEqual(loader.call_count, 2)

    def test_deleted_required_and_threshold_invalid_caches_only_regenerate_target(self):
        self._write_csv(self.input_root / "Rev1000_hoge" / "L_Stage02-test.csv", [1.0])
        self.assertEqual(self._run_generator(), 0)
        first = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        second = self.cache_root / "Rev1000_hoge" / "L_Stage02.json"

        first.unlink()
        with patch("generate_statistics.load_frame_data", wraps=load_frame_data) as loader:
            self.assertEqual(self._run_generator(), 0)
            self.assertEqual(loader.call_count, 1)

        payload = json.loads(second.read_text(encoding="utf-8"))
        del payload["metrics"]["GPU"]["P95"]
        second.write_text(json.dumps(payload), encoding="utf-8")
        with patch("generate_statistics.load_frame_data", wraps=load_frame_data) as loader:
            self.assertEqual(self._run_generator(), 0)
            self.assertEqual(loader.call_count, 1)

        payload = json.loads(first.read_text(encoding="utf-8"))
        payload["over_budget_threshold_ms"] = 20.0
        first.write_text(json.dumps(payload), encoding="utf-8")
        with patch("generate_statistics.load_frame_data", wraps=load_frame_data) as loader:
            self.assertEqual(self._run_generator(), 0)
            self.assertEqual(loader.call_count, 1)

    def test_deleted_csv_is_excluded_even_when_cache_remains(self):
        self.assertEqual(self._run_generator(), 0)
        cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        self.csv_path.unlink()
        measurements = generate_statistics.discover_measurements(self.input_root)
        self.assertEqual(measurements, [])
        self.assertTrue(cache_path.exists())

    def test_generation_continues_after_one_csv_failure_and_returns_error(self):
        second_csv = self.input_root / "Rev1000_hoge" / "L_Stage02-test.csv"
        self._write_csv(second_csv, [1.0])
        original_loader = generate_statistics.load_frame_data

        def fail_first(path):
            if Path(path) == self.csv_path:
                raise ValueError("test CSV failure")
            return original_loader(path)

        with patch("generate_statistics.load_frame_data", side_effect=fail_first):
            self.assertEqual(self._run_generator(), 1)
        self.assertFalse((self.cache_root / "Rev1000_hoge" / "L_Stage01.json").exists())
        self.assertTrue((self.cache_root / "Rev1000_hoge" / "L_Stage02.json").exists())

    def test_changed_csv_does_not_regenerate_valid_cache(self):
        self.assertEqual(self._run_generator(), 0)
        self._write_csv(self.csv_path, [999.0])
        with patch("generate_statistics.load_frame_data", side_effect=AssertionError):
            self.assertEqual(self._run_generator(), 0)

    def test_json_is_standard_and_saved_atomically(self):
        self._run_generator()
        cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        text = cache_path.read_text(encoding="utf-8")
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)
        json.loads(text)
        valid, _ = validate_statistics_cache(cache_path, "Rev1000_hoge", 1000, "L_Stage01")
        self.assertTrue(valid)

    def test_save_failure_preserves_existing_json_and_cleans_temporary_file(self):
        self._run_generator()
        cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
        original = cache_path.read_bytes()
        directory_before = set(cache_path.parent.iterdir())
        payload = json.loads(original)
        payload["metrics"]["FrameTime"]["Mean"] = 999.0
        with patch("data_loader.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                save_statistics_cache(cache_path, payload)
        self.assertEqual(cache_path.read_bytes(), original)
        self.assertEqual(set(cache_path.parent.iterdir()), directory_before)

    def test_dashboard_cache_read_is_read_only_and_never_reads_csv_or_generates(self):
        item = Measurement(
            "Rev1000_hoge", 1000, "L_Stage01", self.csv_path,
            self.root / "GraphCache" / "Rev1000_hoge" / "L_Stage01.png",
        )
        with patch.object(app, "STATISTICS_CACHE_ROOT", self.cache_root):
            app.cached_statistics_cache.clear()
            with patch("data_loader.load_frame_data", side_effect=AssertionError):
                self.assertIsNone(app._load_stats(item))
                cache_path = self.cache_root / "Rev1000_hoge" / "L_Stage01.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text("{broken", encoding="utf-8")
                app.cached_statistics_cache.clear()
                self.assertIsNone(app._load_stats(item))
        self.assertTrue((self.cache_root / "Rev1000_hoge" / "L_Stage01.json").exists())

    def test_successful_generation_returns_zero(self):
        self.assertEqual(self._run_generator(), 0)


if __name__ == "__main__":
    unittest.main()
