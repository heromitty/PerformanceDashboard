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
    calculate_statistics_cache,
    load_frame_data,
    load_statistics_cache,
    save_statistics_cache,
    validate_statistics_cache,
)
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


if __name__ == "__main__":
    unittest.main()
