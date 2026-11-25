import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import generate_statistics
from data_loader import discover_measurements


class StatisticsDisplayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_root = self.root / "SanitizedData"
        self.cache_root = self.root / "StatisticsCache"
        self.graph_root = self.root / "GraphCache"
        self._write_csv(
            900,
            [5, 10, 30],
            [0, 0, 0],
            [2, 3, 4],
            [4, 5, 6],
            [1, 3, 5],
        )
        self._write_csv(
            300000,
            [10, 20, 40],
            [0, 20, 30],
            [2, 3, 4],
            [4, 5, 6],
            [1, 3, 5],
        )
        self._write_csv(
            900,
            [5, 10, 30],
            [0, 0, 0],
            [2, 3, 4],
            [4, 5, 6],
            None,
            level="L_Stage02",
        )
        self._write_csv(
            300000,
            [10, 20, 40],
            [0, 20, 30],
            [2, 3, 4],
            [4, 5, 6],
            None,
            level="L_Stage02",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_csv(
        self, revision, frame, game, render, gpu, translucency, level="L_Stage01"
    ):
        path = self.input_root / f"Rev{revision}_integration" / f"{level}-test.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            header = ["EVENTS", "FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime"]
            if translucency is not None:
                header.append("GPU/Translucency")
            writer.writerow(header)
            for index, values in enumerate(zip(frame, game, render, gpu)):
                row = ["Frame", *values]
                if translucency is not None:
                    row.append(translucency[index])
                writer.writerow(row)

    def _generate_and_load(self):
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
            self.assertEqual(generate_statistics.main(), 0)
        measurements = discover_measurements(self.input_root, self.graph_root)
        with patch.object(app, "STATISTICS_CACHE_ROOT", self.cache_root):
            app.cached_statistics_cache.clear()
            stats_by_key, missing = app._load_statistics_for_measurements(measurements)
        self.assertEqual(missing, 0)
        return measurements, stats_by_key

    def test_generated_json_flows_through_overview_detail_and_trend(self):
        measurements, stats_by_key = self._generate_and_load()
        current = {
            item.level_name: item
            for item in measurements
            if item.revision_number == 300000
        }
        previous = {
            item.level_name: item
            for item in measurements
            if item.revision_number == 900
        }

        with patch.object(app.st, "dataframe") as dataframe:
            app._render_overview(current, previous, "Mean", stats_by_key)
        overview = dataframe.call_args.args[0].data
        self.assertEqual(overview.loc["L_Stage01", "FrameTime"], "23.33 ms (+55.56%)")
        self.assertEqual(overview.loc["L_Stage01", "GT超過"], "2 (+2)")
        self.assertEqual(overview.loc["L_Stage01", "RT超過"], "0 (0)")

        with patch.object(app.st, "dataframe") as dataframe:
            app._render_statistics(current["L_Stage01"], previous["L_Stage01"], stats_by_key)
        detail = dataframe.call_args.args[0].data
        self.assertEqual(detail.loc["FrameTime", "Mean Current"], "23.33 ms")
        self.assertEqual(detail.loc["FrameTime", "Median Current"], "20.00 ms")
        self.assertEqual(detail.loc["FrameTime", "Max Current"], "40.00 ms")
        self.assertEqual(detail.loc["FrameTime", "P95 Current"], "38.00 ms")
        self.assertEqual(detail.loc["Translucency", "Mean Current"], "3.00 ms")

        mean_time, mean_over = app._trend_data(
            measurements, stats_by_key, "L_Stage01", "Mean"
        )
        median_time, median_over = app._trend_data(
            measurements, stats_by_key, "L_Stage01", "Median"
        )
        self.assertEqual(
            mean_time[mean_time["metric"] == "FrameTime"]["actual_value"].tolist(),
            [15.0, 70 / 3],
        )
        self.assertEqual(
            median_time[median_time["metric"] == "FrameTime"]["actual_value"].tolist(),
            [10.0, 20.0],
        )
        self.assertEqual(mean_over["value"].tolist(), median_over["value"].tolist())

    def test_generated_json_preserves_missing_translucency_and_valid_zero(self):
        measurements, stats_by_key = self._generate_and_load()
        current = {
            item.level_name: item
            for item in measurements
            if item.revision_number == 300000
        }
        previous = {
            item.level_name: item
            for item in measurements
            if item.revision_number == 900
        }
        current_stats = stats_by_key[("Rev300000_integration", "L_Stage01")]
        self.assertEqual(current_stats["metrics"]["GameThread"]["OverBudgetFrameCount"], 2)
        self.assertEqual(current_stats["metrics"]["RenderThread"]["OverBudgetFrameCount"], 0)
        self.assertEqual(current_stats["metrics"]["Translucency"]["ValidFrameCount"], 3)

        with patch.object(app.st, "dataframe") as dataframe:
            app._render_statistics(current["L_Stage01"], previous["L_Stage01"], stats_by_key)
        detail = dataframe.call_args.args[0].data
        self.assertNotEqual(detail.loc["Translucency", "Mean Current"], "N/A")
        self.assertEqual(detail.loc["RenderThread", "Mean Current"], "3.00 ms")

        with patch.object(app.st, "dataframe") as dataframe:
            app._render_statistics(current["L_Stage02"], previous["L_Stage02"], stats_by_key)
        missing_detail = dataframe.call_args.args[0].data
        self.assertEqual(missing_detail.loc["Translucency", "Mean Current"], "N/A")


if __name__ == "__main__":
    unittest.main()
