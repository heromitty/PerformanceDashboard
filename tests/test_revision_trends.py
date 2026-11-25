import tempfile
import unittest
from pathlib import Path

import app
from data_loader import Measurement, discover_measurements


class RevisionTrendTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_root = self.root / "SanitizedData"

        self.measurements = []
        for revision, levels in ((1002, ("L_Stage02",)), (1000, ("L_Stage01", "L_Stage02")), (1001, ("L_Stage01",))):
            for level in levels:
                csv_path = self.input_root / f"Rev{revision}_build" / f"{level}-capture.csv"
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                csv_path.write_text("EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime\n", encoding="utf-8")
        self.measurements = discover_measurements(self.input_root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _stats(self, revision, level, frame_time, gt_count, valid_count=1):
        metrics = {}
        for name in app.TREND_TIME_METRICS:
            metrics[name] = {
                "Mean": frame_time,
                "Median": frame_time + 1,
                "Max": frame_time + 2,
                "P95": frame_time + 3,
                "ValidFrameCount": valid_count,
            }
        metrics["GameThread"]["OverBudgetFrameCount"] = gt_count
        metrics["GameThread"]["OverBudgetRate"] = 1.0 if valid_count else None
        metrics["RenderThread"]["OverBudgetFrameCount"] = 0
        metrics["RenderThread"]["OverBudgetRate"] = 0.0 if valid_count else None
        metrics["GPU"]["OverBudgetFrameCount"] = 2
        metrics["GPU"]["OverBudgetRate"] = 2.0 if valid_count else None
        return {
            "revision": revision,
            "revision_folder": f"Rev{revision}_build",
            "level": level,
            "metrics": metrics,
        }

    def _stats_by_key(self, values):
        return {
            (f"Rev{revision}_build", level): self._stats(
                revision, level, frame_time, gt_count, valid_count
            )
            for revision, level, frame_time, gt_count, valid_count in values
        }

    def test_revision_and_level_union_is_numeric_and_includes_current_missing_levels(self):
        self.assertEqual([item.revision_number for item in self.measurements], [1000, 1000, 1001, 1002])
        self.assertEqual(app._trend_levels(self.measurements), ["L_Stage01", "L_Stage02"])
        stats = self._stats_by_key([(1000, "L_Stage01", 10, 0, 1), (1001, "L_Stage01", 11, 1, 1)])
        time_data, _ = app._trend_data(self.measurements, stats, "L_Stage02", "Mean")
        stage02 = time_data[time_data["metric"] == "FrameTime"]
        self.assertEqual(stage02["revision"].tolist(), [1000, 1001, 1002])
        self.assertTrue(stage02["actual_value"].isna().all())

    def test_deleted_csv_and_cache_only_revision_are_excluded(self):
        cache_only = self.input_root / "Rev9999_build" / "L_Stage01.json"
        cache_only.parent.mkdir(parents=True)
        cache_only.write_text("{}", encoding="utf-8")
        deleted_csv = self.input_root / "Rev1001_build" / "L_Stage01-capture.csv"
        deleted_csv.unlink()
        measurements = discover_measurements(self.input_root)
        self.assertEqual([item.revision_number for item in measurements], [1000, 1000, 1002])

    def test_statistic_selection_changes_time_values_but_not_over_budget_counts(self):
        stats = self._stats_by_key([(1000, "L_Stage01", 10, 3, 1)])
        mean_time, mean_over = app._trend_data(self.measurements, stats, "L_Stage01", "Mean")
        median_time, median_over = app._trend_data(self.measurements, stats, "L_Stage01", "Median")
        mean_value = mean_time[(mean_time["revision"] == 1000) & (mean_time["metric"] == "FrameTime")]["actual_value"].iloc[0]
        median_value = median_time[(median_time["revision"] == 1000) & (median_time["metric"] == "FrameTime")]["actual_value"].iloc[0]
        self.assertEqual(mean_value, 10)
        self.assertEqual(median_value, 11)
        self.assertEqual(mean_over[mean_over["revision"] == 1000]["value"].tolist(), median_over[median_over["revision"] == 1000]["value"].tolist())

    def test_time_overflow_is_clipped_without_mutating_actual_value(self):
        stats = self._stats_by_key([(1000, "L_Stage01", 42.5, 0, 1)])
        time_data, _ = app._trend_data(self.measurements, stats, "L_Stage01", "Mean")
        point = time_data[(time_data["revision"] == 1000) & (time_data["metric"] == "FrameTime")].iloc[0]
        self.assertEqual(point["actual_value"], 42.5)
        self.assertEqual(point["display_value"], 35.0)
        self.assertTrue(point["is_overflow"])
        spec = app._time_trend_chart(time_data).to_dict()
        self.assertEqual(spec["layer"][1]["encoding"]["y"]["scale"]["domain"], [0, 35.0])
        self.assertEqual(spec["layer"][2]["mark"]["shape"], "triangle-up")
        self.assertFalse(spec["layer"][2]["mark"]["clip"])
        self.assertEqual(spec["layer"][3]["encoding"]["text"]["field"], "actual_value")
        self.assertEqual(
            spec["layer"][1]["mark"]["invalid"],
            "break-paths-show-domains",
        )
        self.assertIn(
            {"budget": 16.67},
            [row for rows in spec["datasets"].values() for row in rows],
        )

    def test_missing_values_break_series_and_zero_count_is_valid(self):
        stats = self._stats_by_key([(1000, "L_Stage01", 10, 0, 1), (1002, "L_Stage01", 20, 2, 1)])
        time_data, over_data = app._trend_data(self.measurements, stats, "L_Stage01", "Mean")
        frame_time = time_data[time_data["metric"] == "FrameTime"]
        self.assertTrue(frame_time.loc[frame_time["revision"] == 1001, "actual_value"].isna().all())
        self.assertEqual(over_data[(over_data["revision"] == 1000) & (over_data["metric"] == "GT超過")]["value"].iloc[0], 0)

    def test_no_valid_value_is_safe(self):
        stats = self._stats_by_key([(1000, "L_Stage01", 0, 0, 0)])
        time_data, over_data = app._trend_data(self.measurements, stats, "L_Stage01", "Mean")
        self.assertFalse(time_data["actual_value"].notna().any())
        self.assertFalse(over_data["value"].notna().any())

    def test_ordinal_axes_use_shared_numeric_revision_order_and_keep_missing_positions(self):
        measurements = []
        for revision, level in (
            (900, "L_Stage01"),
            (1000, "L_Stage02"),
            (20000, "L_Stage01"),
            (20100, "L_Stage02"),
            (300000, "L_Stage01"),
        ):
            csv_path = self.input_root / f"Rev{revision}_build" / f"{level}-axis.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_text("EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime\n", encoding="utf-8")
            measurements.append(Measurement(
                f"Rev{revision}_build", revision, level, csv_path, self.root / "GraphCache" / f"{revision}.png"
            ))
        stats = self._stats_by_key([
            (900, "L_Stage01", 10, 0, 1),
            (20000, "L_Stage01", 20, 1, 1),
            (300000, "L_Stage01", 30, 2, 1),
        ])
        time_data, over_data = app._trend_data(measurements, stats, "L_Stage01", "Mean")
        self.assertEqual(
            time_data["revision_label"].drop_duplicates().tolist(),
            ["900", "1000", "20000", "20100", "300000"],
        )
        self.assertTrue(time_data.loc[time_data["revision"] == 1000, "actual_value"].isna().all())
        self.assertTrue(time_data.loc[time_data["revision"] == 20100, "actual_value"].isna().all())
        time_spec = app._time_trend_chart(time_data).to_dict()
        over_spec = app._over_budget_trend_chart(over_data).to_dict()
        expected_order = ["900", "1000", "20000", "20100", "300000"]
        self.assertEqual(time_spec["layer"][1]["encoding"]["x"]["type"], "ordinal")
        self.assertEqual(time_spec["layer"][1]["encoding"]["x"]["sort"], expected_order)
        self.assertEqual(
            time_spec["layer"][1]["mark"]["invalid"],
            "break-paths-show-domains",
        )
        self.assertEqual(time_spec["layer"][2]["encoding"]["x"]["field"], "revision_label")
        self.assertEqual(over_spec["encoding"]["x"]["type"], "ordinal")
        self.assertEqual(over_spec["encoding"]["x"]["sort"], expected_order)
        self.assertEqual(over_spec["mark"]["invalid"], "break-paths-show-domains")


if __name__ == "__main__":
    unittest.main()
